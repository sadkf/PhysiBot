"""Unit tests for events/scheduler.py."""

from __future__ import annotations

import asyncio

import pytest

from physi_core.events.scheduler import Scheduler, Throttle


class TestThrottle:
    @pytest.mark.asyncio
    async def test_first_call_passes(self) -> None:
        throttle = Throttle(cooldown_seconds=60)
        called = False

        async def cb() -> None:
            nonlocal called
            called = True

        result = await throttle.try_run(cb)
        assert result is True
        assert called is True

    @pytest.mark.asyncio
    async def test_second_call_within_cooldown_blocked(self) -> None:
        throttle = Throttle(cooldown_seconds=60)

        async def cb() -> None:
            pass

        await throttle.try_run(cb)
        result = await throttle.try_run(cb)
        assert result is False

    @pytest.mark.asyncio
    async def test_call_after_cooldown_passes(self) -> None:
        throttle = Throttle(cooldown_seconds=0)  # instant cooldown

        async def cb() -> None:
            pass

        await throttle.try_run(cb)
        await asyncio.sleep(0.01)
        result = await throttle.try_run(cb)
        assert result is True

    @pytest.mark.asyncio
    async def test_reset(self) -> None:
        throttle = Throttle(cooldown_seconds=9999)

        async def cb() -> None:
            pass

        await throttle.try_run(cb)
        throttle.reset()
        result = await throttle.try_run(cb)
        assert result is True


class TestScheduler:
    @pytest.mark.asyncio
    async def test_interval_task_runs(self) -> None:
        results: list[int] = []

        async def cb() -> None:
            results.append(1)

        sched = Scheduler()
        sched.start()
        sched.add_interval("test", cb, interval_seconds=100)
        assert sched.task_count == 1

        # Give it time to run once
        await asyncio.sleep(0.1)
        await sched.stop()

        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self) -> None:
        sched = Scheduler()
        sched.start()
        sched.add_interval("a", lambda: asyncio.sleep(0), interval_seconds=1)
        sched.add_interval("b", lambda: asyncio.sleep(0), interval_seconds=1)
        assert sched.task_count == 2

        await sched.stop()
        assert sched.task_count == 0

    @pytest.mark.asyncio
    async def test_task_exception_does_not_crash(self) -> None:
        runs = 0

        async def failing_cb() -> None:
            nonlocal runs
            runs += 1
            if runs == 1:
                raise ValueError("boom")

        sched = Scheduler()
        sched.start()
        sched.add_interval("fail", failing_cb, interval_seconds=0)
        await asyncio.sleep(0.15)
        await sched.stop()

        # Should have run at least twice (first fails, second succeeds)
        assert runs >= 2
