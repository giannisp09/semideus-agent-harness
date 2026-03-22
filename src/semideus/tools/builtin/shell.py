"""Shell execution tool."""

from __future__ import annotations

from typing import Any

from semideus.core.interfaces import Tool
from semideus.core.types import ToolDefinition, ToolResult
from semideus.tools.execution import execute_command


class ShellTool(Tool):
    """Execute shell commands."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="shell",
            description="Execute a shell command and return the output.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory (defaults to current).",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Timeout in seconds (default 30).",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        command = arguments["command"]
        cwd = arguments.get("cwd")
        timeout = arguments.get("timeout", 30)

        try:
            result = await execute_command(command, cwd=cwd, timeout=timeout)
            return ToolResult(
                tool_call_id="",
                content=result.output,
                is_error=not result.success,
            )
        except Exception as e:
            return ToolResult(tool_call_id="", content=str(e), is_error=True)
