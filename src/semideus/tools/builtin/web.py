"""HTTP fetch tool."""

from __future__ import annotations

from typing import Any

import httpx

from semideus.core.interfaces import Tool
from semideus.core.types import ToolDefinition, ToolResult


class HttpFetchTool(Tool):
    """Fetch a URL and return its content."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="http_fetch",
            description="Fetch the content of a URL via HTTP GET.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch.",
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP headers.",
                    },
                },
                "required": ["url"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        url = arguments["url"]
        headers = arguments.get("headers", {})

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                content_type = response.headers.get("content-type", "")

                if "text" in content_type or "json" in content_type or "xml" in content_type:
                    body = response.text
                else:
                    body = f"[Binary content: {content_type}, {len(response.content)} bytes]"

                result = f"Status: {response.status_code}\n\n{body}"
                # Truncate very large responses
                if len(result) > 50_000:
                    result = result[:50_000] + "\n\n[Truncated]"

                return ToolResult(tool_call_id="", content=result)
        except Exception as e:
            return ToolResult(tool_call_id="", content=f"HTTP error: {e}", is_error=True)
