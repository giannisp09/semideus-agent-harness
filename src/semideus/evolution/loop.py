"""Main evolution loop orchestrator."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from semideus.core.config import EvolutionConfig, load_config
from semideus.core.errors import EvolutionError
from semideus.core.events import EventBus
from semideus.core.interfaces import LLMProvider
from semideus.core.types import EvalResult
from semideus.evaluation.runner import BenchmarkRunner
from semideus.evaluation.types import AggregateResult
from semideus.evolution.history import EvolutionHistory
from semideus.evolution.sandbox import WorktreeSandbox
from semideus.evolution.strategy import DefaultEvolutionStrategy

logger = logging.getLogger(__name__)


class EvolutionResult(BaseModel):
    """Summary returned after an evolution run."""

    baseline_score: float = 0.0
    final_score: float = 0.0
    iterations: int = 0
    accepted_count: int = 0
    history_path: str = ""


class EvolutionLoop:
    """Orchestrates the self-evolution feedback cycle.

    1. Run baseline benchmarks
    2. For each iteration:
       a. Analyze failures (LLM)
       b. Plan mutations (LLM)
       c. Apply mutations in sandbox
       d. Evaluate in sandbox
       e. Accept or reject
    3. Save history, return result
    """

    def __init__(
        self,
        provider: LLMProvider,
        config: EvolutionConfig,
        event_bus: EventBus | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self._provider = provider
        self._config = config
        self._event_bus = event_bus or EventBus()
        self._repo_root = repo_root or Path.cwd()

    async def run(
        self,
        harness_factory: Any,
        benchmark_names: list[str] | None = None,
        suite_path: str | None = None,
        max_iterations: int | None = None,
    ) -> EvolutionResult:
        """Execute the full evolution loop."""
        max_iter = max_iterations or self._config.max_iterations
        run_id = f"evo-{uuid.uuid4().hex[:8]}"
        history = EvolutionHistory(run_id, self._repo_root)

        logger.info("Starting self-evolution loop (max %d iterations)", max_iter)

        await self._event_bus.emit("evolution.start", {
            "run_id": run_id,
            "max_iterations": max_iter,
        })

        # --- Step 1: Baseline evaluation ---
        logger.info("Running baseline evaluation...")
        baseline = await self._run_baseline(harness_factory, benchmark_names, suite_path)
        baseline_score = baseline.overall_score
        history.record_baseline(baseline_score)

        logger.info("Baseline score: %.4f", baseline_score)

        # Collect eval results for analysis
        current_best_score = baseline_score
        eval_results = baseline.results  # list[EvalResult]

        # --- Step 2: Iteration loop ---
        for iteration in range(1, max_iter + 1):
            await self._event_bus.emit("evolution.iteration.start", {
                "run_id": run_id,
                "iteration": iteration,
                "current_best": current_best_score,
            })

            logger.info("=== Evolution iteration %d/%d ===", iteration, max_iter)

            try:
                iter_result = await self._run_iteration(
                    iteration=iteration,
                    eval_results=eval_results,
                    harness_factory=harness_factory,
                    benchmark_names=benchmark_names,
                    suite_path=suite_path,
                )
            except Exception as e:
                logger.error("Iteration %d failed: %s", iteration, e)
                history.record_iteration(
                    iteration=iteration,
                    analysis={},
                    mutations=[],
                    before_score=current_best_score,
                    after_score=current_best_score,
                    accepted=False,
                )
                await self._event_bus.emit("evolution.iteration.end", {
                    "run_id": run_id,
                    "iteration": iteration,
                    "accepted": False,
                    "error": str(e),
                })
                continue

            accepted = iter_result["accepted"]
            after_score = iter_result["after_score"]

            history.record_iteration(
                iteration=iteration,
                analysis=iter_result.get("analysis", {}),
                mutations=iter_result.get("mutations", []),
                before_score=current_best_score,
                after_score=after_score,
                accepted=accepted,
            )

            if accepted:
                current_best_score = after_score
                eval_results = iter_result.get("eval_results", eval_results)

            await self._event_bus.emit("evolution.iteration.end", {
                "run_id": run_id,
                "iteration": iteration,
                "accepted": accepted,
                "before_score": iter_result["before_score"],
                "after_score": after_score,
            })

        # --- Step 3: Finalize ---
        history_path = history.save()

        await self._event_bus.emit("evolution.end", {
            "run_id": run_id,
            "baseline_score": baseline_score,
            "final_score": current_best_score,
            "iterations": max_iter,
            "accepted_count": history.accepted_count,
        })

        return EvolutionResult(
            baseline_score=baseline_score,
            final_score=current_best_score,
            iterations=max_iter,
            accepted_count=history.accepted_count,
            history_path=str(history_path),
        )

    async def _run_baseline(
        self,
        harness_factory: Any,
        benchmark_names: list[str] | None,
        suite_path: str | None,
    ) -> AggregateResult:
        """Run baseline benchmarks without any mutations."""
        if suite_path:
            from semideus.evaluation.loader import load_suite
            from semideus.evaluation.task_completion import TaskCompletionBenchmark
            from semideus.evaluation.skill_adherence import SkillAdherenceBenchmark

            suite = load_suite(Path(suite_path))
            runner = BenchmarkRunner(harness_factory=harness_factory)

            if suite.test_cases:
                runner.register(TaskCompletionBenchmark(
                    harness_factory=harness_factory, suite=suite,
                ))
            if suite.skill_test_cases:
                runner.register(SkillAdherenceBenchmark(
                    harness_factory=harness_factory, suite=suite,
                ))
        else:
            import semideus.evaluation  # noqa: F401
            from semideus.core.registry import registry
            from semideus.core.types import ComponentType

            runner = BenchmarkRunner(harness_factory=harness_factory)
            names = benchmark_names or registry.list(ComponentType.BENCHMARK)
            for name in names:
                bench_cls = registry.get(ComponentType.BENCHMARK, name)
                bench = bench_cls(harness_factory=harness_factory)
                runner.register(bench)

        if not runner.benchmark_names:
            raise EvolutionError("No benchmarks to run for baseline evaluation")

        return await runner.run_all()

    async def _run_iteration(
        self,
        iteration: int,
        eval_results: list[EvalResult],
        harness_factory: Any,
        benchmark_names: list[str] | None,
        suite_path: str | None,
    ) -> dict[str, Any]:
        """Execute a single evolution iteration."""
        # Create strategy (fresh per iteration so sandbox is scoped)
        async with WorktreeSandbox(self._repo_root) as sandbox:
            strategy = DefaultEvolutionStrategy(
                provider=self._provider,
                config=self._config,
                sandbox=sandbox,
                repo_root=sandbox.worktree_path,
            )

            # a. Analyze
            analysis = await strategy.analyze(eval_results)

            # b. Plan
            plan = await strategy.plan(analysis)

            # c. Apply mutations in sandbox
            change_desc = await strategy.modify(plan)
            if change_desc.get("applied", 0) == 0:
                logger.warning("No mutations applied in iteration %d", iteration)
                return {
                    "accepted": False,
                    "analysis": analysis,
                    "mutations": [],
                    "before_score": eval_results[0].score if eval_results else 0.0,
                    "after_score": eval_results[0].score if eval_results else 0.0,
                }

            # d. Evaluate in sandbox
            sandbox_result = await sandbox.run_eval(
                harness_factory=harness_factory,
                benchmark_names=benchmark_names,
                suite_path=suite_path,
            )

            # Build before/after EvalResults for acceptance check
            before_score = sum(r.score for r in eval_results) / len(eval_results) if eval_results else 0.0
            after_score = sandbox_result.overall_score

            before_eval = EvalResult(benchmark="aggregate", score=before_score)
            after_eval = EvalResult(benchmark="aggregate", score=after_score)

            # e. Accept or reject
            accepted = await strategy.should_accept(before_eval, after_eval)

            if accepted:
                copied = sandbox.accept(self._repo_root)
                logger.info("Accepted iteration %d: copied %d files", iteration, len(copied))

            return {
                "accepted": accepted,
                "analysis": analysis,
                "mutations": change_desc.get("mutations", []),
                "before_score": before_score,
                "after_score": after_score,
                "eval_results": sandbox_result.results,
            }
