"""Skill adherence benchmark — measures whether the agent activates correct skills and tools."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Callable

from semideus.core.interfaces import Benchmark
from semideus.core.registry import registry
from semideus.core.types import ComponentType, EvalResult
from semideus.evaluation.types import BenchmarkSuite, SkillTestCase

logger = logging.getLogger(__name__)

HarnessFactory = Callable[[], Any]


@registry.register(ComponentType.BENCHMARK, "skill_adherence")
class SkillAdherenceBenchmark(Benchmark):
    """Evaluates whether the agent activates the right skills and uses expected tools."""

    def __init__(
        self,
        harness_factory: HarnessFactory | None = None,
        suite: BenchmarkSuite | None = None,
    ) -> None:
        self._harness_factory = harness_factory
        self._suite = suite

    @property
    def name(self) -> str:
        return "skill_adherence"

    async def _run_case(self, tc: SkillTestCase) -> dict[str, Any]:
        """Run a single skill test case with event listeners."""
        harness = self._harness_factory()
        event_bus = harness.event_bus

        activated_skills: list[str] = []
        called_tools: list[str] = []

        async def on_skill_activated(data: dict[str, Any]) -> None:
            activated_skills.append(data.get("name", ""))

        async def on_tool_call(data: dict[str, Any]) -> None:
            called_tools.append(data.get("name", ""))

        event_bus.subscribe("skill.activated", on_skill_activated)
        event_bus.subscribe("tool.call.before", on_tool_call)

        try:
            output = await asyncio.wait_for(
                harness.run(tc.task),
                timeout=120.0,
            )
        except asyncio.TimeoutError:
            output = ""
        except Exception as e:
            logger.error("Skill test case '%s' failed: %s", tc.name, e)
            output = ""
        finally:
            event_bus.unsubscribe("skill.activated", on_skill_activated)
            event_bus.unsubscribe("tool.call.before", on_tool_call)
            try:
                await harness.close()
            except Exception:
                pass

        # Score: activation
        activation = 1.0 if tc.skill_name in activated_skills else 0.0

        # Score: tool adherence
        if tc.expected_tools:
            tool_hits = sum(1 for t in tc.expected_tools if t in called_tools)
            tool_adherence = tool_hits / len(tc.expected_tools)
        else:
            tool_adherence = 1.0

        # Score: output pattern match
        if tc.expected_output_patterns:
            pattern_hits = sum(
                1 for p in tc.expected_output_patterns if re.search(p, output, re.IGNORECASE)
            )
            output_match = pattern_hits / len(tc.expected_output_patterns)
        else:
            output_match = 1.0

        score = 0.4 * activation + 0.35 * tool_adherence + 0.25 * output_match

        return {
            "activation": activation,
            "tool_adherence": tool_adherence,
            "output_match": output_match,
            "score": score,
            "activated_skills": activated_skills,
            "called_tools": called_tools,
        }

    async def run(self, agent: Any = None) -> EvalResult:
        """Run the benchmark."""
        if not self._harness_factory:
            raise ValueError("harness_factory is required for SkillAdherenceBenchmark")

        test_cases = self._suite.skill_test_cases if self._suite else []
        if not test_cases:
            return EvalResult(
                benchmark=self.name,
                score=0.0,
                metrics={},
                details={"error": "No skill test cases provided"},
            )

        per_case: dict[str, float] = {}
        details: dict[str, Any] = {}
        scores: list[float] = []
        total_start = time.monotonic()

        for tc in test_cases:
            case_start = time.monotonic()
            case_result = await self._run_case(tc)
            case_elapsed = time.monotonic() - case_start

            per_case[tc.name] = case_result["score"]
            scores.append(case_result["score"])
            details[tc.name] = {
                **case_result,
                "elapsed": round(case_elapsed, 2),
            }

        overall = sum(scores) / len(scores) if scores else 0.0
        total_elapsed = time.monotonic() - total_start

        return EvalResult(
            benchmark=self.name,
            score=round(overall, 4),
            metrics=per_case,
            details={
                "breakdown": details,
                "total_elapsed": round(total_elapsed, 2),
                "num_cases": len(test_cases),
            },
        )
