"""Memory manager: tiered memory with session + persistent layers."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from semideus.core.config import MemoryConfig
from semideus.core.events import EventBus
from semideus.core.interfaces import MemoryStore
from semideus.core.registry import registry
from semideus.core.types import ComponentType

logger = logging.getLogger(__name__)


class MemoryManager:
    """Orchestrates tiered memory for an agent session.

    Two tiers:
        - **Session memory** (in-memory dict): fast, ephemeral, cleared when session ends.
          Good for tracking intermediate results, iteration history, and step-level state.
        - **Persistent memory** (FileMemoryStore or VectorMemoryStore): durable across sessions.
          Good for institutional knowledge, learned conventions, and cross-session context.

    The manager provides a unified API:
        - ``remember(key, value, ...)``  — store to the appropriate tier
        - ``recall(key)``               — retrieve from persistent, fallback to session
        - ``search(query)``             — search across persistent store
        - ``get_context(task)``         — retrieve relevant memories formatted for context injection
    """

    def __init__(
        self,
        config: MemoryConfig,
        event_bus: EventBus | None = None,
    ) -> None:
        self._config = config
        self._event_bus = event_bus

        # Session-scoped memory (in-memory, ephemeral)
        self._session: dict[str, Any] = {}
        self._session_log: list[dict[str, Any]] = []

        # Persistent memory (backend determined by config)
        self._persistent = self._create_store(config)

        # Wire up event listeners
        if event_bus:
            event_bus.subscribe("session.end", self._on_session_end)

    def _create_store(self, config: MemoryConfig) -> MemoryStore:
        """Instantiate the configured persistent memory backend."""
        store_cls = registry.get(ComponentType.MEMORY, config.backend)
        return store_cls(base_path=config.path)

    # -- Session memory (ephemeral) -------------------------------------------

    def session_set(self, key: str, value: Any) -> None:
        """Store a value in session memory (ephemeral, in-memory only)."""
        self._session[key] = value

    def session_get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from session memory."""
        return self._session.get(key, default)

    def session_clear(self) -> None:
        """Clear all session memory."""
        self._session.clear()
        self._session_log.clear()

    def log_step(self, step: int, summary: str, metadata: dict[str, Any] | None = None) -> None:
        """Append to the session iteration log (short-term memory markdown pattern from M2*)."""
        entry = {
            "step": step,
            "summary": summary,
            "metadata": metadata or {},
            "timestamp": time.time(),
        }
        self._session_log.append(entry)

    @property
    def session_log(self) -> list[dict[str, Any]]:
        """Return the session iteration log."""
        return list(self._session_log)

    # -- Persistent memory -----------------------------------------------------

    async def remember(
        self,
        key: str,
        value: Any,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a value in persistent memory."""
        await self._persistent.store(key, value, metadata)

    async def recall(self, key: str) -> Any | None:
        """Retrieve from persistent memory, falling back to session memory."""
        value = await self._persistent.retrieve(key)
        if value is not None:
            return value
        return self._session.get(key)

    async def forget(self, key: str) -> bool:
        """Delete from persistent memory."""
        return await self._persistent.delete(key)

    async def list_memories(self, prefix: str = "") -> list[str]:
        """List all persistent memory keys."""
        return await self._persistent.list_keys(prefix)

    async def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Search persistent memory (keyword or semantic depending on backend)."""
        return await self._persistent.search(query, top_k)

    # -- Context injection -----------------------------------------------------

    async def get_context(self, task: str, max_entries: int = 5) -> str:
        """Retrieve relevant memories and format them for system prompt injection.

        Returns a formatted string suitable for ``ContextManager.add_system_context()``.
        Returns empty string if no relevant memories are found.
        """
        results = await self.search(task, top_k=max_entries)
        if not results:
            return ""

        lines = ["## Relevant Memories"]
        for entry in results:
            key = entry["key"]
            value = entry["value"]
            # Truncate long values for context injection
            if isinstance(value, str) and len(value) > 500:
                value = value[:500] + "..."
            elif not isinstance(value, str):
                value = json.dumps(value, default=str)
                if len(value) > 500:
                    value = value[:500] + "..."
            lines.append(f"- **{key}**: {value}")

        return "\n".join(lines)

    # -- Event handlers --------------------------------------------------------

    async def _on_session_end(self, data: dict[str, Any]) -> None:
        """Persist session summary when a session ends."""
        session_id = data.get("session_id", "unknown")
        status = data.get("status", "unknown")
        steps = data.get("steps", 0)

        # Only persist if there's meaningful session data
        if not self._session_log:
            return

        summary = {
            "session_id": session_id,
            "status": status,
            "steps": steps,
            "log": self._session_log[-10:],  # Keep last 10 entries
            "session_data": {
                k: v for k, v in self._session.items()
                if isinstance(v, (str, int, float, bool, list, dict))
            },
        }

        await self.remember(
            key=f"session/{session_id}",
            value=summary,
            metadata={"type": "session_summary", "status": status, "steps": steps},
        )
        logger.debug("Persisted session summary: %s", session_id)

    # -- Lifecycle -------------------------------------------------------------

    async def close(self) -> None:
        """Clean up resources."""
        await self._persistent.close()
        self.session_clear()
