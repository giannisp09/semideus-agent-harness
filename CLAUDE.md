# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

semideus-agentic-harness — a modular, self-evolving agentic harness for LLM-powered agents. Python 3.13, managed with uv.

## Commands

- **Install dependencies**: `uv sync`
- **Run CLI**: `uv run semideus <command>`
- **Run agent**: `uv run semideus run "your task here"`
- **List providers**: `uv run semideus providers`
- **List components**: `uv run semideus components`
- **Init project**: `uv run semideus init`
- **Run via main.py**: `uv run main.py`

## Architecture

Uses `src/semideus/` layout with `hatchling` build backend.

- **`core/`** — Foundation: interfaces (ABCs), registry (plugin system), config (Pydantic + YAML), events (async pub/sub), errors, types
- **`providers/`** — LLM providers: Anthropic, OpenAI, vLLM local (all registered via `@registry.register` decorator)
- **`harness/`** — Agent runtime: Harness (assembler), Agent (step loop), ContextManager (message history), SessionState (tracking)
- **`tools/`** — Tool system: ToolManager (registry + dispatch), execution (sandboxed shell), built-in tools (filesystem, shell, git, web)
- **`memory/`** — Tiered memory: FileMemoryStore (JSON on disk), VectorMemoryStore (ChromaDB), MemoryManager (session + persistent tiers)
- **`skills/`** — Skill system: SkillManager (registry + progressive disclosure), SkillChain (composable pipelines), FileSkill (YAML-loaded), builtin skills (debug, fix, code_review, summarize)
- **`cli.py`** — Typer CLI entry point

### Key patterns

- **Registry/Plugin**: `ComponentRegistry` with `@register(type, name)` decorator. All component types (provider, skill, tool, memory) registered the same way.
- **Config**: Pydantic models loaded from `configs/default.yaml`, mergeable with overrides. API keys resolved from env vars.
- **Event Bus**: Async pub/sub for hooks (`agent.step.before/after`, `tool.call.before/after`, `session.start/end`, `skill.activated/deactivated`).
- **Interfaces**: All ABCs in `core/interfaces.py` — single source of truth for contracts.
- **Tiered Memory**: Session memory (in-memory, ephemeral) + persistent memory (file/vector, durable). Auto-persists session summaries. Relevant memories injected into context at run start.
- **Progressive Disclosure**: Only active skill prompts/tools are injected into LLM context. Skills auto-selected by task keywords or explicit triggers (`/debug`).
- **Skill Chaining**: Skills can chain via `chain_next` field (e.g., `debug -> fix -> summarize`). Chains can be defined in config or auto-built from skill links.

### Future phases (not yet implemented)

Guardrails, Evaluation, Self-Evolution Loop, Training Pipeline, MCP, Orchestration, Experiments.
