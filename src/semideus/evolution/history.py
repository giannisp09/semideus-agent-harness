"""Evolution iteration tracking — persists run history to disk."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IterationRecord(BaseModel):
    """Record of a single evolution iteration."""

    iteration: int
    analysis: dict[str, Any] = Field(default_factory=dict)
    mutations: list[dict[str, Any]] = Field(default_factory=list)
    before_score: float = 0.0
    after_score: float = 0.0
    accepted: bool = False
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class EvolutionHistory:
    """Tracks and persists the full history of an evolution run.

    Data is saved to ``.semideus/evolution/<run_id>.json``.
    """

    def __init__(self, run_id: str, base_dir: Path | None = None) -> None:
        self.run_id = run_id
        self._base_dir = base_dir or Path.cwd()
        self.baseline_score: float = 0.0
        self.iterations: list[IterationRecord] = []
        self._started_at = datetime.now(timezone.utc).isoformat()

    def record_baseline(self, score: float) -> None:
        self.baseline_score = score

    def record_iteration(
        self,
        iteration: int,
        analysis: dict[str, Any],
        mutations: list[dict[str, Any]],
        before_score: float,
        after_score: float,
        accepted: bool,
    ) -> None:
        self.iterations.append(
            IterationRecord(
                iteration=iteration,
                analysis=analysis,
                mutations=mutations,
                before_score=before_score,
                after_score=after_score,
                accepted=accepted,
            )
        )

    @property
    def best_score(self) -> float:
        accepted = [it for it in self.iterations if it.accepted]
        if accepted:
            return max(it.after_score for it in accepted)
        return self.baseline_score

    @property
    def accepted_count(self) -> int:
        return sum(1 for it in self.iterations if it.accepted)

    def save(self) -> Path:
        """Persist history to disk and return the file path."""
        out_dir = self._base_dir / ".semideus" / "evolution"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.run_id}.json"

        data = {
            "run_id": self.run_id,
            "started_at": self._started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "baseline_score": self.baseline_score,
            "best_score": self.best_score,
            "total_iterations": len(self.iterations),
            "accepted_count": self.accepted_count,
            "iterations": [it.model_dump() for it in self.iterations],
        }

        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        logger.info("Evolution history saved to %s", path)
        return path
