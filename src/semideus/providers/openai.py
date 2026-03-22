"""OpenAI provider via the OpenAI SDK."""

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


def _messages_to_openai(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert our Message format to OpenAI's API format."""
    api_messages: list[dict[str, Any]] = []

    for msg in messages:
        entry: dict[str, Any] = {"role": msg.role.value}

        if msg.role == Role.TOOL:
            entry["tool_call_id"] = msg.tool_call_id
            entry["content"] = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
        elif msg.tool_calls:
            entry["content"] = msg.content or ""
            entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in msg.tool_calls
            ]
        else:
            entry["content"] = msg.content

        api_messages.append(entry)

    return api_messages


def _tools_to_openai(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Convert ToolDefinition list to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def _parse_response(response: Any) -> LLMResponse:
    """Parse an OpenAI API response into our LLMResponse."""
    choice = response.choices[0]
    message = choice.message

    content = message.content or ""
    tool_calls: list[ToolCall] = []

    if message.tool_calls:
        for tc in message.tool_calls:
            tool_calls.append(
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                )
            )

    stop_map = {"stop": StopReason.END_TURN, "tool_calls": StopReason.TOOL_USE, "length": StopReason.MAX_TOKENS}
    stop_reason = stop_map.get(choice.finish_reason or "stop", StopReason.END_TURN)

    usage = None
    if response.usage:
        usage = TokenUsage(
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )

    return LLMResponse(
        content=content,
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        usage=usage,
    )


@registry.register(ComponentType.PROVIDER, "openai")
class OpenAIProvider(LLMProvider):
    """OpenAI provider using the OpenAI SDK."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        api_key = resolve_api_key(config)
        if not api_key:
            raise ProviderError(
                f"API key not found in env var '{config.api_key_env}'. "
                f"Set {config.api_key_env} to use the OpenAI provider."
            )
        try:
            import openai
        except ImportError:
            raise ProviderError("openai package not installed. Run: uv add openai")

        kwargs: dict[str, Any] = {"api_key": api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = openai.AsyncOpenAI(**kwargs)

    @property
    def name(self) -> str:
        return "openai"

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        api_messages = _messages_to_openai(messages)

        create_kwargs: dict[str, Any] = {
            "model": kwargs.pop("model", self._config.model),
            "max_tokens": kwargs.pop("max_tokens", self._config.max_tokens),
            "messages": api_messages,
            **kwargs,
        }
        if self._config.temperature > 0:
            create_kwargs["temperature"] = self._config.temperature
        if tools:
            create_kwargs["tools"] = _tools_to_openai(tools)

        try:
            response = await self._client.chat.completions.create(**create_kwargs)
            return _parse_response(response)
        except Exception as e:
            raise ProviderError(f"OpenAI API error: {e}") from e

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMResponse]:
        api_messages = _messages_to_openai(messages)

        create_kwargs: dict[str, Any] = {
            "model": kwargs.pop("model", self._config.model),
            "max_tokens": kwargs.pop("max_tokens", self._config.max_tokens),
            "messages": api_messages,
            "stream": True,
            **kwargs,
        }
        if self._config.temperature > 0:
            create_kwargs["temperature"] = self._config.temperature
        if tools:
            create_kwargs["tools"] = _tools_to_openai(tools)

        try:
            stream = await self._client.chat.completions.create(**create_kwargs)
            collected_content = ""
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    collected_content += delta
                    yield LLMResponse(content=delta)
            yield LLMResponse(content=collected_content, stop_reason=StopReason.END_TURN)
        except Exception as e:
            raise ProviderError(f"OpenAI streaming error: {e}") from e

    async def close(self) -> None:
        await self._client.close()
