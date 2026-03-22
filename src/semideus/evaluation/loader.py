"""Load benchmark suites from YAML files."""

from __future__ import annotations

from pathlib import Path

from semideus.core.config import load_yaml
from semideus.core.errors import EvaluationError
from semideus.evaluation.types import BenchmarkSuite


def load_suite(path: Path) -> BenchmarkSuite:
    """Load a single benchmark suite from a YAML file."""
    if not path.exists():
        raise EvaluationError(f"Suite file not found: {path}")
    data = load_yaml(path)
    if not data:
        raise EvaluationError(f"Empty suite file: {path}")
    try:
        return BenchmarkSuite(**data)
    except Exception as e:
        raise EvaluationError(f"Invalid suite file {path}: {e}") from e


def load_suites_from_directory(dir_path: Path) -> list[BenchmarkSuite]:
    """Load all benchmark suites from YAML files in a directory."""
    if not dir_path.is_dir():
        return []
    suites = []
    for yaml_file in sorted(dir_path.glob("*.yaml")):
        suites.append(load_suite(yaml_file))
    for yml_file in sorted(dir_path.glob("*.yml")):
        suites.append(load_suite(yml_file))
    return suites
