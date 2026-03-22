"""Pydantic configuration models and YAML loader."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from semideus.core.errors import ConfigError


# ---------------------------------------------------------------------------
# Config models
# ---------------------------------------------------------------------------

class ProviderConfig(BaseModel):
    name: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key_env: str = "ANTHROPIC_API_KEY"
    base_url: str | None = None
    max_tokens: int = 8192
    temperature: float = 0.0
    extra: dict[str, Any] = Field(default_factory=dict)


class MemoryConfig(BaseModel):
    backend: str = "file"
    path: str = ".semideus/memory"
    extra: dict[str, Any] = Field(default_factory=dict)


class EvolutionConfig(BaseModel):
    enabled: bool = False
    strategy: str = "default"
    sandbox: str = "worktree"  # "worktree" or "docker"
    max_iterations: int = 10
    acceptance_threshold: float = 0.01
    extra: dict[str, Any] = Field(default_factory=dict)


class TrainingConfig(BaseModel):
    enabled: bool = False
    collector: str = "event"
    dataset_format: str = "sft"
    output_dir: str = ".semideus/training"
    extra: dict[str, Any] = Field(default_factory=dict)


class GuardrailsConfig(BaseModel):
    enabled: bool = True
    rules: list[str] = Field(default_factory=lambda: ["safety", "boundaries"])
    extra: dict[str, Any] = Field(default_factory=dict)


class ToolsConfig(BaseModel):
    enabled: list[str] = Field(
        default_factory=lambda: ["filesystem", "shell", "git", "web"]
    )
    sandbox: bool = True
    extra: dict[str, Any] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    max_steps: int = 50
    max_tokens_per_step: int = 8192
    system_prompt: str = "You are a helpful AI agent with access to tools."
    extra: dict[str, Any] = Field(default_factory=dict)


class SkillsConfig(BaseModel):
    dir: str = "skills"
    enabled: list[str] = Field(default_factory=list)  # empty = all available
    auto_select: bool = True  # auto-activate skills based on task keywords
    chains: dict[str, list[str]] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class EvaluationConfig(BaseModel):
    enabled: bool = False
    suites_dir: str = "configs/eval"
    output_dir: str = ".semideus/eval_results"
    parallel: bool = False
    benchmarks: list[str] = Field(default_factory=list)


class TraceConfig(BaseModel):
    enabled: bool = False
    path: str = ".semideus/traces"
    extra: dict[str, Any] = Field(default_factory=dict)


class HarnessConfig(BaseModel):
    """Top-level harness configuration."""

    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    guardrails: GuardrailsConfig = Field(default_factory=GuardrailsConfig)
    evolution: EvolutionConfig = Field(default_factory=EvolutionConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    trace: TraceConfig = Field(default_factory=TraceConfig)
    plugins_dir: str = "plugins"
    extra: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, returning an empty dict if it doesn't exist."""
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data or {}


def load_config(
    config_path: str | Path | None = None,
    overrides: dict[str, Any] | None = None,
    base_dir: str | Path | None = None,
) -> HarnessConfig:
    """Load harness configuration from YAML with optional overrides.

    Resolution order:
    1. base_dir/configs/default.yaml (base)
    2. config_path (if provided)
    3. overrides dict (if provided)
    """
    if base_dir is None:
        base_dir = Path.cwd()
    config_base = Path(base_dir) / "configs"
    data: dict[str, Any] = {}

    # Load base defaults
    default_path = config_base / "default.yaml"
    if default_path.exists():
        data = load_yaml(default_path)

    # Merge config_path
    if config_path:
        overlay = load_yaml(Path(config_path))
        data = _deep_merge(data, overlay)

    # Merge overrides
    if overrides:
        data = _deep_merge(data, overrides)

    try:
        return HarnessConfig(**data)
    except Exception as e:
        raise ConfigError(f"Invalid configuration: {e}") from e


def resolve_api_key(config: ProviderConfig) -> str | None:
    """Resolve API key from environment variable."""
    return os.environ.get(config.api_key_env)
