"""Unit tests for events/bus.py."""

from __future__ import annotations

import pytest

from physi_core.events.bus import EventBus


class TestEventBus:
    @pytest.mark.asyncio
    async def test_emit_calls_handler(self) -> None:
        bus = EventBus()
        received: list[str] = []

        async def handler(msg: str) -> None:
            received.append(msg)

        bus.on("test", handler)
        await bus.emit("test", msg="hello")

        assert received == ["hello"]

    @pytest.mark.asyncio
    async def test_emit_calls_multiple_handlers(self) -> None:
        bus = EventBus()
        results: list[int] = []

        async def h1(val: int) -> None:
            results.append(val * 2)

        async def h2(val: int) -> None:
            results.append(val * 3)

        bus.on("calc", h1)
        bus.on("calc", h2)
        await bus.emit("calc", val=5)

        assert sorted(results) == [10, 15]

    @pytest.mark.asyncio
    async def test_emit_unknown_event_is_noop(self) -> None:
        bus = EventBus()
        await bus.emit("nonexistent", data="test")  # should not raise

    @pytest.mark.asyncio
    async def test_off_removes_handler(self) -> None:
        bus = EventBus()
        called = False

        async def handler() -> None:
            nonlocal called
            called = True

        bus.on("evt", handler)
        bus.off("evt", handler)
        await bus.emit("evt")

        assert called is False

    @pytest.mark.asyncio
    async def test_off_unknown_handler_is_noop(self) -> None:
        bus = EventBus()

        async def handler() -> None:
            pass

        bus.off("evt", handler)  # should not raise

    def test_handler_count(self) -> None:
        bus = EventBus()

        async def h1() -> None:
            pass

        async def h2() -> None:
            pass

        bus.on("a", h1)
        bus.on("a", h2)
        bus.on("b", h1)

        assert bus.handler_count == 3

    def test_clear(self) -> None:
        bus = EventBus()

        async def h() -> None:
            pass

        bus.on("a", h)
        bus.on("b", h)
        bus.clear()

        assert bus.handler_count == 0

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_break_others(self) -> None:
        bus = EventBus()
        results: list[str] = []

        async def bad_handler() -> None:
            raise ValueError("boom")

        async def good_handler() -> None:
            results.append("ok")

        bus.on("evt", bad_handler)
        bus.on("evt", good_handler)
        await bus.emit("evt")  # should not raise

        assert results == ["ok"]
