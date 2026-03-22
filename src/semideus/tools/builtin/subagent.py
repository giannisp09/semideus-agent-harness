"""Sub-agent parallel execution tool."""

from __future__ import annotations

import asyncio
from typing import Any

from semideus.core.config import HarnessConfig
from semideus.core.interfaces import Tool
from semideus.core.types import ToolDefinition, ToolResult


class SubAgentTool(Tool):
    """Spawn parallel sub-agents to solve tasks."""

    def __init__(self, config: HarnessConfig) -> None:
        # Create a deep copy of the config if needed, or re-use
        # We re-use it so the sub-agent has the same capabilities.
        self._config = config

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="subagent_parallel",
            description="Spawn multiple isolated sub-agents to execute tasks in parallel.",
            parameters={
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "A list of tasks for the sub-agents to execute. Each task is run by a separate sub-agent.",
                    }
                },
                "required": ["tasks"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        tasks = arguments.get("tasks", [])
        if not tasks:
            return ToolResult(tool_call_id="", content="No tasks provided.", is_error=True)
            
        from semideus.harness.harness import Harness
        
        async def run_subagent(task: str, i: int) -> str:
            # Create an isolated harness instance for parallel execution
            harness = Harness(self._config)
            try:
                result = await harness.run(task)
                return f"--- Sub-agent {i} Task: {task} ---\n{result}"
            except Exception as e:
                return f"--- Sub-agent {i} Error (Task: {task}) ---\n{e}"
            finally:
                await harness.close()

        # Run all sub-agents concurrently
        results = await asyncio.gather(*(run_subagent(task, i) for i, task in enumerate(tasks)))
        
        combined_output = "\n\n".join(results)
        return ToolResult(tool_call_id="", content=combined_output, is_error=False)
