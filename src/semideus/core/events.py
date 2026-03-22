"""Async event bus for hooks and middleware."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

EventHandler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    """Simple async pub/sub event bus.

    Usage:
        bus = EventBus()

        @bus.on("agent.step.before")
        async def log_step(data):
            print(f"Step: {data}")

        await bus.emit("agent.step.before", {"step": 1})
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def on(self, event: str) -> Callable[[EventHandler], EventHandler]:
        """Decorator to register an event handler."""
        def decorator(fn: EventHandler) -> EventHandler:
            self._handlers[event].append(fn)
            return fn
        return decorator

    def subscribe(self, event: str, handler: EventHandler) -> None:
        """Programmatically subscribe a handler to an event."""
        self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: EventHandler) -> None:
        """Remove a handler from an event."""
        self._handlers[event] = [h for h in self._handlers[event] if h is not handler]

    async def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        """Emit an event, calling all registered handlers concurrently."""
        handlers = self._handlers.get(event, [])
        if not handlers:
            return
        data = data or {}
        results = await asyncio.gather(
            *(h(data) for h in handlers),
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Event handler %s for '%s' raised: %s",
                    handlers[i].__name__, event, result,
                )

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()
