"""Local Ollama provider via OpenAI-compatible API using httpx."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

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


def _messages_to_openai_compat(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert messages to OpenAI-compatible format."""
    result: list[dict[str, Any]] = []
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
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in msg.tool_calls
            ]
        else:
            entry["content"] = msg.content
        result.append(entry)
    return result


@registry.register(ComponentType.PROVIDER, "ollama")
class OllamaProvider(LLMProvider):
    """Local Ollama provider using the OpenAI-compatible HTTP API."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        base_url = config.base_url or "http://localhost:11434/v1/"
        if not base_url.endswith("/"):
            base_url += "/"
        api_key = resolve_api_key(config) or "not-needed"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=300.0,
        )

    @property
    def name(self) -> str:
        return "ollama"

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        api_messages = _messages_to_openai_compat(messages)

        payload: dict[str, Any] = {
            "model": kwargs.pop("model", self._config.model),
            "max_tokens": kwargs.pop("max_tokens", self._config.max_tokens),
            "messages": api_messages,
            **kwargs,
        }
        if self._config.temperature > 0:
            payload["temperature"] = self._config.temperature
        if tools:
            payload["tools"] = [
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
            logger.debug(
                "Ollama: sending %d tools: %s",
                len(tools),
                [t.name for t in tools],
            )

        try:
            resp = await self._client.post("chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            raise ProviderError(f"Ollama API error: {e}") from e

        choice = data["choices"][0]
        message = choice["message"]
        content = message.get("content", "") or ""

        # Debug: log raw response to diagnose tool calling issues
        logger.debug(
            "Ollama raw response: finish_reason=%s, has_tool_calls=%s, tool_calls_raw=%s, tools_sent=%d",
            choice.get("finish_reason"),
            bool(message.get("tool_calls")),
            message.get("tool_calls"),
            len(payload.get("tools", [])),
        )

        tool_calls: list[ToolCall] = []
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                tool_calls.append(
                    ToolCall(
                        id=tc.get("id", f"call_{len(tool_calls)}"),
                        name=tc["function"]["name"],
                        arguments=json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"],
                    )
                )

        stop_map = {"stop": StopReason.END_TURN, "tool_calls": StopReason.TOOL_USE, "length": StopReason.MAX_TOKENS}
        stop_reason = stop_map.get(choice.get("finish_reason", "stop"), StopReason.END_TURN)

        usage = None
        if "usage" in data:
            usage = TokenUsage(
                input_tokens=data["usage"].get("prompt_tokens", 0),
                output_tokens=data["usage"].get("completion_tokens", 0),
            )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            usage=usage,
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMResponse]:
        api_messages = _messages_to_openai_compat(messages)

        payload: dict[str, Any] = {
            "model": kwargs.pop("model", self._config.model),
            "max_tokens": kwargs.pop("max_tokens", self._config.max_tokens),
            "messages": api_messages,
            "stream": True,
            **kwargs,
        }
        if self._config.temperature > 0:
            payload["temperature"] = self._config.temperature
        if tools:
            payload["tools"] = [
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

        try:
            async with self._client.stream("POST", "chat/completions", json=payload) as resp:
                resp.raise_for_status()
                collected = ""
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    chunk = json.loads(data_str)
                    if chunk["choices"] and chunk["choices"][0]["delta"].get("content"):
                        delta = chunk["choices"][0]["delta"]["content"]
                        collected += delta
                        yield LLMResponse(content=delta)
                yield LLMResponse(content=collected, stop_reason=StopReason.END_TURN)
        except Exception as e:
            raise ProviderError(f"Ollama streaming error: {e}") from e

    async def close(self) -> None:
        await self._client.aclose()
