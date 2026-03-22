"""Skill manager: registry, activation, auto-selection, progressive disclosure."""

from __future__ import annotations

import logging
from typing import Any

from semideus.core.events import EventBus
from semideus.core.interfaces import Skill
from semideus.core.types import ToolDefinition

logger = logging.getLogger(__name__)


class SkillManager:
    """Manages the lifecycle of skills: registration, activation, and selection.

    Design principles (from M2* and LangChain harness anatomy):
        - **Progressive disclosure**: only active skill prompts/tools are injected
          into the LLM context, preventing context rot.
        - **Auto-selection**: skills can be automatically activated based on
          task keywords matching skill trigger words.
        - **Hierarchical composition**: skills can chain to other skills
          (via ``chain_next``), enabling ``/debug -> /fix -> /report`` flows.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._available: dict[str, Skill] = {}
        self._active: dict[str, Skill] = {}
        self._event_bus = event_bus

    # -- Registration ----------------------------------------------------------

    def register(self, skill: Skill) -> None:
        """Register a skill as available (not yet active)."""
        name = skill.metadata.name
        if name in self._available:
            logger.warning("Overwriting skill: %s", name)
        self._available[name] = skill
        logger.debug("Registered skill: %s", name)

    def unregister(self, name: str) -> None:
        """Remove a skill from the registry."""
        self._available.pop(name, None)
        self._active.pop(name, None)

    # -- Activation / deactivation ---------------------------------------------

    async def activate(self, name: str) -> None:
        """Activate a skill — its prompt and tools will be injected into context."""
        if name not in self._available:
            logger.warning("Cannot activate unknown skill: %s", name)
            return
        skill = self._available[name]
        self._active[name] = skill
        await skill.on_activate()
        if self._event_bus:
            await self._event_bus.emit("skill.activated", {"name": name})
        logger.debug("Activated skill: %s", name)

    async def deactivate(self, name: str) -> None:
        """Deactivate a skill — removes its prompt and tools from context."""
        skill = self._active.pop(name, None)
        if skill:
            await skill.on_deactivate()
            if self._event_bus:
                await self._event_bus.emit("skill.deactivated", {"name": name})
            logger.debug("Deactivated skill: %s", name)

    async def deactivate_all(self) -> None:
        """Deactivate all skills."""
        for name in list(self._active.keys()):
            await self.deactivate(name)

    # -- Auto-selection --------------------------------------------------------

    async def select_for_task(self, task: str) -> list[str]:
        """Auto-select and activate skills based on task content.

        Matches task text against each skill's trigger keywords.
        Returns the list of newly activated skill names.
        """
        task_lower = task.lower()
        activated: list[str] = []

        for name, skill in self._available.items():
            if name in self._active:
                continue  # Already active

            # Check explicit triggers (e.g., "/debug" in the task)
            trigger_explicit = getattr(skill, "trigger_explicit", [])
            if any(trigger in task_lower for trigger in trigger_explicit):
                await self.activate(name)
                activated.append(name)
                continue

            # Check keyword triggers
            trigger_keywords = getattr(skill, "trigger_keywords", [])
            if any(kw.lower() in task_lower for kw in trigger_keywords):
                await self.activate(name)
                activated.append(name)

        if activated:
            logger.info("Auto-activated skills for task: %s", activated)
        return activated

    # -- Progressive disclosure ------------------------------------------------

    def get_active_prompts(self) -> list[str]:
        """Return system prompt fragments from all active skills.

        These should be injected into the ContextManager before the LLM call.
        """
        prompts: list[str] = []
        for skill in self._active.values():
            prompt = skill.get_system_prompt()
            if prompt:
                prompts.append(prompt)
        return prompts

    def get_active_tools(self) -> list[ToolDefinition]:
        """Return tool definitions from all active skills.

        These should be registered with the ToolManager alongside built-in tools.
        """
        tools: list[ToolDefinition] = []
        for skill in self._active.values():
            tools.extend(skill.get_tools())
        return tools

    # -- Introspection ---------------------------------------------------------

    @property
    def available_names(self) -> list[str]:
        return list(self._available.keys())

    @property
    def active_names(self) -> list[str]:
        return list(self._active.keys())

    def get_skill(self, name: str) -> Skill | None:
        return self._available.get(name)

    def get_chain_next(self, name: str) -> str | None:
        """Get the next skill in a chain, if configured."""
        skill = self._available.get(name)
        if skill and hasattr(skill, "chain_next"):
            return skill.chain_next
        return None
