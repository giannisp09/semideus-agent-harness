"""CLI entry point using Typer."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="semideus",
    help="Semideus Agentic Harness — a modular, self-evolving agentic framework.",
    no_args_is_help=True,
)
console = Console()


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@app.command()
def run(
    task: str = typer.Argument(..., help="The task to give the agent."),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config YAML."),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Provider name override."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model name override."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Run the agent on a task."""
    _setup_logging(verbose)

    overrides = {}
    if provider:
        overrides.setdefault("provider", {})["name"] = provider
    if model:
        overrides.setdefault("provider", {})["model"] = model

    from semideus.harness.harness import Harness

    try:
        harness = Harness.from_config(config_path=config, overrides=overrides or None)
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1)

    async def _run() -> str:
        try:
            result = await harness.run(task)
            return result
        finally:
            await harness.close()

    try:
        result = asyncio.run(_run())
        console.print()
        console.print(result)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        raise typer.Exit(130)
    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def providers(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """List registered providers."""
    _setup_logging(verbose)

    # Import to trigger registration
    import semideus.providers  # noqa: F401
    from semideus.core.registry import registry
    from semideus.core.types import ComponentType

    names = registry.list(ComponentType.PROVIDER)
    table = Table(title="Registered Providers")
    table.add_column("Name", style="cyan")
    for name in sorted(names):
        table.add_row(name)
    console.print(table)


@app.command()
def components(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """List all registered components."""
    _setup_logging(verbose)

    import semideus.providers  # noqa: F401
    import semideus.memory.file_store  # noqa: F401
    import semideus.skills.builtin.debug  # noqa: F401
    import semideus.skills.builtin.code_review  # noqa: F401
    import semideus.skills.builtin.summarize  # noqa: F401
    import semideus.skills.builtin.fix  # noqa: F401
    try:
        import semideus.memory.vector_store  # noqa: F401
    except ImportError:
        pass
    import semideus.evaluation  # noqa: F401
    import semideus.evolution  # noqa: F401
    from semideus.core.registry import registry

    all_components = registry.list_all()
    table = Table(title="Registered Components")
    table.add_column("Type", style="cyan")
    table.add_column("Names", style="green")
    for ctype, names in sorted(all_components.items()):
        table.add_row(ctype, ", ".join(sorted(names)))
    console.print(table)


@app.command()
def init(
    path: str = typer.Argument(".", help="Directory to initialize."),
) -> None:
    """Initialize a new Semideus project with default config."""
    target = Path(path)
    config_dir = target / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)

    default_config = config_dir / "default.yaml"
    if default_config.exists():
        console.print("[yellow]configs/default.yaml already exists, skipping.[/yellow]")
    else:
        # Copy from package defaults
        src = Path(__file__).parent.parent.parent / "configs" / "default.yaml"
        if src.exists():
            default_config.write_text(src.read_text())
        else:
            default_config.write_text(
                "provider:\n  name: anthropic\n  model: claude-sonnet-4-20250514\n  api_key_env: ANTHROPIC_API_KEY\n"
            )
        console.print(f"[green]Created[/green] {default_config}")

    # Create plugin/skills dirs
    for d in ["plugins", "skills"]:
        (target / d).mkdir(exist_ok=True)
        console.print(f"[green]Created[/green] {target / d}/")

    console.print("\n[bold green]Semideus project initialized![/bold green]")


@app.command(name="eval")
def eval_cmd(
    suite: Optional[str] = typer.Option(None, "--suite", "-s", help="Path to a benchmark suite YAML."),
    benchmark: Optional[str] = typer.Option(None, "--benchmark", "-b", help="Run a specific benchmark by name."),
    max_tasks: int = typer.Option(0, "--max-tasks", help="Limit the number of tasks/problems (0 = all)."),
    max_steps: int = typer.Option(0, "--max-steps", help="Max agent loop iterations per task (0 = use default)."),
    all_suites: bool = typer.Option(False, "--all", help="Load all suites from the configured suites directory."),
    parallel: bool = typer.Option(False, "--parallel", help="Run benchmarks in parallel."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save results to a JSON file."),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Run evaluation benchmarks against the agent."""
    _setup_logging(verbose)

    from semideus.core.config import load_config
    from semideus.harness.harness import Harness
    from semideus.evaluation.loader import load_suite, load_suites_from_directory
    from semideus.evaluation.runner import BenchmarkRunner
    from semideus.evaluation.task_completion import TaskCompletionBenchmark
    from semideus.evaluation.skill_adherence import SkillAdherenceBenchmark
    from semideus.evaluation.types import BenchmarkSuite

    try:
        harness_config = load_config(config_path=config)
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1)

    # Load suites
    suites: list[BenchmarkSuite] = []
    if suite:
        suites.append(load_suite(Path(suite)))
    elif all_suites:
        suites_dir = Path(harness_config.evaluation.suites_dir)
        suites = load_suites_from_directory(suites_dir)
        if not suites:
            console.print(f"[yellow]No suites found in {suites_dir}[/yellow]")
            raise typer.Exit(1)
    elif not benchmark:
        console.print("[yellow]Specify --suite, --all, or --benchmark to run evaluations.[/yellow]")
        raise typer.Exit(1)

    def harness_factory(base_dir: Path | None = None, **overrides_kw: Any) -> Harness:
        return Harness.from_config(config_path=config, overrides=overrides_kw or None, base_dir=base_dir)

    runner = BenchmarkRunner(harness_factory=harness_factory)

    # Standalone benchmark mode: look up registered benchmark by name
    if benchmark and not suites:
        import semideus.evaluation  # noqa: F401
        from semideus.core.registry import registry as _reg
        from semideus.core.types import ComponentType
        bench_cls = _reg.get(ComponentType.BENCHMARK, benchmark)
        if bench_cls is None:
            console.print(f"[red]Unknown benchmark:[/red] {benchmark}")
            console.print("Use [cyan]semideus eval-list[/cyan] to see available benchmarks.")
            raise typer.Exit(1)
        # Build kwargs — HumanEvalBenchmark uses max_problems, others use max_tasks
        bench_kwargs: dict[str, Any] = {"harness_factory": harness_factory}
        if max_tasks > 0:
            param_name = "max_problems" if "humaneval" in benchmark else "max_tasks"
            bench_kwargs[param_name] = max_tasks
        if max_steps > 0:
            bench_kwargs["max_agent_steps"] = max_steps
        bench_instance = bench_cls(**bench_kwargs)
        runner.register(bench_instance)
    elif suites:
        # Merge all suites
        merged = BenchmarkSuite(
            name="merged",
            test_cases=[tc for s in suites for tc in s.test_cases],
            skill_test_cases=[sc for s in suites for sc in s.skill_test_cases],
        )

        # Register benchmarks based on available test cases and filter
        if merged.test_cases and (not benchmark or benchmark == "task_completion"):
            runner.register(TaskCompletionBenchmark(harness_factory=harness_factory, suite=merged))
        if merged.skill_test_cases and (not benchmark or benchmark == "skill_adherence"):
            runner.register(SkillAdherenceBenchmark(harness_factory=harness_factory, suite=merged))

    if not runner.benchmark_names:
        console.print("[yellow]No matching benchmarks to run.[/yellow]")
        raise typer.Exit(1)

    console.print(f"[bold]Running benchmarks:[/bold] {', '.join(runner.benchmark_names)}")

    async def _run():
        if parallel:
            return await runner.run_parallel()
        return await runner.run_all()

    try:
        result = asyncio.run(_run())
    except Exception as e:
        console.print(f"\n[red]Evaluation error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)

    # Display results
    table = Table(title="Evaluation Results")
    table.add_column("Benchmark", style="cyan")
    table.add_column("Score", style="green")
    table.add_column("Details", style="dim")
    for r in result.results:
        table.add_row(
            r.benchmark,
            f"{r.score:.4f}",
            f"{len(r.metrics)} cases",
        )
    table.add_row("", "", "")
    table.add_row("[bold]Overall[/bold]", f"[bold]{result.overall_score:.4f}[/bold]", f"{result.total_elapsed:.1f}s")
    console.print(table)

    # Save results
    output_path = Path(output) if output else Path(harness_config.evaluation.output_dir) / "latest.json"
    runner.save_results(result, output_path)
    console.print(f"\nResults saved to [cyan]{output_path}[/cyan]")


@app.command()
def evolve(
    suite: Optional[str] = typer.Option(None, "--suite", "-s", help="Path to a benchmark suite YAML."),
    benchmark: Optional[str] = typer.Option(None, "--benchmark", "-b", help="Run a specific benchmark by name."),
    max_iterations: int = typer.Option(3, "--max-iterations", "-n", help="Maximum evolution iterations."),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Path to config YAML."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
) -> None:
    """Run the self-evolution loop to improve agent performance."""
    _setup_logging(verbose)

    from semideus.core.config import load_config
    from semideus.core.registry import registry as _reg
    from semideus.core.types import ComponentType
    from semideus.harness.harness import Harness
    from semideus.evolution.loop import EvolutionLoop

    # Ensure evolution strategy is registered
    import semideus.evolution  # noqa: F401

    try:
        harness_config = load_config(config_path=config)
    except Exception as e:
        console.print(f"[red]Configuration error:[/red] {e}")
        raise typer.Exit(1)

    def harness_factory(base_dir: Path | None = None, **overrides_kw: Any) -> Harness:
        return Harness.from_config(config_path=config, overrides=overrides_kw or None, base_dir=base_dir)

    # Ensure provider is available
    import semideus.providers  # noqa: F401

    provider_cls = _reg.get(ComponentType.PROVIDER, harness_config.provider.name)
    provider = provider_cls(harness_config.provider)

    benchmark_names = [benchmark] if benchmark else None

    loop = EvolutionLoop(
        provider=provider,
        config=harness_config.evolution,
        repo_root=Path.cwd(),
    )

    console.print(f"[bold]Starting self-evolution loop[/bold] (max {max_iterations} iterations)")
    if suite:
        console.print(f"  Suite: {suite}")
    if benchmark:
        console.print(f"  Benchmark: {benchmark}")

    async def _run():
        try:
            return await loop.run(
                harness_factory=harness_factory,
                benchmark_names=benchmark_names,
                suite_path=suite,
                max_iterations=max_iterations,
            )
        finally:
            await provider.close()

    try:
        result = asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        raise typer.Exit(130)
    except Exception as e:
        console.print(f"\n[red]Evolution error:[/red] {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)

    # Display results
    table = Table(title="Evolution Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Baseline score", f"{result.baseline_score:.4f}")
    table.add_row("Final score", f"{result.final_score:.4f}")
    improvement = result.final_score - result.baseline_score
    color = "green" if improvement > 0 else ("red" if improvement < 0 else "yellow")
    table.add_row("Improvement", f"[{color}]{improvement:+.4f}[/{color}]")
    table.add_row("Iterations", str(result.iterations))
    table.add_row("Accepted", str(result.accepted_count))
    console.print(table)
    console.print(f"\nHistory saved to [cyan]{result.history_path}[/cyan]")


@app.command(name="eval-list")
def eval_list(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """List registered benchmarks."""
    _setup_logging(verbose)

    import semideus.evaluation  # noqa: F401
    from semideus.core.registry import registry
    from semideus.core.types import ComponentType

    names = registry.list(ComponentType.BENCHMARK)
    table = Table(title="Registered Benchmarks")
    table.add_column("Name", style="cyan")
    for name in sorted(names):
        table.add_row(name)
    console.print(table)


if __name__ == "__main__":
    app()
