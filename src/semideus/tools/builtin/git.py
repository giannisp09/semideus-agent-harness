"""Git operation tools."""

from __future__ import annotations

from typing import Any

from semideus.core.interfaces import Tool
from semideus.core.types import ToolDefinition, ToolResult
from semideus.tools.execution import execute_command


class GitStatusTool(Tool):
    """Show git repository status."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_status",
            description="Show the working tree status of the git repository.",
            parameters={
                "type": "object",
                "properties": {
                    "cwd": {
                        "type": "string",
                        "description": "Repository directory (defaults to current).",
                    },
                },
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        cwd = arguments.get("cwd")
        result = await execute_command("git status", cwd=cwd)
        return ToolResult(tool_call_id="", content=result.output, is_error=not result.success)


class GitDiffTool(Tool):
    """Show git diff."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_diff",
            description="Show changes in the working directory or between commits.",
            parameters={
                "type": "object",
                "properties": {
                    "args": {
                        "type": "string",
                        "description": "Additional arguments (e.g., '--staged', 'HEAD~1').",
                        "default": "",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Repository directory.",
                    },
                },
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        args = arguments.get("args", "")
        cwd = arguments.get("cwd")
        result = await execute_command(f"git diff {args}", cwd=cwd)
        return ToolResult(tool_call_id="", content=result.output, is_error=not result.success)


class GitLogTool(Tool):
    """Show git log."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_log",
            description="Show recent git commit history.",
            parameters={
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "description": "Number of commits to show (default 10).",
                        "default": 10,
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Repository directory.",
                    },
                },
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        count = arguments.get("count", 10)
        cwd = arguments.get("cwd")
        result = await execute_command(
            f"git log --oneline -n {count}", cwd=cwd
        )
        return ToolResult(tool_call_id="", content=result.output, is_error=not result.success)
