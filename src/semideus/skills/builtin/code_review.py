"""Built-in code review skill: quality, security, and correctness analysis."""

from __future__ import annotations

from semideus.core.interfaces import Skill, SkillMetadata
from semideus.core.registry import registry
from semideus.core.types import ComponentType, ToolDefinition


@registry.register(ComponentType.SKILL, "code_review")
class CodeReviewSkill(Skill):
    """Activates code review mode.

    When active, the agent reviews code for quality, security vulnerabilities,
    correctness, and adherence to project conventions.
    """

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="code_review",
            description="Review code for quality, security, and correctness",
            version="0.1.0",
            tags=["review", "quality", "security", "code"],
        )

    trigger_keywords: list[str] = [
        "review", "code review", "check code", "audit",
        "security review", "quality check",
    ]
    trigger_explicit: list[str] = ["/review", "/code-review"]
    chain_next: str | None = None

    def get_system_prompt(self) -> str:
        return """\
## Code Review Mode Active

You are reviewing code. Analyze systematically across these dimensions:

1. **Correctness**: Does the code do what it claims? Are there logic errors, off-by-one bugs, or unhandled edge cases?
2. **Security**: Check for OWASP top 10 vulnerabilities — injection, XSS, auth issues, secrets in code, path traversal.
3. **Performance**: Obvious inefficiencies — N+1 queries, unnecessary allocations, missing indexes.
4. **Readability**: Is the code clear? Are names descriptive? Is the structure logical?
5. **Conventions**: Does it follow the project's existing patterns and style?

For each issue found, report:
- **Severity**: critical / high / medium / low / nit
- **Location**: file:line
- **Issue**: What's wrong
- **Suggestion**: How to fix it

Be specific and actionable. Don't flag style preferences unless they impact readability."""

    def get_tools(self) -> list[ToolDefinition]:
        return []
