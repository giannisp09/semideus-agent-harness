"""Task completion benchmark — measures whether the agent completes tasks correctly."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Callable

from semideus.core.interfaces import Benchmark
from semideus.core.registry import registry
from semideus.core.types import ComponentType, EvalResult, SessionStatus
from semideus.evaluation.types import BenchmarkSuite, TestCase

logger = logging.getLogger(__name__)

# Type alias for the harness factory
HarnessFactory = Callable[[], Any]  # Returns Harness


@registry.register(ComponentType.BENCHMARK, "task_completion")
class TaskCompletionBenchmark(Benchmark):
    """Evaluates whether the agent can complete tasks and produce expected output."""

    def __init__(
        self,
        harness_factory: HarnessFactory | None = None,
        suite: BenchmarkSuite | None = None,
    ) -> None:
        self._harness_factory = harness_factory
        self._suite = suite

    @property
    def name(self) -> str:
        return "task_completion"

    def _score_case(
        self, output: str, test_case: TestCase, step_count: int, status: SessionStatus
    ) -> dict[str, float]:
        """Score a single test case."""
        # Completion: 1.0 if completed without hitting max steps
        completion = 1.0 if (status == SessionStatus.COMPLETED and step_count < test_case.max_steps) else 0.0

        # Pattern match: fraction of expected patterns found in output
        if test_case.expected_patterns:
            matches = sum(
                1 for p in test_case.expected_patterns if re.search(p, output, re.IGNORECASE)
            )
            pattern_match = matches / len(test_case.expected_patterns)
        else:
            pattern_match = 1.0  # No patterns to check = pass

        # Efficiency: how quickly the agent finished relative to max steps
        efficiency = max(0.0, min(1.0, 1.0 - step_count / test_case.max_steps))

        # Weighted score
        score = 0.5 * completion + 0.35 * pattern_match + 0.15 * efficiency

        return {
            "completion": completion,
            "pattern_match": pattern_match,
            "efficiency": efficiency,
            "score": score,
        }

    async def run(self, agent: Any = None) -> EvalResult:
        """Run the benchmark. Uses harness_factory to create isolated harness instances."""
        if not self._harness_factory:
            raise ValueError("harness_factory is required for TaskCompletionBenchmark")

        test_cases = self._suite.test_cases if self._suite else []
        if not test_cases:
            return EvalResult(
                benchmark=self.name,
                score=0.0,
                metrics={},
                details={"error": "No test cases provided"},
            )

        per_case: dict[str, float] = {}
        details: dict[str, Any] = {}
        scores: list[float] = []
        total_start = time.monotonic()

        for tc in test_cases:
            harness = self._harness_factory()
            case_start = time.monotonic()
            try:
                output = await asyncio.wait_for(
                    harness.run(tc.task),
                    timeout=tc.timeout_seconds,
                )
                last_state = harness.last_agent_state
                step_count = last_state.step_count if last_state else 0
                status = last_state.status if last_state else SessionStatus.COMPLETED
            except asyncio.TimeoutError:
                output = ""
                step_count = tc.max_steps
                status = SessionStatus.FAILED
            except Exception as e:
                logger.error("Test case '%s' failed: %s", tc.name, e)
                output = ""
                step_count = tc.max_steps
                status = SessionStatus.FAILED
            finally:
                try:
                    await harness.close()
                except Exception:
                    pass

            case_scores = self._score_case(output, tc, step_count, status)
            case_elapsed = time.monotonic() - case_start

            per_case[tc.name] = case_scores["score"]
            scores.append(case_scores["score"])
            details[tc.name] = {
                **case_scores,
                "elapsed": round(case_elapsed, 2),
                "steps": step_count,
                "status": status.value,
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
