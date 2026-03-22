"""Built-in fix skill: targeted code fixes (chains from debug)."""

from __future__ import annotations

from semideus.core.interfaces import Skill, SkillMetadata
from semideus.core.registry import registry
from semideus.core.types import ComponentType, ToolDefinition


@registry.register(ComponentType.SKILL, "fix")
class FixSkill(Skill):
    """Activates fix mode — applies targeted code fixes.

    Designed to chain after the debug skill: once the root cause is identified,
    this skill guides the agent to apply a minimal, correct fix and verify it.
    """

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="fix",
            description="Apply targeted code fixes with verification",
            version="0.1.0",
            tags=["fix", "patch", "repair", "code"],
        )

    trigger_keywords: list[str] = ["fix", "patch", "repair", "resolve"]
    trigger_explicit: list[str] = ["/fix"]
    chain_next: str | None = "summarize"  # debug -> fix -> summarize

    def get_system_prompt(self) -> str:
        return """\
## Fix Mode Active

Apply a targeted fix based on the identified root cause. Follow these rules:

1. **Minimal change**: Fix only what's broken. Do not refactor, clean up, or "improve" surrounding code.
2. **Read before writing**: Always read the file and understand the context before making edits.
3. **One logical change**: Each fix should address exactly one issue.
4. **Verify**: After applying the fix, run the relevant test or command to confirm it works.
5. **Explain**: Briefly state what you changed and why.

If multiple issues need fixing, address them one at a time in priority order."""

    def get_tools(self) -> list[ToolDefinition]:
        return []
