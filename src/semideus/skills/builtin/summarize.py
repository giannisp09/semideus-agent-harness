"""Built-in summarize skill: concise summaries of code, results, and conversations."""

from __future__ import annotations

from semideus.core.interfaces import Skill, SkillMetadata
from semideus.core.registry import registry
from semideus.core.types import ComponentType, ToolDefinition


@registry.register(ComponentType.SKILL, "summarize")
class SummarizeSkill(Skill):
    """Activates summarization mode.

    When active, the agent produces concise, structured summaries
    of code, conversations, results, or documentation.
    """

    @property
    def metadata(self) -> SkillMetadata:
        return SkillMetadata(
            name="summarize",
            description="Produce concise structured summaries",
            version="0.1.0",
            tags=["summarize", "report", "documentation"],
        )

    trigger_keywords: list[str] = [
        "summarize", "summary", "report", "recap",
        "overview", "tldr", "explain",
    ]
    trigger_explicit: list[str] = ["/summarize", "/report"]
    chain_next: str | None = None

    def get_system_prompt(self) -> str:
        return """\
## Summarize Mode Active

Produce a concise, structured summary. Follow these guidelines:

1. **Lead with the conclusion** — state the key finding or answer first.
2. **Structure by importance** — most critical information first, details later.
3. **Use bullet points** for lists of findings, changes, or recommendations.
4. **Be specific** — include file names, line numbers, function names where relevant.
5. **Quantify when possible** — "3 files changed, 2 tests added" not "some changes were made".

Format your summary with clear sections:
- **TL;DR**: One-sentence summary
- **Key Findings**: Bullet points of the most important items
- **Details**: Deeper analysis if needed
- **Next Steps**: Recommended actions (if applicable)"""

    def get_tools(self) -> list[ToolDefinition]:
        return []
