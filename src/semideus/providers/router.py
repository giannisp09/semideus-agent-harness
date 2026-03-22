"""Model router — selects provider per task based on configuration."""

from __future__ import annotations

import logging
from typing import Any

from semideus.core.config import ProviderConfig
from semideus.core.interfaces import LLMProvider
from semideus.core.registry import registry
from semideus.core.types import ComponentType

logger = logging.getLogger(__name__)


class ModelRouter:
    """Routes requests to the appropriate provider based on task or config.

    Supports a default provider and optional task-specific overrides.
    """

    def __init__(
        self,
        default_config: ProviderConfig,
        task_overrides: dict[str, ProviderConfig] | None = None,
    ) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._default_name = default_config.name
        self._task_overrides = task_overrides or {}

        # Initialize default provider
        self._providers[default_config.name] = self._create_provider(default_config)

        # Initialize task-specific providers
        for task, config in self._task_overrides.items():
            if config.name not in self._providers:
                self._providers[config.name] = self._create_provider(config)

    def _create_provider(self, config: ProviderConfig) -> LLMProvider:
        """Create a provider instance from config."""
        provider_cls = registry.get(ComponentType.PROVIDER, config.name)
        return provider_cls(config)

    def get_provider(self, task: str | None = None) -> LLMProvider:
        """Get the provider for a given task, or the default."""
        if task and task in self._task_overrides:
            config = self._task_overrides[task]
            return self._providers[config.name]
        return self._providers[self._default_name]

    @property
    def default_provider(self) -> LLMProvider:
        return self._providers[self._default_name]

    async def close(self) -> None:
        for provider in self._providers.values():
            await provider.close()
