"""Load skills from YAML definition files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from semideus.core.errors import SkillError
from semideus.core.interfaces import Skill, SkillMetadata
from semideus.core.types import ToolDefinition

logger = logging.getLogger(__name__)


class FileSkill(Skill):
    """A skill loaded from a YAML definition file.

    YAML schema::

        name: debug
        description: Systematic debugging of code issues
        version: "0.1.0"
        tags: [debugging, code, errors]

        system_prompt: |
          You are in debug mode. Analyze the issue systematically:
          1. Reproduce the problem
          2. Identify root cause
          3. Propose a fix

        triggers:
          keywords: [debug, error, bug, traceback, exception, crash]
          explicit: [/debug]

        chain_next: fix   # optional: auto-chain to another skill

        tools: []  # optional: additional tool definitions
    """

    def __init__(self, data: dict[str, Any], source_path: Path | None = None) -> None:
        self._data = data
        self._source = source_path
        self._metadata = SkillMetadata(
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "0.1.0"),
            tags=data.get("tags", []),
        )
        self._system_prompt = data.get("system_prompt", "")
        self._trigger_keywords: list[str] = (
            data.get("triggers", {}).get("keywords", [])
        )
        self._trigger_explicit: list[str] = (
            data.get("triggers", {}).get("explicit", [])
        )
        self._chain_next: str | None = data.get("chain_next")
        self._tool_defs = self._parse_tools(data.get("tools", []))

    def _parse_tools(self, raw_tools: list[dict[str, Any]]) -> list[ToolDefinition]:
        """Parse tool definitions from YAML data."""
        defs: list[ToolDefinition] = []
        for t in raw_tools:
            if "name" not in t:
                continue
            defs.append(ToolDefinition(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("parameters", {}),
            ))
        return defs

    @property
    def metadata(self) -> SkillMetadata:
        return self._metadata

    def get_system_prompt(self) -> str:
        return self._system_prompt

    def get_tools(self) -> list[ToolDefinition]:
        return list(self._tool_defs)

    @property
    def trigger_keywords(self) -> list[str]:
        return self._trigger_keywords

    @property
    def trigger_explicit(self) -> list[str]:
        return self._trigger_explicit

    @property
    def chain_next(self) -> str | None:
        return self._chain_next

    @property
    def source_path(self) -> Path | None:
        return self._source


def load_skill_file(path: Path) -> FileSkill:
    """Load a single skill from a YAML file."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise SkillError(f"Failed to parse skill file {path}: {e}") from e

    if not isinstance(data, dict) or "name" not in data:
        raise SkillError(
            f"Invalid skill file {path}: must be a YAML mapping with a 'name' field"
        )

    return FileSkill(data, source_path=path)


def load_skills_from_directory(skills_dir: str | Path) -> list[FileSkill]:
    """Scan a directory for YAML skill definitions and load them all.

    Searches for ``*.yaml`` and ``*.yml`` files (non-recursive by default,
    recursive with ``**/`` patterns if the directory has subdirectories).
    """
    base = Path(skills_dir)
    if not base.is_dir():
        logger.debug("Skills directory does not exist: %s", base)
        return []

    skills: list[FileSkill] = []
    for pattern in ("*.yaml", "*.yml"):
        for yaml_path in sorted(base.rglob(pattern)):
            try:
                skill = load_skill_file(yaml_path)
                skills.append(skill)
                logger.debug("Loaded skill: %s from %s", skill.metadata.name, yaml_path)
            except SkillError as e:
                logger.warning("Skipping invalid skill file: %s", e)

    return skills
