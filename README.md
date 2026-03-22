# Semideus Agentic Harness

A modular, self-evolving agentic harness for LLM-powered agents. Designed around a flexible plugin architecture and an event-driven core to support multiple LLM providers, tools, tiered memory, and sophisticated skill chains.

## Overview

The Semideus Agentic Harness provides a robust runtime environment (harness) to spin up and track advanced autonomous agents. It supports progressive disclosure of skills, sandboxed execution of tools, and tiered (session + persistent vector/file) memory out-of-the-box.

### Key Features

* **Modular Architecture**: Built on a solid foundation with an extensible `ComponentRegistry`. Everything (providers, tools, memory stores, skills) is a registered component.
* **Tiered Memory**: Maintains short-term session memory in-memory, while long-term memories and vector summaries can be seamlessly committed to persistent storage mechanisms like JSON files or ChromaDB.
* **Event-Driven Execution**: Employs an asynchronous pub/sub event bus handling hooks for agent steps, tool calls, skill activations, and session lifecycles.
* **Progressive Skills Matrix**: Auto-injects relevant prompts and tools directly into the LLM context to prevent prompt bloating.
* **Skill Chaining**: Design complex logic by linking skills sequentially (e.g., `debug -> fix -> summarize`).

## Prerequisites

* **Python:** `>= 3.13`
* Package managed via [uv](https://github.com/astral-sh/uv). Ensure `uv` is installed on your system.

## Installation

To set up the project and install its dependencies, simply clone the repository and use `uv sync`. You can also use the included Makefile for convenience:

```bash
# Clone the repository
git clone <repository_url>
cd omega-agentic-harness

# Install dependencies using uv
make install
# or directly: uv sync
```

### Optional Dependencies
Depending on the components you are using, you can install optional dependencies:
- **Vector Storage**: `uv pip install ".[vector]"` (installs ChromaDB)
- **Training**: `uv pip install ".[training]"`
- **MCP Integration**: `uv pip install ".[mcp]"`
- **Docker/Sandboxing**: `uv pip install ".[docker]"`
- **All Features**: `uv pip install ".[all]"`

## Usage

The harness comes with a comprehensive CLI interface (`semideus`) mapped to various utility tasks in the `Makefile`. 

### Running an Agent

To run the agent with a specific objective, use the `make run` command:

```bash
make run TASK="Analyze codebase and suggest minor optimizations"
```

Or using the CLI directly:
```bash
uv run semideus run "Analyze codebase and suggest minor optimizations"
```

### Make Commands Cheatsheet

| Command | Description |
|---|---|
| `make install` | Install all bare dependencies using `uv sync`. |
| `make cli CMD="..."` | Run the underlying semideus CLI. E.g., `make cli CMD="run 'my task'"`. |
| `make run TASK="..."` | Quickly start an agent with the given task. |
| `make providers` | List all LLM providers currently registered. |
| `make components` | List all modular components available in the system. |
| `make init` | Initialize project configurations. |
| `make main` | Run the application via the `main.py` entrypoint. |

## Project Structure

```text
omega-agentic-harness/
├── src/
│   └── semideus/
│       ├── core/       # Interfaces, configuration parsing, pub/sub event bus, registry.
│       ├── providers/  # LLM integrations (Anthropic, OpenAI, vLLM).
│       ├── harness/    # Agent lifecycle engine, runtime loops, history tracking.
│       ├── tools/      # Sandboxed tool orchestration (git, shell, files).
│       ├── memory/     # Context/memory management (in-memory, JSON, Vector).
│       ├── skills/     # Specialised behavior implementations and configurations.
│       └── cli.py      # Entrypoint for the Typer CLI app.
├── configs/            # YAML configurations defining agents, skills, and model behavior.
├── skills/             # External skill definition files.
├── Makefile            # Quick command abbreviations.
└── main.py             # Simple direct execution entrypoint.
```

## Configuration

Configurations are managed via a combination of Pydantic models and YAML files (ordinarily rooted at `configs/default.yaml`). The system merges runtime specifications over the default configuration tree. 

API Keys for activated providers (e.g., `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) should be exported as environment variables prior to running the harness.

## Roadmap & Future Enhancements

Future development phases to watch out for include:
- Strict Guardrails implementations
- Evaluative mechanisms 
- A Continuous Self-Evolution Loop 
- Automated Training Pipelines 
- Full MCP (Model Context Protocol) Integration
- Complex Agent Orchestration & Experimentation Suite
