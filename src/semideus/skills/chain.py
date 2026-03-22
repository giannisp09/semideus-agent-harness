"""Skill chaining: sequential execution of composable skills."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from semideus.core.events import EventBus
from semideus.skills.manager import SkillManager

logger = logging.getLogger(__name__)


@dataclass
class ChainStep:
    """A single step in a skill chain."""
    skill_name: str
    condition: str | None = None  # Optional: only run if previous output contains this


@dataclass
class SkillChainDef:
    """Definition of a skill chain — an ordered sequence of skills."""
    name: str
    description: str
    steps: list[ChainStep] = field(default_factory=list)


class SkillChainExecutor:
    """Executes skill chains: activating skills in sequence.

    A skill chain defines an ordered pipeline, e.g.::

        debug -> fix -> report

    The executor:
    1. Activates each skill in order
    2. Deactivates the previous skill before activating the next
    3. Supports conditional steps (skip if condition not met)
    4. Emits events for chain lifecycle tracking

    Note: The executor manages skill activation/deactivation only.
    The actual agent loop (LLM calls, tool dispatch) runs in Agent.run().
    Chain execution is meant to wrap multiple agent invocations or to
    reconfigure the agent's skill context between sub-tasks.
    """

    def __init__(
        self,
        skill_manager: SkillManager,
        event_bus: EventBus | None = None,
    ) -> None:
        self._skills = skill_manager
        self._event_bus = event_bus
        self._chains: dict[str, SkillChainDef] = {}

    def register_chain(self, chain: SkillChainDef) -> None:
        """Register a chain definition."""
        self._chains[chain.name] = chain
        logger.debug("Registered skill chain: %s (%d steps)", chain.name, len(chain.steps))

    def register_chain_from_config(
        self, name: str, skill_names: list[str], description: str = ""
    ) -> None:
        """Convenience: create and register a chain from a list of skill names."""
        steps = [ChainStep(skill_name=sn) for sn in skill_names]
        chain = SkillChainDef(name=name, description=description, steps=steps)
        self.register_chain(chain)

    def get_chain(self, name: str) -> SkillChainDef | None:
        return self._chains.get(name)

    @property
    def chain_names(self) -> list[str]:
        return list(self._chains.keys())

    async def advance(
        self,
        chain_name: str,
        current_step: int,
        previous_output: str = "",
    ) -> tuple[int, str | None]:
        """Advance one step in a chain.

        Deactivates the current step's skill, activates the next.

        Args:
            chain_name: Name of the chain to advance.
            current_step: Index of the current step (0-based). Pass -1 to start.
            previous_output: Output from the previous step (used for conditions).

        Returns:
            Tuple of (new_step_index, activated_skill_name).
            Returns (current_step, None) if the chain is complete or step skipped.
        """
        chain = self._chains.get(chain_name)
        if not chain:
            logger.warning("Unknown chain: %s", chain_name)
            return (current_step, None)

        # Deactivate current step's skill (if we're past the start)
        if 0 <= current_step < len(chain.steps):
            await self._skills.deactivate(chain.steps[current_step].skill_name)

        next_step = current_step + 1
        while next_step < len(chain.steps):
            step = chain.steps[next_step]

            # Check condition
            if step.condition and step.condition not in previous_output:
                logger.debug(
                    "Skipping chain step %s (condition '%s' not met)",
                    step.skill_name,
                    step.condition,
                )
                next_step += 1
                continue

            # Activate this step's skill
            await self._skills.activate(step.skill_name)
            if self._event_bus:
                await self._event_bus.emit("skill.chain.step", {
                    "chain": chain_name,
                    "step": next_step,
                    "skill": step.skill_name,
                })
            return (next_step, step.skill_name)

        # Chain complete
        if self._event_bus:
            await self._event_bus.emit("skill.chain.complete", {"chain": chain_name})
        return (next_step, None)

    async def run_full_chain(self, chain_name: str) -> list[str]:
        """Activate all skills in a chain sequentially (no condition checks).

        Returns list of activated skill names. Useful for setting up context
        before an agent run where all skills in the chain should be active.
        """
        chain = self._chains.get(chain_name)
        if not chain:
            return []

        activated: list[str] = []
        for step in chain.steps:
            if step.skill_name in self._skills.available_names:
                await self._skills.activate(step.skill_name)
                activated.append(step.skill_name)

        if self._event_bus:
            await self._event_bus.emit("skill.chain.started", {
                "chain": chain_name,
                "skills": activated,
            })
        return activated

    def build_chain_from_skill(self, start_skill_name: str) -> SkillChainDef | None:
        """Auto-build a chain by following ``chain_next`` links from a starting skill.

        Returns None if the skill has no chain_next configured.
        """
        steps: list[ChainStep] = []
        visited: set[str] = set()
        current = start_skill_name

        while current and current not in visited:
            visited.add(current)
            if current not in self._skills.available_names:
                break
            steps.append(ChainStep(skill_name=current))
            current = self._skills.get_chain_next(current)

        if len(steps) <= 1:
            return None  # No chain to build

        chain = SkillChainDef(
            name=f"auto_{start_skill_name}",
            description=f"Auto-generated chain starting from {start_skill_name}",
            steps=steps,
        )
        return chain
