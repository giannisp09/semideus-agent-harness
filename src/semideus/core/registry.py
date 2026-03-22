"""Plugin registry with decorator registration and filesystem discovery."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, Callable, TypeVar

from semideus.core.errors import RegistryError
from semideus.core.types import ComponentType

logger = logging.getLogger(__name__)

T = TypeVar("T")
Factory = Callable[..., Any]


class ComponentRegistry:
    """Central registry for all swappable components.

    Usage:
        registry = ComponentRegistry()

        @registry.register(ComponentType.PROVIDER, "anthropic")
        class AnthropicProvider:
            ...

        provider_cls = registry.get(ComponentType.PROVIDER, "anthropic")
    """

    def __init__(self) -> None:
        self._components: dict[ComponentType, dict[str, Factory]] = {}

    def register(
        self, component_type: ComponentType, name: str
    ) -> Callable[[T], T]:
        """Decorator to register a component factory/class."""
        def decorator(cls: T) -> T:
            self.register_factory(component_type, name, cls)
            return cls
        return decorator

    def register_factory(
        self, component_type: ComponentType, name: str, factory: Factory
    ) -> None:
        """Programmatically register a component factory."""
        if component_type not in self._components:
            self._components[component_type] = {}
        if name in self._components[component_type]:
            logger.warning(
                "Overwriting %s/%s in registry", component_type.value, name
            )
        self._components[component_type][name] = factory
        logger.debug("Registered %s/%s", component_type.value, name)

    def get(self, component_type: ComponentType, name: str) -> Factory:
        """Retrieve a registered component factory."""
        try:
            return self._components[component_type][name]
        except KeyError:
            available = self.list(component_type)
            raise RegistryError(
                f"Component '{name}' not found in {component_type.value}. "
                f"Available: {available}"
            )

    def list(self, component_type: ComponentType) -> list[str]:
        """List all registered names for a component type."""
        return list(self._components.get(component_type, {}).keys())

    def list_all(self) -> dict[str, list[str]]:
        """List all registered components grouped by type."""
        return {
            ct.value: self.list(ct)
            for ct in ComponentType
            if self.list(ct)
        }

    def discover_plugins(self, plugin_dir: Path) -> int:
        """Scan a directory for plugin modules and import them.

        Plugins register themselves via @registry.register decorators.
        Returns the number of modules loaded.
        """
        if not plugin_dir.is_dir():
            return 0
        count = 0
        for py_file in sorted(plugin_dir.glob("**/*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = (
                str(py_file.relative_to(plugin_dir.parent))
                .replace("/", ".")
                .removesuffix(".py")
            )
            try:
                importlib.import_module(module_name)
                count += 1
                logger.debug("Loaded plugin: %s", module_name)
            except Exception as e:
                logger.warning("Failed to load plugin %s: %s", module_name, e)
        return count

    def discover_entry_points(self, group: str = "semideus.plugins") -> int:
        """Load plugins registered as Python entry points."""
        count = 0
        try:
            from importlib.metadata import entry_points
            eps = entry_points(group=group)
            for ep in eps:
                try:
                    ep.load()
                    count += 1
                    logger.debug("Loaded entry point: %s", ep.name)
                except Exception as e:
                    logger.warning("Failed to load entry point %s: %s", ep.name, e)
        except Exception:
            pass
        return count


# Global singleton registry
registry = ComponentRegistry()
