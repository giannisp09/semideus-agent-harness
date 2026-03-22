"""Exception hierarchy for the Omega harness."""


class OmegaError(Exception):
    """Base exception for all Omega errors."""


class ConfigError(OmegaError):
    """Configuration loading or validation error."""


class ProviderError(OmegaError):
    """LLM provider error (API failures, auth, rate limits)."""


class SkillError(OmegaError):
    """Skill loading, chaining, or execution error."""


class ToolError(OmegaError):
    """Tool registration or execution error."""


class MemoryError(OmegaError):
    """Memory store read/write error."""


class GuardrailError(OmegaError):
    """Guardrail check failure (input or output blocked)."""


class EvaluationError(OmegaError):
    """Benchmark or evaluation error."""


class EvolutionError(OmegaError):
    """Self-evolution loop error."""


class TrainingError(OmegaError):
    """Training pipeline error."""


class RegistryError(OmegaError):
    """Component registry error (not found, duplicate, etc.)."""


class ExecutionError(OmegaError):
    """Sandboxed execution error."""


class ContextError(OmegaError):
    """Context management error (overflow, compaction failure)."""
