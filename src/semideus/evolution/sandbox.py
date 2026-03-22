"""Git worktree isolation for safe mutation testing."""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from semideus.core.errors import EvolutionError
from semideus.evaluation.runner import BenchmarkRunner
from semideus.evaluation.types import AggregateResult

logger = logging.getLogger(__name__)


async def _run_git(*args: str, cwd: Path | None = None) -> str:
    """Run a git command asynchronously, returning stdout."""
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise EvolutionError(
            f"git {' '.join(args)} failed (rc={proc.returncode}): {stderr.decode()}"
        )
    return stdout.decode().strip()


class WorktreeSandbox:
    """Async context manager that creates an isolated git worktree for mutation testing.

    Usage::

        async with WorktreeSandbox(repo_root) as sandbox:
            sandbox.apply_mutations(mutations)
            result = await sandbox.run_eval(harness_factory)
            if good:
                sandbox.accept(repo_root)
    """

    def __init__(self, repo_root: Path | None = None) -> None:
        self._repo_root = repo_root or Path.cwd()
        self._worktree_path: Path | None = None
        self._branch_name: str = ""
        self._tmpdir: str = ""

    @property
    def worktree_path(self) -> Path:
        if self._worktree_path is None:
            raise EvolutionError("Sandbox not entered — use 'async with'")
        return self._worktree_path

    async def __aenter__(self) -> WorktreeSandbox:
        self._branch_name = f"evolution-sandbox-{uuid.uuid4().hex[:8]}"
        self._tmpdir = tempfile.mkdtemp(prefix="semideus-evo-")
        wt_path = Path(self._tmpdir) / "worktree"

        try:
            await _run_git(
                "worktree", "add", "-b", self._branch_name, str(wt_path),
                cwd=self._repo_root,
            )
        except EvolutionError:
            # Fallback: if the branch already exists, just add without -b
            await _run_git(
                "worktree", "add", str(wt_path), "HEAD",
                cwd=self._repo_root,
            )

        self._worktree_path = wt_path
        logger.info("Created sandbox worktree at %s (branch %s)", wt_path, self._branch_name)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        if self._worktree_path and self._worktree_path.exists():
            try:
                await _run_git(
                    "worktree", "remove", "--force", str(self._worktree_path),
                    cwd=self._repo_root,
                )
            except EvolutionError as e:
                logger.warning("Failed to remove worktree: %s", e)
                # Fallback: manual cleanup
                shutil.rmtree(self._worktree_path, ignore_errors=True)

        if self._branch_name:
            try:
                await _run_git(
                    "branch", "-D", self._branch_name,
                    cwd=self._repo_root,
                )
            except EvolutionError:
                pass  # Branch may not exist if worktree add failed

        # Clean up tmpdir
        if self._tmpdir:
            shutil.rmtree(self._tmpdir, ignore_errors=True)

        logger.info("Cleaned up sandbox worktree")

    def apply_mutations(self, mutations: list[Any]) -> None:
        """Apply a list of Mutation objects to the worktree."""
        for mutation in mutations:
            mutation.apply(self.worktree_path)
        logger.info("Applied %d mutations to sandbox", len(mutations))

    async def run_eval(
        self,
        harness_factory: Any,
        benchmark_names: list[str] | None = None,
        suite_path: str | None = None,
    ) -> AggregateResult:
        """Run evaluation benchmarks inside the sandbox.

        Creates a Harness from config pointed at the worktree's config and
        skills directory, then runs BenchmarkRunner in-process.
        """
        from semideus.core.config import load_config
        from semideus.harness.harness import Harness

        wt = self.worktree_path
        config_path = wt / "configs" / "default.yaml"
        skills_dir = wt / "skills"

        # Build overrides pointing to worktree paths
        overrides: dict[str, Any] = {}
        if skills_dir.exists():
            overrides["skills"] = {"dir": str(skills_dir)}

        def sandbox_harness_factory(**kw: Any) -> Harness:
            merged = {**overrides, **kw}
            return harness_factory(base_dir=wt, **merged)

        # Load suite if provided
        if suite_path:
            from semideus.evaluation.loader import load_suite
            from semideus.evaluation.task_completion import TaskCompletionBenchmark
            from semideus.evaluation.skill_adherence import SkillAdherenceBenchmark

            suite = load_suite(Path(suite_path))
            runner = BenchmarkRunner(harness_factory=sandbox_harness_factory)

            if suite.test_cases:
                runner.register(TaskCompletionBenchmark(
                    harness_factory=sandbox_harness_factory, suite=suite,
                ))
            if suite.skill_test_cases:
                runner.register(SkillAdherenceBenchmark(
                    harness_factory=sandbox_harness_factory, suite=suite,
                ))
        else:
            # Use benchmark_names from registry
            import semideus.evaluation  # noqa: F401
            from semideus.core.registry import registry
            from semideus.core.types import ComponentType

            runner = BenchmarkRunner(harness_factory=sandbox_harness_factory)
            names = benchmark_names or registry.list(ComponentType.BENCHMARK)
            for name in names:
                bench_cls = registry.get(ComponentType.BENCHMARK, name)
                bench = bench_cls(harness_factory=sandbox_harness_factory)
                runner.register(bench)

        return await runner.run_all()

    def accept(self, target_dir: Path) -> list[Path]:
        """Copy changed files from the sandbox back to the main repo.

        Copies skill YAMLs and config files. Returns list of copied paths.
        """
        copied: list[Path] = []
        wt = self.worktree_path

        # Copy skill YAML files
        wt_skills = wt / "skills"
        target_skills = target_dir / "skills"
        if wt_skills.is_dir():
            target_skills.mkdir(parents=True, exist_ok=True)
            for yaml_file in wt_skills.glob("*.yaml"):
                dest = target_skills / yaml_file.name
                shutil.copy2(yaml_file, dest)
                copied.append(dest)
                logger.info("Accepted: %s -> %s", yaml_file, dest)

        # Copy config if modified
        wt_config = wt / "configs" / "default.yaml"
        target_config = target_dir / "configs" / "default.yaml"
        if wt_config.exists():
            target_config.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wt_config, target_config)
            copied.append(target_config)
            logger.info("Accepted config: %s", target_config)

        return copied
