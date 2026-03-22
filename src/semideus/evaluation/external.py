"""External benchmark adapter for PrimeIntellect / verifiers environments."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from semideus.core.errors import EvaluationError
from semideus.core.interfaces import Benchmark
from semideus.core.registry import registry
from semideus.core.types import ComponentType, EvalResult

logger = logging.getLogger(__name__)

HarnessFactory = Callable[[], Any]


@registry.register(ComponentType.BENCHMARK, "external")
class ExternalBenchmark(Benchmark):
    """Adapter for external benchmark environments (e.g., PrimeIntellect verifiers).

    Loads an environment from the `verifiers` package, iterates its dataset,
    runs the agent on each task, and scores via the environment's rubric.
    """

    def __init__(
        self,
        env_name: str = "",
        harness_factory: HarnessFactory | None = None,
        max_tasks: int = 0,
    ) -> None:
        self._env_name = env_name
        self._harness_factory = harness_factory
        self._max_tasks = max_tasks  # 0 = all tasks

    @property
    def name(self) -> str:
        return f"external:{self._env_name}" if self._env_name else "external"

    async def run(self, agent: Any = None) -> EvalResult:
        """Run the external benchmark."""
        if not self._harness_factory:
            raise ValueError("harness_factory is required for ExternalBenchmark")
        if not self._env_name:
            raise ValueError("env_name is required for ExternalBenchmark")

        try:
            from verifiers import load_environment  # type: ignore[import-untyped]
        except ImportError:
            raise EvaluationError(
                "The 'verifiers' package is not installed. "
                "Install it with: pip install verifiers"
            )

        env = load_environment(self._env_name)
        dataset = env.get_dataset()

        if self._max_tasks > 0:
            dataset = dataset[: self._max_tasks]

        scores: list[float] = []
        per_task: dict[str, Any] = {}
        total_start = time.monotonic()

        for i, task_data in enumerate(dataset):
            task_name = task_data.get("name", f"task_{i}")
            task_prompt = task_data.get("prompt", task_data.get("question", ""))

            harness = self._harness_factory()
            try:
                output = await asyncio.wait_for(
                    harness.run(task_prompt),
                    timeout=300.0,
                )
                score = env.score(task_data, output)
                scores.append(float(score))
                per_task[task_name] = {
                    "score": float(score),
                    "output_preview": output[:200],
                }
            except asyncio.TimeoutError:
                scores.append(0.0)
                per_task[task_name] = {"score": 0.0, "error": "timeout"}
            except Exception as e:
                logger.error("External task '%s' failed: %s", task_name, e)
                scores.append(0.0)
                per_task[task_name] = {"score": 0.0, "error": str(e)}
            finally:
                try:
                    await harness.close()
                except Exception:
                    pass

        overall = sum(scores) / len(scores) if scores else 0.0
        total_elapsed = time.monotonic() - total_start

        return EvalResult(
            benchmark=self.name,
            score=round(overall, 4),
            metrics={k: v["score"] for k, v in per_task.items()},
            details={
                "env_name": self._env_name,
                "breakdown": per_task,
                "total_elapsed": round(total_elapsed, 2),
                "num_tasks": len(dataset),
            },
        )
