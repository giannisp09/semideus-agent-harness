"""Execution state tracking for agent sessions."""

from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from semideus.core.types import SessionStatus, TokenUsage


class SessionState(BaseModel):
    """Tracks the state of an agent execution session."""

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: SessionStatus = SessionStatus.RUNNING
    step_count: int = 0
    total_usage: TokenUsage = Field(default_factory=TokenUsage)
    start_time: float = Field(default_factory=time.time)
    end_time: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def record_step(self, usage: TokenUsage | None = None) -> None:
        """Record a completed step."""
        self.step_count += 1
        if usage:
            self.total_usage.input_tokens += usage.input_tokens
            self.total_usage.output_tokens += usage.output_tokens
            self.total_usage.cache_read_tokens += usage.cache_read_tokens
            self.total_usage.cache_write_tokens += usage.cache_write_tokens

    def finish(self, status: SessionStatus = SessionStatus.COMPLETED) -> None:
        """Mark session as finished."""
        self.status = status
        self.end_time = time.time()

    @property
    def elapsed(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time
