"""LLM-driven evolution strategy — analyzes failures, proposes mutations."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from semideus.core.config import EvolutionConfig
from semideus.core.interfaces import EvolutionStrategy, LLMProvider
from semideus.core.registry import registry
from semideus.core.types import ComponentType, EvalResult, Message, Role
from semideus.evolution.mutations import Mutation, parse_mutations
from semideus.evolution.sandbox import WorktreeSandbox

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt constants
# ---------------------------------------------------------------------------

ANALYSIS_SYSTEM_PROMPT = """\
You are an expert AI systems analyst. You are given evaluation results from an \
AI agent harness. Your job is to analyze the results and identify:

1. **Weaknesses**: Which benchmarks or test cases performed poorly?
2. **Failure patterns**: Are there common themes across failures (e.g., tool \
   misuse, poor reasoning, incorrect output format)?
3. **Root causes**: What about the agent's prompts, configuration, or skill \
   definitions likely caused these failures?

Respond with a JSON object containing:
{
  "weaknesses": [{"benchmark": "...", "description": "...", "severity": "high|medium|low"}],
  "patterns": [{"pattern": "...", "affected_benchmarks": [...], "frequency": "..."}],
  "root_causes": [{"cause": "...", "evidence": "...", "suggested_fix": "..."}],
  "priority_order": ["most important cause first", ...]
}
"""

PLANNING_SYSTEM_PROMPT = """\
You are an expert AI systems engineer. Based on the analysis of evaluation \
failures, propose specific mutations to improve the agent's performance.

Available mutation types:

**Modification mutations** (tweak existing components):
- **skill_prompt**: Change a skill's system prompt. Fields: type, skill_name, \
  new_system_prompt, description.
- **config_value**: Change a config value. Fields: type, config_path \
  (dot-separated, e.g. "agent.max_steps"), new_value, description.
- **agent_system_prompt**: Change the main agent system prompt. Fields: type, \
  new_system_prompt, description.

**Creation mutations** (create new capabilities):
- **skill_creation**: Create a brand-new skill. Fields: type, skill_name \
  (lowercase, alphanumeric + underscores, e.g. "code_analyzer"), \
  skill_description, system_prompt (full instructions), trigger_keywords \
  (list of auto-activation words), trigger_explicit (list like ["/analyze"]), \
  chain_next (optional skill name to chain to), tags (list), version \
  (default "0.1.0"), description.
- **skill_chain**: Create or modify a skill chain in config. Fields: type, \
  chain_name, skill_sequence (list of 2+ skill names in order), \
  chain_description, description.
- **skill_tool**: Add or modify tool declarations on an existing skill. \
  Fields: type, skill_name, tools (list of objects with name, description, \
  parameters as JSON Schema), mode ("replace" or "append"), description.

Rules:
- Propose 1-3 mutations per iteration (small, targeted changes).
- Each mutation must have a clear rationale tied to the analysis.
- Prefer **skill_creation** when the agent lacks a capability entirely — \
  don't try to overload existing skills with unrelated responsibilities.
- Prefer **skill_prompt** when an existing skill handles the right domain \
  but its instructions are inadequate.
- Use **skill_chain** when a multi-step workflow would help (e.g., \
  analyze -> fix -> verify).
- Use **skill_tool** to give a skill structured tool access it currently lacks.
- Prefer skill-level mutations over config changes — they are safer.
- Do NOT propose mutations that would break the agent (e.g., setting max_steps=0).
- Do NOT create skills that duplicate built-in skills (listed below).

Respond with a JSON object:
{
  "mutations": [
    {
      "type": "skill_creation",
      "skill_name": "code_analyzer",
      "skill_description": "Analyze code for patterns and anti-patterns",
      "system_prompt": "You are a code analysis expert...",
      "trigger_keywords": ["analyze", "review code", "patterns"],
      "trigger_explicit": ["/analyze"],
      "tags": ["analysis", "code-quality"],
      "description": "New skill to handle code analysis tasks"
    }
  ],
  "rationale": "Overall explanation of the proposed changes"
}
"""


def _extract_json(text: str) -> dict[str, Any]:
    """Extract JSON from LLM response, handling code blocks and markdown."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from code block
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding JSON object boundaries
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    logger.warning("Failed to extract JSON from LLM response")
    return {}


@registry.register(ComponentType.EVOLUTION, "default")
class DefaultEvolutionStrategy(EvolutionStrategy):
    """LLM-driven strategy that analyzes eval failures and proposes mutations."""

    def __init__(
        self,
        provider: LLMProvider,
        config: EvolutionConfig,
        sandbox: WorktreeSandbox | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self._provider = provider
        self._config = config
        self._sandbox = sandbox
        self._repo_root = repo_root or Path.cwd()
        self._current_mutations: list[Mutation] = []

    async def _llm_call(self, system_prompt: str, user_content: str) -> str:
        """Send a single LLM call and return the text response."""
        messages = [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=user_content),
        ]
        response = await self._provider.complete(messages)
        return response.content

    async def analyze(self, history: list[EvalResult]) -> dict[str, Any]:
        """Analyze eval results to identify weaknesses and failure patterns."""
        # Serialize eval results for the LLM
        results_json = json.dumps(
            [r.model_dump() for r in history],
            indent=2,
            default=str,
        )

        user_msg = (
            f"Here are the evaluation results from the most recent run:\n\n"
            f"```json\n{results_json}\n```\n\n"
            f"Analyze these results and identify weaknesses, patterns, and root causes."
        )

        response_text = await self._llm_call(ANALYSIS_SYSTEM_PROMPT, user_msg)
        analysis = _extract_json(response_text)

        if not analysis:
            analysis = {
                "weaknesses": [],
                "patterns": [],
                "root_causes": [{"cause": "Unable to parse analysis", "evidence": response_text}],
                "priority_order": [],
            }

        logger.info(
            "Analysis complete: %d weaknesses, %d patterns, %d root causes",
            len(analysis.get("weaknesses", [])),
            len(analysis.get("patterns", [])),
            len(analysis.get("root_causes", [])),
        )
        return analysis

    async def plan(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Propose mutations based on the analysis."""
        # Gather current context for the LLM
        context_parts = [
            f"Analysis:\n```json\n{json.dumps(analysis, indent=2, default=str)}\n```",
        ]

        # Include current skill prompts if available
        skills_dir = self._repo_root / "skills"
        if skills_dir.is_dir():
            for yaml_path in sorted(skills_dir.glob("*.yaml")):
                content = yaml_path.read_text(encoding="utf-8")
                context_parts.append(f"\nCurrent skill '{yaml_path.stem}':\n```yaml\n{content}\n```")

        # Include agent config and extract chain / tool info
        config_path = self._repo_root / "configs" / "default.yaml"
        config_data: dict[str, Any] = {}
        if config_path.exists():
            config_content = config_path.read_text(encoding="utf-8")
            config_data = yaml.safe_load(config_content) or {}
            context_parts.append(f"\nCurrent config:\n```yaml\n{config_content}\n```")

        # Existing skill chains
        chains = config_data.get("skills", {}).get("chains", {})
        if chains:
            chains_info = json.dumps(chains, indent=2)
            context_parts.append(f"\nExisting skill chains:\n```json\n{chains_info}\n```")

        # Built-in skill names (avoid duplicates)
        builtin_skills = ["debug", "fix", "code_review", "summarize"]
        context_parts.append(
            f"\nBuilt-in skills (do NOT create duplicates): {', '.join(builtin_skills)}"
        )

        # Available tool names from config
        enabled_tools = config_data.get("tools", {}).get("enabled", [])
        if enabled_tools:
            context_parts.append(f"\nAvailable tools: {', '.join(enabled_tools)}")

        user_msg = "\n".join(context_parts) + (
            "\n\nBased on the analysis above, propose specific mutations to improve performance."
        )

        response_text = await self._llm_call(PLANNING_SYSTEM_PROMPT, user_msg)
        plan = _extract_json(response_text)

        if not plan or "mutations" not in plan:
            plan = {"mutations": [], "rationale": "No mutations proposed"}

        logger.info(
            "Plan complete: %d mutations proposed — %s",
            len(plan.get("mutations", [])),
            plan.get("rationale", ""),
        )
        return plan

    async def modify(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Parse and apply mutations from the plan."""
        mutation_specs = plan.get("mutations", [])
        if not mutation_specs:
            return {"applied": 0, "mutations": []}

        self._current_mutations = parse_mutations(mutation_specs)

        if self._sandbox:
            self._sandbox.apply_mutations(self._current_mutations)
        else:
            # Apply directly (no sandbox — testing mode)
            for m in self._current_mutations:
                m.apply(self._repo_root)

        return {
            "applied": len(self._current_mutations),
            "mutations": [m.model_dump() for m in self._current_mutations],
            "rationale": plan.get("rationale", ""),
        }

    async def should_accept(self, before: EvalResult, after: EvalResult) -> bool:
        """Accept if the score improved by at least the acceptance threshold."""
        improvement = after.score - before.score
        accepted = improvement >= self._config.acceptance_threshold
        logger.info(
            "Score change: %.4f -> %.4f (delta=%.4f, threshold=%.4f) -> %s",
            before.score,
            after.score,
            improvement,
            self._config.acceptance_threshold,
            "ACCEPTED" if accepted else "REJECTED",
        )
        return accepted

    @property
    def current_mutations(self) -> list[Mutation]:
        return list(self._current_mutations)
