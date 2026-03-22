"""Context management: message history, system prompt assembly, compaction."""

from __future__ import annotations

from typing import Any

from semideus.core.config import AgentConfig
from semideus.core.types import Message, Role


class ContextManager:
    """Manages the conversation context for an agent session.

    Handles system prompt assembly, message history, and context compaction.
    """

    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        self._messages: list[Message] = []
        self._system_parts: list[str] = [config.system_prompt]

    def add_system_context(self, text: str) -> None:
        """Add a system prompt fragment (e.g., from a skill)."""
        self._system_parts.append(text)

    @property
    def system_prompt(self) -> str:
        return "\n\n".join(self._system_parts)

    @property
    def messages(self) -> list[Message]:
        """Return the full message list including system prompt."""
        system_msg = Message(role=Role.SYSTEM, content=self.system_prompt)
        return [system_msg] + self._messages

    def add_message(self, message: Message) -> None:
        """Add a message to history."""
        self._messages.append(message)

    def add_user_message(self, content: str) -> None:
        self._messages.append(Message(role=Role.USER, content=content))

    def add_assistant_message(
        self, content: str, tool_calls: list[Any] | None = None
    ) -> None:
        self._messages.append(
            Message(role=Role.ASSISTANT, content=content, tool_calls=tool_calls)
        )

    def add_tool_result(self, tool_call_id: str, content: str, is_error: bool = False) -> None:
        prefix = "[ERROR] " if is_error else ""
        self._messages.append(
            Message(role=Role.TOOL, content=f"{prefix}{content}", tool_call_id=tool_call_id)
        )

    @property
    def message_count(self) -> int:
        return len(self._messages)

    def compact(self, keep_last: int = 10) -> None:
        """Simple compaction: keep system + last N messages.

        A more sophisticated implementation would use summarization.
        """
        if len(self._messages) > keep_last:
            self._messages = self._messages[-keep_last:]

    def clear(self) -> None:
        """Clear message history (keeps system prompt)."""
        self._messages.clear()
