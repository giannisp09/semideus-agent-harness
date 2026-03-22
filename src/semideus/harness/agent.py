"""Agent runtime: message loop, tool call dispatch, context injection."""

from __future__ import annotations

import logging
from typing import Any

from semideus.core.events import EventBus
from semideus.core.interfaces import LLMProvider
from semideus.core.types import (
    LLMResponse,
    Message,
    Role,
    SessionStatus,
    StopReason,
    ToolDefinition,
)
from semideus.harness.context import ContextManager
from semideus.harness.state import SessionState
from semideus.memory.manager import MemoryManager
from semideus.skills.manager import SkillManager
from semideus.tools.manager import ToolManager

logger = logging.getLogger(__name__)


class Agent:
    """Agent runtime that orchestrates the LLM step loop.

    Each step: send messages -> get response -> dispatch tool calls -> repeat.
    Stops when the LLM returns end_turn, hits max_steps, or errors out.

    Integrates with:
        - **MemoryManager**: logs each step to session memory for iteration tracking
        - **SkillManager**: provides active skill tools alongside built-in tools
    """

    def __init__(
        self,
        provider: LLMProvider,
        tool_manager: ToolManager,
        context: ContextManager,
        event_bus: EventBus,
        max_steps: int = 50,
        memory_manager: MemoryManager | None = None,
        skill_manager: SkillManager | None = None,
    ) -> None:
        self._provider = provider
        self._tools = tool_manager
        self._context = context
        self._events = event_bus
        self._max_steps = max_steps
        self._state = SessionState()
        self._memory = memory_manager
        self._skills = skill_manager

    @property
    def state(self) -> SessionState:
        return self._state

    async def run(self, task: str) -> str:
        """Run the agent on a task, returning the final text response."""
        self._context.add_user_message(task)
        await self._events.emit("session.start", {"task": task, "session_id": self._state.session_id})

        final_content = ""
        try:
            while self._state.step_count < self._max_steps:
                response = await self._step()
                self._state.record_step(response.usage)

                # Trace logging for debugging agent behavior
                logger.info(
                    "Agent step %d: stop_reason=%s, tool_calls=%s, content_preview=%s",
                    self._state.step_count,
                    response.stop_reason.value,
                    [tc.name for tc in response.tool_calls] if response.tool_calls else "none",
                    repr(response.content[:200]) if response.content else "empty",
                )

                # Log step to session memory for iteration tracking (M2* pattern)
                if self._memory:
                    step_summary = (
                        f"tool_calls={[tc.name for tc in response.tool_calls]}"
                        if response.tool_calls
                        else f"response={response.content[:200]}"
                    )
                    self._memory.log_step(
                        step=self._state.step_count,
                        summary=step_summary,
                        metadata={"stop_reason": response.stop_reason.value},
                    )

                if response.tool_calls:
                    # Record assistant message with tool calls
                    consecutive_no_tool = 0  # Reset nudge counter
                    self._context.add_assistant_message(
                        response.content, tool_calls=response.tool_calls
                    )
                    # Execute tool calls
                    for tc in response.tool_calls:
                        await self._events.emit(
                            "tool.call.before",
                            {"name": tc.name, "arguments": tc.arguments},
                        )
                        result = await self._tools.execute(tc.name, tc.arguments)
                        logger.info(
                            "  Tool '%s' result: is_error=%s, content_preview=%s",
                            tc.name,
                            result.is_error,
                            repr(result.content[:300]) if result.content else "empty",
                        )
                        self._context.add_tool_result(
                            tc.id, result.content, result.is_error
                        )
                        await self._events.emit(
                            "tool.call.after",
                            {"name": tc.name, "result": result.content, "is_error": result.is_error},
                        )
                else:
                    # No tool calls — check if we should nudge the model to use tools
                    consecutive_no_tool += 1
                    
                    # If max nudges exceeded or this looks like a genuine final answer, stop
                    if consecutive_no_tool > 3:
                        logger.info(
                            "Agent stopping: %d consecutive responses without tool calls",
                            consecutive_no_tool,
                        )
                        final_content = response.content
                        self._context.add_assistant_message(response.content)
                        break
                    
                    # Record the assistant's text and nudge it to act
                    self._context.add_assistant_message(response.content)
                    nudge = (
                        "You wrote a plan but did not use any tools. "
                        "You MUST use the available tools to take action NOW. "
                        "Start by calling the 'shell' tool or 'read_file' tool to begin your work. "
                        "Do NOT just describe what you would do — actually do it by calling a tool."
                    )
                    self._context.add_user_message(nudge)
                    logger.info(
                        "Agent nudge %d: model returned text without tool calls, re-prompting",
                        consecutive_no_tool,
                    )
            else:
                final_content = "[Agent reached maximum step limit]"
                logger.warning("Agent hit max_steps=%d", self._max_steps)

            self._state.finish(SessionStatus.COMPLETED)
        except Exception as e:
            self._state.finish(SessionStatus.FAILED)
            logger.error("Agent error: %s", e)
            raise
        finally:
            await self._events.emit(
                "session.end",
                {
                    "session_id": self._state.session_id,
                    "status": self._state.status.value,
                    "steps": self._state.step_count,
                    "usage": self._state.total_usage.model_dump(),
                },
            )

        return final_content

    async def _step(self) -> LLMResponse:
        """Execute a single agent step (LLM call)."""
        await self._events.emit(
            "agent.step.before",
            {"step": self._state.step_count},
        )

        # Combine built-in tools with active skill tools
        tool_defs = self._tools.get_tool_definitions()
        if self._skills:
            tool_defs = tool_defs + self._skills.get_active_tools()

        response = await self._provider.complete(
            messages=self._context.messages,
            tools=tool_defs if tool_defs else None,
        )

        await self._events.emit(
            "agent.step.after",
            {
                "step": self._state.step_count,
                "stop_reason": response.stop_reason.value,
                "has_tool_calls": bool(response.tool_calls),
            },
        )

        return response
