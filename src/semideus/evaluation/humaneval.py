"""HumanEval benchmark adapter — OpenAI's 164-problem Python coding benchmark."""

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


@registry.register(ComponentType.BENCHMARK, "humaneval")
class HumanEvalBenchmark(Benchmark):
    """Evaluate agent code-generation ability using OpenAI HumanEval.

    Loads the ``openai_humaneval`` dataset (164 problems), asks the agent to
    complete each function, then runs the provided unit tests in a subprocess
    to compute **pass@1**.
    """

    def __init__(
        self,
        harness_factory: HarnessFactory | None = None,
        max_problems: int = 10,
        timeout_per_problem: float = 120.0,
        test_timeout: int = 10,
    ) -> None:
        self._harness_factory = harness_factory
        self._max_problems = max_problems  # 0 = all 164
        self._timeout_per_problem = timeout_per_problem
        self._test_timeout = test_timeout

    @property
    def name(self) -> str:
        return "humaneval"

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

        ds = load_dataset("openai/openai_humaneval", split="test")
        problems: list[dict[str, Any]] = [dict(row) for row in ds]

        if self._max_problems > 0:
            problems = problems[: self._max_problems]

        return problems

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(problem: dict[str, Any]) -> str:
        return (
            "Complete the following Python function. "
            "Return ONLY the complete function implementation "
            "in a single python code block.\n\n"
            f"{problem['prompt']}"
        )

    # ------------------------------------------------------------------
    # Code extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_code(output: str, prompt: str, entry_point: str) -> str:
        """Extract the function implementation from agent output."""

        # Strategy 1: ```python ... ``` block
        m = re.search(r"```python\s*\n(.*?)```", output, re.DOTALL)
        if m:
            return m.group(1).strip()

        # Strategy 2: ``` ... ``` block (any language)
        m = re.search(r"```\s*\n(.*?)```", output, re.DOTALL)
        if m:
            return m.group(1).strip()

        # Strategy 3: find the function definition in raw text
        m = re.search(
            rf"(def {re.escape(entry_point)}\s*\(.*$(?:\n(?:[ \t].*|$))*)",
            output,
            re.MULTILINE,
        )
        if m:
            return m.group(1).strip()

        # Fallback: prepend the original prompt to the raw output so the
        # function signature is present even if the agent only returned the body.
        return prompt + output

    # ------------------------------------------------------------------
    # Test execution
    # ------------------------------------------------------------------

    def _run_test(self, problem: dict[str, Any], code: str) -> tuple[bool, str]:
        """Run the HumanEval test harness for a single problem.

        Returns ``(passed, error_message)``.
        """
        test_code = problem["test"]
        entry_point = problem["entry_point"]

        full_program = f"{code}\n\n{test_code}\n\ncheck({entry_point})\n"

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
        """Run HumanEval benchmark and return pass@1 score."""
        if not self._harness_factory:
            raise ValueError("harness_factory is required for HumanEvalBenchmark")

        problems = self._load_dataset()
        total = len(problems)
        passed_count = 0
        per_problem: dict[str, Any] = {}
        total_start = time.monotonic()

        for i, problem in enumerate(problems):
            task_id: str = problem.get("task_id", f"HumanEval/{i}")
            entry_point: str = problem["entry_point"]
            prompt_text = self._build_prompt(problem)

            logger.info("HumanEval [%d/%d] %s", i + 1, total, task_id)

            harness = self._harness_factory()
            try:
                output = await asyncio.wait_for(
                    harness.run(prompt_text),
                    timeout=self._timeout_per_problem,
                )
                code = self._extract_code(output, problem["prompt"], entry_point)
                passed, error = self._run_test(problem, code)
            except asyncio.TimeoutError:
                passed, error, code = False, "agent timed out", ""
            except Exception as e:
                logger.error("HumanEval problem '%s' failed: %s", task_id, e)
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
            benchmark="humaneval",
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
