# Semideus Agentic Harness Architecture

This document describes the architectural flow and internal structure of the `semideus-agentic-harness` using Unicode box-drawing diagrams. This format ensures high legibility across all environments and follows the `architecture-docs` skill constraints.

## System Flow

The core system is an event-driven harness that orchestrates LLM providers, multi-tier memory, sandboxed execution of tools, and complex skill chains. It also supports automated evaluation and self-evolution loops.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                            Semideus Orchestration                            │
├──────────────────────────────────────┬───────────────────────────────────────┤
│           Evolution Loop             │          Evaluation Runner            │
│  (Baseline -> Mutate -> Benchmark)   │     (Task/Skill/Code Benchmarks)      │
└───────────────────┬──────────────────┴──────────────────┬────────────────────┘
                    │                                     │
                    └──────────────────┬──────────────────┘
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │       Harness Assembler       │◀───[ YAML Config ]
                       └───────────────┬───────────────┘
                                       │
           ┌───────────────────────────┴───────────────────────────┐
           │                                                       │
           ▼                                                       ▼
 ┌───────────────────┐       ┌───────────────────┐       ┌───────────────────┐
 │     Event Bus     │◀─────▶│  Agent Lifecycle  │◀─────▶│  Context Manager  │
 └───────────────────┘       └─────────┬─────────┘       └─────────┬─────────┘
                                       │                           ▲
                                       ▼                           │
           ┌───────────────────────────┴───────────────────────────┤
           │                                                       │
           ▼                                                       ▼
 ┌───────────────────┐       ┌───────────────────┐       ┌───────────────────┐
 │   Skill Manager   │       │   Tool Manager    │       │  Memory Manager   │
 └─────────┬─────────┘       └─────────┬─────────┘       └─────────┬─────────┘
           │                           │                           │
           │     ┌─────────────┐       │     ┌─────────────┐       │     ┌─────────────┐
           ├────▶│ Prompt Chain│       ├────▶│ Env Sandbox │       ├────▶│ Vector Store│
           │     └─────────────┘       │     └─────────────┘       │     └─────────────┘
           │     ┌─────────────┐       │     ┌─────────────┐       │     ┌─────────────┐
           └────▶│ Skill Logic │       └────▶│ Shell/Files │       └────▶│ File Store  │
                 └─────────────┘             └─────────────┘             └─────────────┘
                                       │
                                       ▼
                             ┌───────────────────┐
                             │   LLM Provider    │
                             └───────────────────┘
```

## Internal Class Structure

The module structure relies on standard abstractions maintained via a centralized Plugin Registry.

```text
          ┌────────────────┐
          │ BaseComponent  │ (Interface)
          └───────┬────────┘
                  │
        ┌─────────┴─────────┬───────────────────┬──────────────────┐
        │                   │                   │                  │
        ▼                   ▼                   ▼                  ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│    Agent     │    │ MemoryManager│    │ ToolManager  │    │ SkillManager │
├──────────────┤    ├──────────────┤    ├──────────────┤    ├──────────────┤
│ +step()      │    │ +retrieve()  │    │ +dispatch()  │    │ +activate()  │
│ +loop()      │    │ +commit()    │    │ +register()  │    │ +chain()     │
└──────┬───────┘    └──────┬───────┘    └──────┬───────┘    └──────┬───────┘
       │                   │                   │                   │
       │           ┌───────┴───────────────────┴───────┬───────────┘
       ▼           ▼                                   ▼
┌──────────────┐ ┌────────────────┐         ┌──────────────┐
│  Event Bus   │ │ ContextManager │         │ Registry     │
├──────────────┤ ├────────────────┤         ├──────────────┤
│ +subscribe() │ │ +add_message() │         │ +register()  │
│ +publish()   │ │ +get_history() │         │ +get()       │
└──────────────┘ └────────────────┘         └──────────────┘
```

## Architectural Highlights

- **Progressive Skill Disclosure:** Prevents context blooming. The `SkillManager` evaluates intents and selectively activates targeted skills (debug, summarize, etc.), injecting them into the `ContextManager`.
- **Registry / Plugin Pattern:** Every single tier — Providers, Tools, Memories, Skills — registers to the `ComponentRegistry` via decorators, enforcing decoupled behavior.
- **Synchronous Event Bus:** The `EventBus` enables loosely coupled system extensions by broadcasting granular hooks (for instance, `agent.step.before`, `tool.call.after`).
- **Self-Evolution Loop:** The `Evolution` module uses a feedback loop where agent configurations or skills are mutated, benchmarked by the `Evaluation` runner, and accepted only if they improve performance.
- **Sandboxed Execution:** Tools are dispatched through a `ToolManager` that enforces boundaries, ensuring that shell and file operations are tracked and contained.
