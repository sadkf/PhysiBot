"""Scheduler — periodic timer for 30-min summaries and daily/weekly consolidation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

AsyncCallback = Callable[[], Coroutine[Any, Any, None]]


class Scheduler:
    """Manages periodic tasks: 30-min segment, daily merge, weekly review."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False

    def add_interval(
        self,
        name: str,
        callback: AsyncCallback,
        interval_seconds: int,
        initial_delay: int = 0,
    ) -> None:
        """Schedule a repeating task."""
        if name in self._tasks:
            logger.warning("Task %s already scheduled, skipping", name)
            return

        async def _loop() -> None:
            if initial_delay > 0:
                await asyncio.sleep(initial_delay)
            while self._running:
                try:
                    logger.info("Scheduler: running %s", name)
                    await callback()
                except Exception:
                    logger.exception("Scheduler task %s failed", name)
                await asyncio.sleep(interval_seconds)

        self._tasks[name] = asyncio.create_task(_loop())

    def add_daily(
        self,
        name: str,
        callback: AsyncCallback,
        hour: int = 23,
        minute: int = 55,
    ) -> None:
        """Schedule a task to run once daily at the given time (UTC)."""

        async def _loop() -> None:
            while self._running:
                now = datetime.now(UTC)
                target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target <= now:
                    # Already past today's target, wait until tomorrow
                    from datetime import timedelta
                    target = target + timedelta(days=1)
                wait = (target - now).total_seconds()
                logger.info(
                    "Scheduler: %s next run in %.0f seconds", name, wait
                )
                await asyncio.sleep(wait)
                if not self._running:
                    break
                try:
                    await callback()
                except Exception:
                    logger.exception("Daily task %s failed", name)

        self._tasks[name] = asyncio.create_task(_loop())

    def start(self) -> None:
        """Mark scheduler as running (call before add_*)."""
        self._running = True

    async def stop(self) -> None:
        """Cancel all scheduled tasks."""
        self._running = False
        for name, task in self._tasks.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            logger.info("Scheduler: stopped %s", name)
        self._tasks.clear()

    @property
    def task_count(self) -> int:
        return len(self._tasks)


class Throttle:
    """Rate limiter: ensures a callback runs at most once per interval."""

    def __init__(self, cooldown_seconds: int = 600) -> None:
        self._cooldown = cooldown_seconds
        self._last_run: float = 0

    async def try_run(self, callback: AsyncCallback) -> bool:
        """Run callback if cooldown has passed. Returns True if executed."""
        import time

        now = time.monotonic()
        if now - self._last_run < self._cooldown:
            remaining = self._cooldown - (now - self._last_run)
            logger.debug(
                "Throttle: skipping, %.0fs remaining", remaining
            )
            return False

        self._last_run = now
        await callback()
        return True

    def reset(self) -> None:
        """Reset the throttle."""
        self._last_run = 0
