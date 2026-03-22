"""Main Harness — wires all components together."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from semideus.core.config import HarnessConfig, load_config
from semideus.core.events import EventBus
from semideus.core.registry import registry
from semideus.core.types import ComponentType
from semideus.harness.agent import Agent
from semideus.harness.context import ContextManager
from semideus.harness.state import SessionState
from semideus.harness.tracer import AgentTracer
from semideus.memory.manager import MemoryManager
from semideus.skills.chain import SkillChainExecutor
from semideus.skills.manager import SkillManager
from semideus.tools.manager import ToolManager

logger = logging.getLogger(__name__)


class Harness:
    """The main harness that assembles and orchestrates all components.

    Usage:
        harness = Harness.from_config()
        result = await harness.run("Do something useful")
    """

    def __init__(self, config: HarnessConfig) -> None:
        self._config = config
        self._event_bus = EventBus()
        self._tool_manager = ToolManager(event_bus=self._event_bus)
        self._skill_manager = SkillManager(event_bus=self._event_bus)
        self._chain_executor = SkillChainExecutor(
            self._skill_manager, event_bus=self._event_bus
        )
        self._memory_manager: MemoryManager | None = None
        self._provider = None
        self._initialized = False
        self._last_agent_state: SessionState | None = None

    @classmethod
    def from_config(
        cls,
        config_path: str | Path | None = None,
        overrides: dict[str, Any] | None = None,
        base_dir: str | Path | None = None,
    ) -> Harness:
        """Create a Harness from YAML config."""
        config = load_config(config_path, overrides, base_dir=base_dir)
        return cls(config)

    def _ensure_initialized(self) -> None:
        """Lazy initialization of components."""
        if self._initialized:
            return

        # Initialize tracer if enabled
        # Even if not enabled, we can bind it so config determines log vs console
        if getattr(self._config.trace, "enabled", False):
            AgentTracer(config=self._config.trace, event_bus=self._event_bus)

        # Ensure provider modules are imported so decorators run
        import semideus.providers  # noqa: F401

        # Create provider
        provider_cls = registry.get(
            ComponentType.PROVIDER, self._config.provider.name
        )
        self._provider = provider_cls(self._config.provider)

        # Register built-in tools
        self._register_tools()

        # Initialize memory
        self._init_memory()

        # Initialize skills
        self._init_skills()

        # Discover plugins
        plugins_path = Path(self._config.plugins_dir)
        if plugins_path.is_dir():
            registry.discover_plugins(plugins_path)

        self._initialized = True

    def _register_tools(self) -> None:
        """Register enabled built-in tools."""
        from semideus.tools.builtin.filesystem import ReadFileTool, WriteFileTool, ListDirTool, GlobTool
        from semideus.tools.builtin.shell import ShellTool
        from semideus.tools.builtin.git import GitStatusTool, GitDiffTool, GitLogTool
        from semideus.tools.builtin.web import HttpFetchTool
        from semideus.tools.builtin.subagent import SubAgentTool

        tool_map = {
            "filesystem": [ReadFileTool, WriteFileTool, ListDirTool, GlobTool],
            "shell": [ShellTool],
            "git": [GitStatusTool, GitDiffTool, GitLogTool],
            "web": [HttpFetchTool],
            "subagent": [SubAgentTool],
        }

        for tool_group in self._config.tools.enabled:
            if tool_group in tool_map:
                for tool_cls in tool_map[tool_group]:
                    if tool_cls == SubAgentTool:
                        tool = tool_cls(self._config)
                    else:
                        tool = tool_cls()
                    self._tool_manager.register(tool)

    def _init_memory(self) -> None:
        """Initialize memory manager with the configured backend."""
        # Import memory backends so @registry.register decorators run
        import semideus.memory.file_store  # noqa: F401
        try:
            import semideus.memory.vector_store  # noqa: F401
        except ImportError:
            pass  # chromadb not installed — vector backend unavailable

        self._memory_manager = MemoryManager(
            config=self._config.memory,
            event_bus=self._event_bus,
        )
        logger.debug(
            "Memory initialized: backend=%s, path=%s",
            self._config.memory.backend,
            self._config.memory.path,
        )

    def _init_skills(self) -> None:
        """Initialize skills: register builtins, load from directory, set up chains."""
        # Import builtin skills so @registry.register decorators run
        import semideus.skills.builtin.debug  # noqa: F401
        import semideus.skills.builtin.code_review  # noqa: F401
        import semideus.skills.builtin.summarize  # noqa: F401
        import semideus.skills.builtin.fix  # noqa: F401

        # Register builtin skills from the registry
        for skill_name in registry.list(ComponentType.SKILL):
            skill_cls = registry.get(ComponentType.SKILL, skill_name)
            skill_instance = skill_cls()
            self._skill_manager.register(skill_instance)

        # Load user-defined skills from the skills directory
        from semideus.skills.loader import load_skills_from_directory

        skills_dir = Path(self._config.skills.dir)
        file_skills = load_skills_from_directory(skills_dir)
        for skill in file_skills:
            self._skill_manager.register(skill)

        # Filter to enabled skills (if specified)
        if self._config.skills.enabled:
            for name in self._skill_manager.available_names:
                if name not in self._config.skills.enabled:
                    self._skill_manager.unregister(name)

        # Register configured chains
        for chain_name, skill_names in self._config.skills.chains.items():
            self._chain_executor.register_chain_from_config(
                chain_name, skill_names
            )

        logger.debug(
            "Skills initialized: %d available, %d chains",
            len(self._skill_manager.available_names),
            len(self._chain_executor.chain_names),
        )

    async def run(self, task: str) -> str:
        """Run the agent on a task."""
        self._ensure_initialized()

        context = ContextManager(self._config.agent)

        # Inject relevant memories into context
        if self._memory_manager:
            memory_context = await self._memory_manager.get_context(task)
            if memory_context:
                context.add_system_context(memory_context)

        # Auto-select skills based on task content
        if self._config.skills.auto_select:
            await self._skill_manager.select_for_task(task)

        # Inject active skill prompts into context
        for prompt in self._skill_manager.get_active_prompts():
            context.add_system_context(prompt)

        agent = Agent(
            provider=self._provider,
            tool_manager=self._tool_manager,
            context=context,
            event_bus=self._event_bus,
            max_steps=self._config.agent.max_steps,
            memory_manager=self._memory_manager,
            skill_manager=self._skill_manager,
        )

        result = await agent.run(task)
        self._last_agent_state = agent.state

        # Deactivate all skills after the run
        await self._skill_manager.deactivate_all()

        return result

    @property
    def last_agent_state(self) -> SessionState | None:
        """The session state from the most recent run, for benchmark inspection."""
        return self._last_agent_state

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def config(self) -> HarnessConfig:
        return self._config

    @property
    def memory(self) -> MemoryManager | None:
        return self._memory_manager

    @property
    def skills(self) -> SkillManager:
        return self._skill_manager

    @property
    def chains(self) -> SkillChainExecutor:
        return self._chain_executor

    async def close(self) -> None:
        """Clean up resources."""
        if self._provider:
            await self._provider.close()
        if self._memory_manager:
            await self._memory_manager.close()
