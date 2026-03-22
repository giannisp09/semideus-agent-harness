"""Built-in debug skill: systematic code debugging."""

from __future__ import annotations

from semideus.core.interfaces import Skill, SkillMetadata
from semideus.core.registry import registry
from semideus.core.types import ComponentType, ToolDefinition


@registry.register(ComponentType.SKILL, "debug")
class DebugSkill(Skill):
    """Activates systematic debugging mode.

    When active, the agent follows a structured debugging process:
    reproduce → isolate → identify root cause → propose fix.
    Chains to 'fix' skill if configured.
    """

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="debug",
            description="Systematic debugging: reproduce, isolate, root-cause, fix",
            version="0.1.0",
            tags=["debugging", "errors", "troubleshooting"],
        )

    # Trigger keywords for auto-selection
    trigger_keywords: list[str] = [
        "debug", "error", "bug", "traceback", "exception",
        "crash", "failing", "broken", "issue",
    ]
    trigger_explicit: list[str] = ["/debug"]
    chain_next: str | None = "fix"

    def get_system_prompt(self) -> str:
        return """\
## Debug Mode Active

You are now in **debug mode**. Follow this systematic process:

1. **Reproduce**: Confirm the issue. Run the failing code/test to see the exact error.
2. **Isolate**: Narrow down the scope. Which file, function, or line causes the failure?
3. **Root-cause**: Trace the logic. Read the relevant code, check assumptions, identify the root cause.
4. **Diagnose**: Explain the root cause clearly before proposing any fix.
5. **Fix**: Propose a minimal, targeted fix. Do not refactor unrelated code.

When reporting, structure your findings as:
- **Symptom**: What the user sees
- **Root cause**: Why it happens
- **Fix**: What to change

Always verify your fix by running the relevant test or command after applying it."""

    def get_tools(self) -> list[ToolDefinition]:
        return []
