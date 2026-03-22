"""Benchmark runner — orchestrates benchmark execution and result aggregation."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from semideus.core.errors import EvaluationError
from semideus.core.events import EventBus
from semideus.core.interfaces import Benchmark
from semideus.evaluation.types import AggregateResult

logger = logging.getLogger(__name__)

HarnessFactory = Callable[[], Any]


class BenchmarkRunner:
    """Orchestrates benchmark execution."""

    def __init__(
        self,
        harness_factory: HarnessFactory,
        event_bus: EventBus | None = None,
    ) -> None:
        self._harness_factory = harness_factory
        self._event_bus = event_bus or EventBus()
        self._benchmarks: dict[str, Benchmark] = {}

    def register(self, benchmark: Benchmark) -> None:
        """Register a benchmark for execution."""
        self._benchmarks[benchmark.name] = benchmark

    @property
    def benchmark_names(self) -> list[str]:
        return list(self._benchmarks.keys())

    async def run_all(self) -> AggregateResult:
        """Run all registered benchmarks sequentially."""
        return await self._run(list(self._benchmarks.keys()))

    async def run_by_name(self, names: list[str]) -> AggregateResult:
        """Run specific benchmarks by name."""
        for name in names:
            if name not in self._benchmarks:
                raise EvaluationError(
                    f"Benchmark '{name}' not registered. Available: {self.benchmark_names}"
                )
        return await self._run(names)

    async def run_parallel(self, names: list[str] | None = None) -> AggregateResult:
        """Run benchmarks in parallel."""
        target_names = names or list(self._benchmarks.keys())
        for name in target_names:
            if name not in self._benchmarks:
                raise EvaluationError(f"Benchmark '{name}' not registered.")

        start = time.monotonic()
        await self._event_bus.emit("evaluation.start", {"benchmarks": target_names})

        tasks = [self._run_single(name) for name in target_names]
        eval_results = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for name, result in zip(target_names, eval_results):
            if isinstance(result, Exception):
                logger.error("Benchmark '%s' failed: %s", name, result)
            else:
                results.append(result)

        elapsed = time.monotonic() - start
        overall = sum(r.score for r in results) / len(results) if results else 0.0

        aggregate = AggregateResult(
            results=results,
            overall_score=round(overall, 4),
            total_elapsed=round(elapsed, 2),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        await self._event_bus.emit(
            "evaluation.end",
            {"overall_score": aggregate.overall_score, "elapsed": aggregate.total_elapsed},
        )

        return aggregate

    async def _run(self, names: list[str]) -> AggregateResult:
        """Run benchmarks sequentially."""
        start = time.monotonic()
        await self._event_bus.emit("evaluation.start", {"benchmarks": names})

        results = []
        for name in names:
            try:
                result = await self._run_single(name)
                results.append(result)
            except Exception as e:
                logger.error("Benchmark '%s' failed: %s", name, e)

        elapsed = time.monotonic() - start
        overall = sum(r.score for r in results) / len(results) if results else 0.0

        aggregate = AggregateResult(
            results=results,
            overall_score=round(overall, 4),
            total_elapsed=round(elapsed, 2),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        await self._event_bus.emit(
            "evaluation.end",
            {"overall_score": aggregate.overall_score, "elapsed": aggregate.total_elapsed},
        )

        return aggregate

    async def _run_single(self, name: str):
        """Run a single benchmark."""
        benchmark = self._benchmarks[name]
        await self._event_bus.emit("benchmark.start", {"name": name})

        result = await benchmark.run()

        await self._event_bus.emit(
            "benchmark.end", {"name": name, "score": result.score}
        )
        return result

    def save_results(self, result: AggregateResult, path: Path) -> None:
        """Save aggregate results to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = result.model_dump()
        path.write_text(json.dumps(data, indent=2, default=str))
        logger.info("Results saved to %s", path)
