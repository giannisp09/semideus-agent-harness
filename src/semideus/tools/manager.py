"""Tool manager: registers tools, progressive disclosure, dispatches calls."""

from __future__ import annotations

import logging
from typing import Any

from semideus.core.errors import ToolError
from semideus.core.events import EventBus
from semideus.core.interfaces import Tool
from semideus.core.types import ToolDefinition, ToolResult

logger = logging.getLogger(__name__)


class ToolManager:
    """Central tool registry and dispatcher.

    Registers tools, provides their definitions to the LLM,
    and dispatches execution calls.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self._event_bus = event_bus

    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        name = tool.definition.name
        if name in self._tools:
            logger.warning("Overwriting tool: %s", name)
        self._tools[name] = tool
        logger.debug("Registered tool: %s", name)

    def unregister(self, name: str) -> None:
        """Remove a tool."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool:
        """Get a tool by name."""
        if name not in self._tools:
            available = list(self._tools.keys())
            raise ToolError(f"Tool '{name}' not found. Available: {available}")
        return self._tools[name]

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """Return all registered tool definitions for the LLM."""
        return [tool.definition for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a tool by name with given arguments."""
        tool = self.get(name)
        try:
            result = await tool.execute(arguments)
            return result
        except Exception as e:
            logger.error("Tool '%s' execution failed: %s", name, e)
            return ToolResult(
                tool_call_id="",
                content=f"Tool execution error: {e}",
                is_error=True,
            )

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    @property
    def tool_count(self) -> int:
        return len(self._tools)
