"""Typed mutation models that describe and apply changes to the harness."""

from __future__ import annotations

import logging
import re
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Regex for valid skill names: lowercase letter, then up to 63 lowercase alphanumeric/underscores
_SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class MutationType(str, Enum):
    """Categories of mutations the evolution loop can propose."""

    SKILL_PROMPT = "skill_prompt"
    CONFIG_VALUE = "config_value"
    AGENT_SYSTEM_PROMPT = "agent_system_prompt"
    SKILL_CREATION = "skill_creation"
    SKILL_CHAIN = "skill_chain"
    SKILL_TOOL = "skill_tool"


class Mutation(BaseModel):
    """Base mutation model. Subclasses implement ``apply``."""

    type: MutationType
    description: str = ""

    def apply(self, base_dir: Path) -> None:
        """Apply this mutation to files under *base_dir*."""
        raise NotImplementedError


class SkillPromptMutation(Mutation):
    """Replace or create a skill's system prompt via a YAML override file.

    For builtin Python-defined skills the YAML file will be loaded after the
    builtin, so ``SkillManager.register()`` overwrites the duplicate entry.
    """

    type: MutationType = MutationType.SKILL_PROMPT
    skill_name: str
    new_system_prompt: str

    def apply(self, base_dir: Path) -> None:
        skills_dir = base_dir / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_path = skills_dir / f"{self.skill_name}.yaml"

        # If the YAML already exists, update only the system_prompt field
        if skill_path.exists():
            data = yaml.safe_load(skill_path.read_text(encoding="utf-8")) or {}
        else:
            data = {
                "name": self.skill_name,
                "description": f"Evolved {self.skill_name} skill",
            }

        data["system_prompt"] = self.new_system_prompt
        skill_path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
        logger.info("Applied SkillPromptMutation for '%s' at %s", self.skill_name, skill_path)


class ConfigMutation(Mutation):
    """Change a single value in ``configs/default.yaml`` via a dot-separated path."""

    type: MutationType = MutationType.CONFIG_VALUE
    config_path: str  # e.g. "agent.max_steps"
    new_value: Any

    def apply(self, base_dir: Path) -> None:
        config_file = base_dir / "configs" / "default.yaml"
        if config_file.exists():
            data = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        else:
            data = {}

        # Navigate the dot-separated path and set the value
        keys = self.config_path.split(".")
        node = data
        for key in keys[:-1]:
            if key not in node or not isinstance(node[key], dict):
                node[key] = {}
            node = node[key]
        node[keys[-1]] = self.new_value

        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
        logger.info("Applied ConfigMutation: %s = %s", self.config_path, self.new_value)


class AgentSystemPromptMutation(Mutation):
    """Update the agent system prompt in config YAML."""

    type: MutationType = MutationType.AGENT_SYSTEM_PROMPT
    new_system_prompt: str

    def apply(self, base_dir: Path) -> None:
        config_file = base_dir / "configs" / "default.yaml"
        if config_file.exists():
            data = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        else:
            data = {}

        data.setdefault("agent", {})["system_prompt"] = self.new_system_prompt

        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
        logger.info("Applied AgentSystemPromptMutation")


class SkillCreationMutation(Mutation):
    """Create a brand-new YAML skill file with full schema."""

    type: MutationType = MutationType.SKILL_CREATION
    skill_name: str
    skill_description: str = Field(alias="skill_description", default="")
    system_prompt: str
    trigger_keywords: list[str] = Field(default_factory=list)
    trigger_explicit: list[str] = Field(default_factory=list)
    chain_next: str | None = None
    tags: list[str] = Field(default_factory=list)
    version: str = "0.1.0"

    model_config = {"populate_by_name": True}

    def apply(self, base_dir: Path) -> None:
        if not _SKILL_NAME_RE.match(self.skill_name):
            raise ValueError(
                f"Invalid skill_name '{self.skill_name}': "
                "must match ^[a-z][a-z0-9_]{{0,63}}$"
            )
        if not self.system_prompt.strip():
            raise ValueError("system_prompt must be non-empty")

        skills_dir = base_dir / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        data: dict[str, Any] = {
            "name": self.skill_name,
            "description": self.skill_description or f"Auto-generated {self.skill_name} skill",
            "version": self.version,
            "tags": self.tags,
            "system_prompt": self.system_prompt,
            "triggers": {
                "keywords": self.trigger_keywords,
                "explicit": self.trigger_explicit,
            },
            "chain_next": self.chain_next,
            "tools": [],
        }

        skill_path = skills_dir / f"{self.skill_name}.yaml"
        skill_path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        logger.info("Applied SkillCreationMutation: created '%s' at %s", self.skill_name, skill_path)


class SkillChainMutation(Mutation):
    """Create or modify a skill chain in configs/default.yaml under skills.chains."""

    type: MutationType = MutationType.SKILL_CHAIN
    chain_name: str
    skill_sequence: list[str]
    chain_description: str = Field(alias="chain_description", default="")

    model_config = {"populate_by_name": True}

    def apply(self, base_dir: Path) -> None:
        if len(self.skill_sequence) < 2:
            raise ValueError("skill_sequence must contain at least 2 skill names")

        config_file = base_dir / "configs" / "default.yaml"
        if config_file.exists():
            data = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
        else:
            data = {}

        skills_section = data.setdefault("skills", {})
        chains_section = skills_section.setdefault("chains", {})
        chains_section[self.chain_name] = self.skill_sequence

        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        logger.info(
            "Applied SkillChainMutation: chain '%s' = %s",
            self.chain_name,
            self.skill_sequence,
        )


class SkillToolMutation(Mutation):
    """Add or modify tool declarations in an existing skill's YAML."""

    type: MutationType = MutationType.SKILL_TOOL
    skill_name: str
    tools: list[dict[str, Any]]
    mode: str = "replace"  # "replace" or "append"

    def apply(self, base_dir: Path) -> None:
        skill_path = base_dir / "skills" / f"{self.skill_name}.yaml"
        if not skill_path.exists():
            raise FileNotFoundError(
                f"Skill file not found: {skill_path}. "
                "Cannot add tools to a non-existent skill."
            )

        data = yaml.safe_load(skill_path.read_text(encoding="utf-8")) or {}

        if self.mode == "append":
            existing_tools = data.get("tools", []) or []
            data["tools"] = existing_tools + self.tools
        else:
            data["tools"] = self.tools

        skill_path.write_text(
            yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        logger.info(
            "Applied SkillToolMutation: %s %d tools on '%s'",
            self.mode,
            len(self.tools),
            self.skill_name,
        )


def parse_mutations(specs: list[dict[str, Any]]) -> list[Mutation]:
    """Parse a list of mutation specs (from LLM JSON) into typed Mutation objects."""
    type_map: dict[str, type[Mutation]] = {
        MutationType.SKILL_PROMPT.value: SkillPromptMutation,
        MutationType.CONFIG_VALUE.value: ConfigMutation,
        MutationType.AGENT_SYSTEM_PROMPT.value: AgentSystemPromptMutation,
        MutationType.SKILL_CREATION.value: SkillCreationMutation,
        MutationType.SKILL_CHAIN.value: SkillChainMutation,
        MutationType.SKILL_TOOL.value: SkillToolMutation,
    }
    mutations: list[Mutation] = []
    for spec in specs:
        mut_type = spec.get("type", "")
        cls = type_map.get(mut_type)
        if cls is None:
            logger.warning("Unknown mutation type '%s', skipping", mut_type)
            continue
        mutations.append(cls(**spec))
    return mutations
