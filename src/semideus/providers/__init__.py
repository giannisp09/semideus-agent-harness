"""LLM provider implementations."""

# Import providers to trigger registration
from semideus.providers.anthropic import AnthropicProvider
from semideus.providers.openai import OpenAIProvider
from semideus.providers.vllm_local import VLLMLocalProvider
from semideus.providers.ollama import OllamaProvider
from semideus.providers.router import ModelRouter

__all__ = ["AnthropicProvider", "OpenAIProvider", "VLLMLocalProvider", "OllamaProvider", "ModelRouter"]
