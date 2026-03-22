"""Pydantic models for evaluation test definitions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from semideus.core.types import EvalResult


class TestCase(BaseModel):
    """A single task-completion test case."""

    name: str
    task: str
    expected_patterns: list[str] = Field(default_factory=list)
    max_steps: int = 20
    timeout_seconds: float = 120.0


class SkillTestCase(BaseModel):
    """A test case that verifies skill activation and tool usage."""

    name: str
    task: str
    skill_name: str
    expected_tools: list[str] = Field(default_factory=list)
    expected_output_patterns: list[str] = Field(default_factory=list)


class BenchmarkSuite(BaseModel):
    """A collection of test cases loadable from YAML."""

    name: str
    description: str = ""
    test_cases: list[TestCase] = Field(default_factory=list)
    skill_test_cases: list[SkillTestCase] = Field(default_factory=list)


class AggregateResult(BaseModel):
    """Aggregated results from running multiple benchmarks."""

    results: list[EvalResult] = Field(default_factory=list)
    overall_score: float = 0.0
    total_elapsed: float = 0.0
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
