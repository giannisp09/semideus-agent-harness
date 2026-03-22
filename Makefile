.PHONY: help install cli run providers components init main

# Default target prints help
help:
	@echo "Available commands:"
	@echo "  make install    - Install dependencies using uv"
	@echo "  make cli        - Run the semideus CLI (pass arguments with CMD=...)"
	@echo "  make run        - Run the agent (pass task with TASK=\"...\")"
	@echo "  make providers  - List all registered providers"
	@echo "  make components - List all registered components"
	@echo "  make init       - Initialize the project project"
	@echo "  make main       - Run the project via main.py"

# Install dependencies
install:
	uv sync

# Run the semideus CLI (example: make cli CMD="run 'my task'")
cli:
	uv run semideus $(CMD)

# Run an agent with a task (example: make run TASK="your task here")
run:
	@if [ -z "$(TASK)" ]; then \
		echo "Please provide a TASK. Example: make run TASK=\"your task here\""; \
	else \
		uv run semideus run "$(TASK)"; \
	fi

# List all providers
providers:
	uv run semideus providers

# List all components
components:
	uv run semideus components

# Initialize the project
init:
	uv run semideus init

# Run via main.py
main:
	uv run main.py
