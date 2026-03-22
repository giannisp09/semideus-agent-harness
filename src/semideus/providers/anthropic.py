"""Claude provider via the Anthropic SDK."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from semideus.core.config import ProviderConfig, resolve_api_key
from semideus.core.errors import ProviderError
from semideus.core.interfaces import LLMProvider
from semideus.core.registry import registry
from semideus.core.types import (
    ComponentType,
    LLMResponse,
    Message,
    Role,
    StopReason,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


def _messages_to_anthropic(
    messages: list[Message],
) -> tuple[str | None, list[dict[str, Any]]]:
    """Convert our Message format to Anthropic's API format.

    Returns (system_prompt, messages).
    """
    system = None
    api_messages: list[dict[str, Any]] = []

    for msg in messages:
        if msg.role == Role.SYSTEM:
            system = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
            continue

        entry: dict[str, Any] = {"role": msg.role.value}

        if msg.role == Role.TOOL:
            entry["role"] = "user"
            entry["content"] = [
                {
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": msg.content if isinstance(msg.content, str) else json.dumps(msg.content),
                }
            ]
        elif msg.tool_calls:
            content_blocks: list[dict[str, Any]] = []
            if msg.content:
                content_blocks.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls:
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                })
            entry["content"] = content_blocks
        else:
            entry["content"] = msg.content

        api_messages.append(entry)

    return system, api_messages


def _tools_to_anthropic(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Convert ToolDefinition list to Anthropic tool format."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters,
        }
        for t in tools
    ]


def _parse_response(response: Any) -> LLMResponse:
    """Parse an Anthropic API response into our LLMResponse."""
    content = ""
    tool_calls: list[ToolCall] = []

    for block in response.content:
        if block.type == "text":
            content += block.text
        elif block.type == "tool_use":
            tool_calls.append(
                ToolCall(id=block.id, name=block.name, arguments=block.input)
            )

    stop_map = {"end_turn": StopReason.END_TURN, "tool_use": StopReason.TOOL_USE, "max_tokens": StopReason.MAX_TOKENS}
    stop_reason = stop_map.get(response.stop_reason, StopReason.END_TURN)

    usage = TokenUsage(
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
    )

    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        usage=usage,
    )


@registry.register(ComponentType.PROVIDER, "anthropic")
class AnthropicProvider(LLMProvider):
    """Claude provider using the Anthropic SDK."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        api_key = resolve_api_key(config)
        if not api_key:
            raise ProviderError(
                f"API key not found in env var '{config.api_key_env}'. "
                f"Set {config.api_key_env} to use the Anthropic provider."
            )
        try:
            import anthropic
        except ImportError:
            raise ProviderError("anthropic package not installed. Run: uv add anthropic")

        kwargs: dict[str, Any] = {"api_key": api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = anthropic.AsyncAnthropic(**kwargs)

    @property
    def name(self) -> str:
        return "anthropic"

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        system, api_messages = _messages_to_anthropic(messages)

        create_kwargs: dict[str, Any] = {
            "model": kwargs.pop("model", self._config.model),
            "max_tokens": kwargs.pop("max_tokens", self._config.max_tokens),
            "messages": api_messages,
            **kwargs,
        }
        if system:
            create_kwargs["system"] = system
        if self._config.temperature > 0:
            create_kwargs["temperature"] = self._config.temperature
        if tools:
            create_kwargs["tools"] = _tools_to_anthropic(tools)

        try:
            response = await self._client.messages.create(**create_kwargs)
            return _parse_response(response)
        except Exception as e:
            raise ProviderError(f"Anthropic API error: {e}") from e

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMResponse]:
        system, api_messages = _messages_to_anthropic(messages)

        create_kwargs: dict[str, Any] = {
            "model": kwargs.pop("model", self._config.model),
            "max_tokens": kwargs.pop("max_tokens", self._config.max_tokens),
            "messages": api_messages,
            **kwargs,
        }
        if system:
            create_kwargs["system"] = system
        if self._config.temperature > 0:
            create_kwargs["temperature"] = self._config.temperature
        if tools:
            create_kwargs["tools"] = _tools_to_anthropic(tools)

        try:
            async with self._client.messages.stream(**create_kwargs) as stream:
                async for event in stream:
                    if hasattr(event, "type") and event.type == "content_block_delta":
                        if hasattr(event.delta, "text"):
                            yield LLMResponse(content=event.delta.text)
                # Get final message for usage
                final = await stream.get_final_message()
                yield _parse_response(final)
        except Exception as e:
            raise ProviderError(f"Anthropic streaming error: {e}") from e

    async def close(self) -> None:
        await self._client.close()
