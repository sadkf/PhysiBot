"""Unit tests for memory/consolidator.py."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from physi_core.llm.response import LLMResponse, TokenUsage
from physi_core.memory.consolidator import Consolidator, SegmentResult
from physi_core.memory.index import MemoryIndex
from physi_core.memory.long_term import LongTermMemory
from physi_core.memory.mid_term import MidTermMemory


def _mock_llm(text: str) -> AsyncMock:
    mock = AsyncMock()
    mock.chat = AsyncMock(return_value=LLMResponse(
        text=text, usage=TokenUsage(100, 50),
    ))
    return mock


@pytest.fixture
def mem_stack(tmp_path: Path):
    """Create all memory components for consolidator tests."""
    mid = MidTermMemory(tmp_path / "mid_term")
    lt = LongTermMemory(tmp_path / "memory")
    idx = MemoryIndex(tmp_path / "MEMORY.md")
    return mid, lt, idx


class TestSegmentSummarize:
    @pytest.mark.asyncio
    async def test_basic_summarize(self, mem_stack) -> None:
        mid, lt, idx = mem_stack
        llm = _mock_llm("## 主要活动\n编码中\n## 应用使用\nVSCode: 25min\nNOTIFY: NO")
        c = Consolidator(llm, mid, lt, idx)

        result = await c.summarize_segment("OCR data...", "14:30", 1.5)

        assert isinstance(result, SegmentResult)
        assert "编码中" in result.summary
        assert result.should_notify is False

    @pytest.mark.asyncio
    async def test_summarize_with_notify(self, mem_stack) -> None:
        mid, lt, idx = mem_stack
        llm = _mock_llm("用户已经连续编码3小时了\nNOTIFY: YES")
        c = Consolidator(llm, mid, lt, idx)

        result = await c.summarize_segment("data", "16:00", 3.0)

        assert result.should_notify is True


class TestDailyMerge:
    @pytest.mark.asyncio
    async def test_merge_segments_into_daily(self, mem_stack) -> None:
        mid, lt, idx = mem_stack
        from datetime import datetime

        # Create segments
        mid.write_segment("segA", datetime(2026, 4, 5, 9, 0, tzinfo=UTC))
        mid.write_segment("segB", datetime(2026, 4, 5, 9, 30, tzinfo=UTC))

        llm = _mock_llm(
            "# 2026-04-05 日报\n今天写了代码\n"
            "RECYCLABLE: 2026-04-05_0900.md, 2026-04-05_0930.md"
        )
        c = Consolidator(llm, mid, lt, idx)

        result = await c.merge_daily("2026-04-05")

        assert "日报" in result.summary
        assert len(result.recyclable) == 2
        # Daily file should be written
        assert mid.read_daily("2026-04-05") is not None

    @pytest.mark.asyncio
    async def test_merge_empty_day(self, mem_stack) -> None:
        mid, lt, idx = mem_stack
        llm = _mock_llm("")
        c = Consolidator(llm, mid, lt, idx)

        result = await c.merge_daily("2026-04-05")
        assert result.summary == ""
        assert result.recyclable == []


class TestSessionExtract:
    @pytest.mark.asyncio
    async def test_extract_new_info(self, mem_stack) -> None:
        mid, lt, idx = mem_stack
        lt.write_topic("portrait", "# 画像\n程序员")

        llm = _mock_llm(
            '{"updates": [{"topic": "portrait", "action": "append", '
            '"content": "开始学习 Rust"}]}'
        )
        c = Consolidator(llm, mid, lt, idx)

        updates = await c.extract_from_session("用户: 我开始学 Rust 了")

        assert len(updates) == 1
        assert "Rust" in (lt.read_topic("portrait") or "")

    @pytest.mark.asyncio
    async def test_extract_no_updates(self, mem_stack) -> None:
        mid, lt, idx = mem_stack
        llm = _mock_llm('{"updates": []}')
        c = Consolidator(llm, mid, lt, idx)

        updates = await c.extract_from_session("用户: 你好")
        assert updates == []


class TestParseJson:
    def test_parse_direct_json(self) -> None:
        text = '{"updates": [{"topic": "test", "action": "append", "content": "hi"}]}'
        result = Consolidator._parse_json_updates(text)
        assert len(result) == 1

    def test_parse_json_in_markdown(self) -> None:
        text = (
            "Here's the result:\n```json\n"
            '{"updates": [{"topic": "a", "action": "append", "content": "b"}]}'
            "\n```"
        )
        result = Consolidator._parse_json_updates(text)
        assert len(result) == 1

    def test_parse_invalid_json(self) -> None:
        result = Consolidator._parse_json_updates("no json here")
        assert result == []

    def test_parse_json_with_surrounding_text(self) -> None:
        text = 'Based on analysis, {\"updates\": []} is the result.'
        result = Consolidator._parse_json_updates(text)
        assert result == []
