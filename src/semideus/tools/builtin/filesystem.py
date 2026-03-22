"""Filesystem tools: read, write, list, glob."""

from __future__ import annotations

import glob as glob_module
import os
from pathlib import Path
from typing import Any

from semideus.core.interfaces import Tool
from semideus.core.types import ToolDefinition, ToolResult


class ReadFileTool(Tool):
    """Read the contents of a file."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description="Read the contents of a file at the given path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The file path to read.",
                    },
                },
                "required": ["path"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = arguments["path"]
        try:
            content = Path(path).read_text(encoding="utf-8")
            return ToolResult(tool_call_id="", content=content)
        except FileNotFoundError:
            return ToolResult(tool_call_id="", content=f"File not found: {path}", is_error=True)
        except Exception as e:
            return ToolResult(tool_call_id="", content=f"Error reading file: {e}", is_error=True)


class WriteFileTool(Tool):
    """Write content to a file."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="write_file",
            description="Write content to a file, creating parent directories if needed.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The file path to write to.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write.",
                    },
                },
                "required": ["path", "content"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = Path(arguments["path"])
        content = arguments["content"]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolResult(tool_call_id="", content=f"Wrote {len(content)} bytes to {path}")
        except Exception as e:
            return ToolResult(tool_call_id="", content=f"Error writing file: {e}", is_error=True)


class ListDirTool(Tool):
    """List directory contents."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_directory",
            description="List files and directories at the given path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list. Defaults to current directory.",
                        "default": ".",
                    },
                },
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = arguments.get("path", ".")
        try:
            entries = sorted(os.listdir(path))
            result_lines = []
            for entry in entries:
                full = os.path.join(path, entry)
                kind = "dir" if os.path.isdir(full) else "file"
                result_lines.append(f"[{kind}] {entry}")
            return ToolResult(tool_call_id="", content="\n".join(result_lines) or "(empty directory)")
        except Exception as e:
            return ToolResult(tool_call_id="", content=f"Error listing directory: {e}", is_error=True)


class GlobTool(Tool):
    """Find files matching a glob pattern."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="glob",
            description="Find files matching a glob pattern (e.g., '**/*.py').",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern to match.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Base directory for the search. Defaults to current directory.",
                        "default": ".",
                    },
                },
                "required": ["pattern"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        pattern = arguments["pattern"]
        base = arguments.get("path", ".")
        try:
            full_pattern = os.path.join(base, pattern)
            matches = sorted(glob_module.glob(full_pattern, recursive=True))
            if matches:
                return ToolResult(tool_call_id="", content="\n".join(matches))
            return ToolResult(tool_call_id="", content=f"No files matching: {pattern}")
        except Exception as e:
            return ToolResult(tool_call_id="", content=f"Glob error: {e}", is_error=True)
