"""Lightweight asyncio event bus for in-process pub/sub."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Coroutine
from typing import Any

# Type alias for async event handlers
EventHandler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    """Simple async event bus: subscribe handlers to named events, emit to trigger them."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def on(self, event_name: str, handler: EventHandler) -> None:
        """Register an async handler for an event."""
        self._handlers[event_name].append(handler)

    def off(self, event_name: str, handler: EventHandler) -> None:
        """Unregister a handler. No-op if not found."""
        handlers = self._handlers.get(event_name, [])
        if handler in handlers:
            handlers.remove(handler)

    async def emit(self, event_name: str, **kwargs: Any) -> None:
        """Emit an event, calling all registered handlers concurrently."""
        handlers = self._handlers.get(event_name, [])
        if not handlers:
            return
        await asyncio.gather(*(h(**kwargs) for h in handlers), return_exceptions=True)

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()

    @property
    def handler_count(self) -> int:
        """Total number of registered handlers across all events."""
        return sum(len(v) for v in self._handlers.values())
