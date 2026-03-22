"""MBPP benchmark adapter — Mostly Basic Python Problems dataset."""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import sys
import time
from typing import Any, Callable

from semideus.core.errors import EvaluationError
from semideus.core.interfaces import Benchmark
from semideus.core.registry import registry
from semideus.core.types import ComponentType, EvalResult

logger = logging.getLogger(__name__)

HarnessFactory = Callable[[], Any]


@registry.register(ComponentType.BENCHMARK, "mbpp")
class MBPPBenchmark(Benchmark):
    """Evaluate agent code-generation ability using Mostly Basic Python Problems (MBPP).

    Loads the ``mbpp`` dataset (sanitized split), asks the agent to
    complete each function, then runs the provided asserts in a subprocess
    to compute **pass@1**.
    """

    def __init__(
        self,
        harness_factory: HarnessFactory | None = None,
        max_tasks: int = 10,  # 0 = all
        timeout_per_task: float = 120.0,
        test_timeout: int = 10,
    ) -> None:
        self._harness_factory = harness_factory
        self._max_tasks = max_tasks
        self._timeout_per_task = timeout_per_task
        self._test_timeout = test_timeout

    @property
    def name(self) -> str:
        return "mbpp"

    # ------------------------------------------------------------------
    # Dataset loading
    # ------------------------------------------------------------------

    def _load_dataset(self) -> list[dict[str, Any]]:
        try:
            from datasets import load_dataset  # type: ignore[import-untyped]
        except ImportError:
            raise EvaluationError(
                "The 'datasets' package is not installed. "
                "Install it with: uv sync --extra eval"
            )

        ds = load_dataset("mbpp", "sanitized", split="test")
        problems: list[dict[str, Any]] = [dict(row) for row in ds]

        if self._max_tasks > 0:
            problems = problems[: self._max_tasks]

        return problems

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(problem: dict[str, Any]) -> tuple[str, str | None]:
        task_prompt = problem["prompt"]
        tests = problem.get("test_list", [])
        
        func_name = None
        if tests:
            m = re.search(r"assert\s+([a-zA-Z0-9_]+)\(", tests[0])
            if m:
                func_name = m.group(1)

        prompt_str = (
            "Write a complete Python function that solves the following problem:\n\n"
            f"{task_prompt}\n\n"
        )
        if func_name:
            prompt_str += f"IMPORTANT: Name your main function `{func_name}`.\n\n"
        
        prompt_str += (
            "Return ONLY the complete function implementation in a single python code block."
        )
        return prompt_str, func_name

    # ------------------------------------------------------------------
    # Code extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_code(output: str) -> str:
        """Extract the function implementation from agent output."""
        m = re.search(r"```(?:python|py)\s*\n(.*?)```", output, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()

        m = re.search(r"```\s*\n(.*?)```", output, re.DOTALL)
        if m:
            return m.group(1).strip()

        # If no markdown blocks, return everything safely (might fail tests but at least avoids empty string)
        return output.strip()

    # ------------------------------------------------------------------
    # Test execution
    # ------------------------------------------------------------------

    def _run_test(self, problem: dict[str, Any], code: str) -> tuple[bool, str]:
        """Run the MBPP test harness for a single problem."""
        full_program = ""
        
        for imp in problem.get("test_imports", []):
            full_program += f"{imp}\n"
            
        full_program += f"{code}\n\n"
        
        for t in problem.get("test_list", []):
            full_program += f"{t}\n"

        try:
            result = subprocess.run(
                [sys.executable, "-c", full_program],
                capture_output=True,
                text=True,
                timeout=self._test_timeout,
            )
            if result.returncode == 0:
                return True, ""
            return False, (result.stderr or result.stdout)[:500]
        except subprocess.TimeoutExpired:
            return False, "test timed out"
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    async def run(self, agent: Any = None) -> EvalResult:
        """Run MBPP benchmark and return pass@1 score."""
        if not self._harness_factory:
            raise ValueError("harness_factory is required for MBPPBenchmark")

        problems = self._load_dataset()
        total = len(problems)
        passed_count = 0
        per_problem: dict[str, Any] = {}
        total_start = time.monotonic()

        for i, problem in enumerate(problems):
            task_id: str = str(problem.get("task_id", f"mbpp/{i}"))
            prompt_text, _ = self._build_prompt(problem)

            logger.info("MBPP [%d/%d] %s", i + 1, total, task_id)

            harness = self._harness_factory()
            try:
                output = await asyncio.wait_for(
                    harness.run(prompt_text),
                    timeout=self._timeout_per_task,
                )
                code = self._extract_code(output)
                passed, error = self._run_test(problem, code)
            except asyncio.TimeoutError:
                passed, error, code = False, "agent timed out", ""
            except Exception as e:
                logger.error("MBPP problem '%s' failed: %s", task_id, e)
                passed, error, code = False, str(e), ""
            finally:
                try:
                    await harness.close()
                except Exception:
                    pass

            if passed:
                passed_count += 1

            per_problem[task_id] = {
                "passed": passed,
                "error": error if not passed else "",
                "code_preview": code[:300] if code else "",
            }

            status = "[PASS]" if passed else "[FAIL]"
            logger.info("  %s %s", status, task_id)

        pass_at_1 = passed_count / total if total > 0 else 0.0
        total_elapsed = time.monotonic() - total_start

        return EvalResult(
            benchmark="mbpp",
            score=round(pass_at_1, 4),
            metrics={
                "pass@1": round(pass_at_1, 4),
                "passed": float(passed_count),
                "total": float(total),
            },
            details={
                "breakdown": per_problem,
                "total_elapsed": round(total_elapsed, 2),
                "num_problems": total,
            },
        )
