"""ALL abstract base classes and protocols — single source of truth for contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from semideus.core.types import (
    EvalResult,
    LLMResponse,
    Message,
    ToolDefinition,
    ToolResult,
)


# ---------------------------------------------------------------------------
# LLM Providers
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """Abstract LLM provider interface."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send messages and return a complete response."""

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[LLMResponse]:
        """Stream response chunks."""

    async def close(self) -> None:
        """Clean up resources."""


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

class SkillMetadata:
    def __init__(
        self,
        name: str,
        description: str,
        version: str = "0.1.0",
        tags: list[str] | None = None,
    ):
        self.name = name
        self.description = description
        self.version = version
        self.tags = tags or []


class Skill(ABC):
    """A composable skill that augments agent capabilities."""

    @property
    @abstractmethod
    def metadata(self) -> SkillMetadata: ...

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return system prompt fragment for this skill."""

    def get_tools(self) -> list[ToolDefinition]:
        """Return tools this skill provides."""
        return []

    async def on_activate(self) -> None:
        """Called when the skill is activated."""

    async def on_deactivate(self) -> None:
        """Called when the skill is deactivated."""


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemoryStore(ABC):
    """Persistent memory storage interface."""

    @abstractmethod
    async def store(self, key: str, value: Any, metadata: dict[str, Any] | None = None) -> None: ...

    @abstractmethod
    async def retrieve(self, key: str) -> Any | None: ...

    @abstractmethod
    async def delete(self, key: str) -> bool: ...

    @abstractmethod
    async def list_keys(self, prefix: str = "") -> list[str]: ...

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Semantic search (optional — not all backends support this)."""
        return []

    async def close(self) -> None:
        """Clean up resources."""


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

class Tool(ABC):
    """An executable tool that agents can invoke."""

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition: ...

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> ToolResult: ...


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------

class Guardrail(ABC):
    """Safety guardrail that checks inputs and outputs."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def check_input(self, messages: list[Message]) -> tuple[bool, str]:
        """Check input. Returns (allowed, reason)."""

    @abstractmethod
    async def check_output(self, response: LLMResponse) -> tuple[bool, str]:
        """Check output. Returns (allowed, reason)."""


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

class Benchmark(ABC):
    """A benchmark that evaluates agent performance."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def run(self, agent: Any) -> EvalResult:
        """Run the benchmark against an agent, return results."""


# ---------------------------------------------------------------------------
# Evolution
# ---------------------------------------------------------------------------

class EvolutionStrategy(ABC):
    """Strategy for self-evolution iterations."""

    @abstractmethod
    async def analyze(self, history: list[EvalResult]) -> dict[str, Any]:
        """Analyze performance history to identify weaknesses."""

    @abstractmethod
    async def plan(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Plan modifications based on analysis."""

    @abstractmethod
    async def modify(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Execute modifications in a sandbox, return change description."""

    @abstractmethod
    async def should_accept(
        self, before: EvalResult, after: EvalResult
    ) -> bool:
        """Decide whether to accept or reject the modification."""


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

class TrainingJob(ABC):
    """Abstract training job interface."""

    @abstractmethod
    async def prepare_dataset(self, trajectories: list[dict[str, Any]]) -> str:
        """Convert trajectories to a training dataset. Returns dataset path/id."""

    @abstractmethod
    async def launch(self, dataset_id: str, **kwargs: Any) -> str:
        """Launch the training job. Returns job id."""

    @abstractmethod
    async def status(self, job_id: str) -> dict[str, Any]:
        """Check training job status."""
