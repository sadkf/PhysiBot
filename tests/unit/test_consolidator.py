"""Unit tests for memory/consolidator.py.

The Consolidator uses LLM tool calls (not text parsing), so mocks must return
LLMResponse objects that carry ToolCall objects.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from physi_core.llm.response import LLMResponse, TokenUsage, ToolCall
from physi_core.memory.consolidator import Consolidator, SegmentResult
from physi_core.memory.identity import IdentityMemory
from physi_core.memory.index import MemoryIndex
from physi_core.memory.long_term import LongTermMemory
from physi_core.memory.mid_term import MidTermMemory


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tool_response(name: str, args: dict) -> LLMResponse:
    """LLM response that contains exactly one tool call."""
    return LLMResponse(
        tool_calls=[ToolCall(id="mock_1", name=name, arguments=args)],
        usage=TokenUsage(100, 50),
    )


def _text_response(text: str = "done") -> LLMResponse:
    """LLM response with no tool calls (signals loop termination)."""
    return LLMResponse(text=text, usage=TokenUsage(50, 20))


def _mock_llm(*responses: LLMResponse) -> AsyncMock:
    """Return a mock LLM whose .chat() cycles through the given responses."""
    mock = AsyncMock()
    mock.chat = AsyncMock(side_effect=list(responses))
    return mock


@pytest.fixture
def mem_stack(tmp_path: Path):
    mid = MidTermMemory(tmp_path / "mid_term")
    lt  = LongTermMemory(tmp_path / "memory")
    idx = MemoryIndex(tmp_path / "MEMORY.md")
    return mid, lt, idx


# ── Segment summarize ──────────────────────────────────────────────────────────

class TestSegmentSummarize:
    @pytest.mark.asyncio
    async def test_basic_summarize(self, mem_stack) -> None:
        mid, lt, idx = mem_stack
        llm = _mock_llm(_tool_response("write_segment", {
            "summary": "## 主要活动\n编码中\n## 应用使用\nVSCode: 25min",
            "should_notify": False,
            "notify_message": "",
        }))
        c = Consolidator(llm, mid, lt, idx)

        result = await c.summarize_segment("OCR data...", "14:30", 1.5)

        assert isinstance(result, SegmentResult)
        assert "编码中" in result.summary
        assert result.should_notify is False

    @pytest.mark.asyncio
    async def test_summarize_with_notify(self, mem_stack) -> None:
        mid, lt, idx = mem_stack
        llm = _mock_llm(_tool_response("write_segment", {
            "summary": "## 主要活动\n编码中",
            "should_notify": True,
            "notify_message": "闻，你已经连续编码3小时了，休息一下吧",
        }))
        c = Consolidator(llm, mid, lt, idx)

        result = await c.summarize_segment("data", "16:00", 3.0)

        assert result.should_notify is True
        assert "休息" in result.notify_message

    @pytest.mark.asyncio
    async def test_summarize_structured_fields(self, mem_stack) -> None:
        mid, lt, idx = mem_stack
        llm = _mock_llm(_tool_response("write_segment", {
            "summary": "正在修复 PhysiBot 启动脚本",
            "should_notify": False,
            "notify_message": "",
            "active_projects": ["PhysiBot"],
            "learning_topics": ["PowerShell download debug"],
            "metadata_updates": [{"key": "project", "value": "PhysiBot"}],
        }))
        c = Consolidator(llm, mid, lt, idx)

        result = await c.summarize_segment("data", "16:00", 1.0)

        assert result.active_projects == ["PhysiBot"]
        assert result.learning_topics == ["PowerShell download debug"]
        assert result.metadata_updates == [{"key": "project", "value": "PhysiBot"}]


# ── Daily merge ───────────────────────────────────────────────────────────────

class TestDailyMerge:
    @pytest.mark.asyncio
    async def test_merge_segments_into_daily(self, mem_stack) -> None:
        mid, lt, idx = mem_stack
        mid.write_segment("segA", datetime(2026, 4, 5, 9, 0, tzinfo=UTC))
        mid.write_segment("segB", datetime(2026, 4, 5, 9, 30, tzinfo=UTC))

        llm = _mock_llm(_tool_response("write_daily_summary", {
            "summary": "# 2026-04-05 日报\n今天写了代码",
            "recyclable_files": ["2026-04-05_0900.md", "2026-04-05_0930.md"],
        }))
        c = Consolidator(llm, mid, lt, idx)

        result = await c.merge_daily("2026-04-05")

        assert "日报" in result.summary
        assert len(result.recyclable) == 2
        assert mid.read_daily("2026-04-05") is not None

    @pytest.mark.asyncio
    async def test_merge_empty_day(self, mem_stack) -> None:
        mid, lt, idx = mem_stack
        llm = _mock_llm()   # no calls expected
        c = Consolidator(llm, mid, lt, idx)

        result = await c.merge_daily("2026-04-05")
        assert result.summary == ""
        assert result.recyclable == []


# ── Session extraction ─────────────────────────────────────────────────────────

class TestSessionExtract:
    @pytest.mark.asyncio
    async def test_extract_new_info(self, mem_stack) -> None:
        mid, lt, idx = mem_stack
        lt.write_topic("portrait", "# 画像\n程序员")

        # tool_loop: first call writes, second call has no tools → stops
        llm = _mock_llm(
            _tool_response("memory_write", {
                "topic": "portrait",
                "content": "开始学习 Rust",
                "action": "append",
            }),
            _text_response("已完成"),
        )
        c = Consolidator(llm, mid, lt, idx)

        count = await c.extract_from_session("用户: 我开始学 Rust 了")

        assert count == 1
        assert "Rust" in (lt.read_topic("portrait") or "")

    @pytest.mark.asyncio
    async def test_extract_no_updates(self, mem_stack) -> None:
        mid, lt, idx = mem_stack
        # LLM returns no tool call immediately → write_count stays 0
        llm = _mock_llm(_text_response("没有新信息"))
        c = Consolidator(llm, mid, lt, idx)

        count = await c.extract_from_session("用户: 你好")
        assert count == 0

    @pytest.mark.asyncio
    async def test_extract_refreshes_index(self, mem_stack) -> None:
        mid, lt, idx = mem_stack
        lt.write_topic("projects", "# 项目")

        llm = _mock_llm(
            _tool_response("memory_write", {
                "topic": "projects",
                "content": "PhysiBot 已完成核心功能",
                "action": "append",
            }),
            _text_response(),
        )
        c = Consolidator(llm, mid, lt, idx)
        await c.extract_from_session("今天完成了 PhysiBot 核心功能")

        # Index should be refreshed after extraction writes
        index_text = idx.to_prompt_text()
        assert "projects" in index_text

    @pytest.mark.asyncio
    async def test_extract_can_write_identity(self, mem_stack, tmp_path: Path) -> None:
        mid, lt, idx = mem_stack
        identity = IdentityMemory(tmp_path / "identity" / "profile.jsonl")
        llm = _mock_llm(
            _tool_response("identity_set", {"key": "project", "value": "PhysiBot"}),
            _text_response("done"),
        )
        c = Consolidator(llm, mid, lt, idx, identity)
        count = await c.extract_from_session("用户: 我现在在做 PhysiBot")
        assert count == 1
        assert identity.get("project") == "PhysiBot"
