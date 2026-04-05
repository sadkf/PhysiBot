"""Unit tests for agent/loop.py."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from physi_core.agent.loop import AgentLoop
from physi_core.agent.tools import PermissionLevel, ToolController
from physi_core.llm.response import LLMResponse, TokenUsage, ToolCall


def _make_mock_llm(responses: list[LLMResponse]) -> AsyncMock:
    """Create a mock LLM client that returns responses in order."""
    mock = AsyncMock()
    mock.chat = AsyncMock(side_effect=responses)
    return mock


async def _mock_search(query: str) -> str:
    return f"Results for: {query}"


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_simple_text_response(self) -> None:
        llm = _make_mock_llm([
            LLMResponse(text="你好东哥！", usage=TokenUsage(100, 50)),
        ])
        loop = AgentLoop(llm_client=llm, tool_controller=ToolController())
        result = await loop.run("你好")

        assert result.text == "你好东哥！"
        assert result.rounds == 1
        llm.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_tool_call_then_text(self) -> None:
        tc = ToolController()
        tc.register("search", "search", {}, _mock_search)

        llm = _make_mock_llm([
            # Round 1: tool call
            LLMResponse(
                tool_calls=[ToolCall(id="tc1", name="search", arguments={"query": "hello"})],
                usage=TokenUsage(200, 100),
            ),
            # Round 2: text response
            LLMResponse(text="找到了结果！", usage=TokenUsage(300, 50)),
        ])

        loop = AgentLoop(llm_client=llm, tool_controller=tc)
        result = await loop.run("搜索 hello")

        assert result.text == "找到了结果！"
        assert result.rounds == 2

    @pytest.mark.asyncio
    async def test_denied_tool_returns_error_message(self) -> None:
        tc = ToolController()
        tc.register("danger", "dangerous", {}, _mock_search, PermissionLevel.DENY)

        llm = _make_mock_llm([
            LLMResponse(
                tool_calls=[ToolCall(id="tc1", name="danger", arguments={"query": "x"})],
                usage=TokenUsage(100, 50),
            ),
            LLMResponse(text="好的，这个操作不允许。", usage=TokenUsage(200, 50)),
        ])

        loop = AgentLoop(llm_client=llm, tool_controller=tc)
        result = await loop.run("执行危险操作")
        assert result.text == "好的，这个操作不允许。"

    @pytest.mark.asyncio
    async def test_max_rounds_safety(self) -> None:
        """If LLM keeps calling tools, loop should terminate after MAX_TOOL_ROUNDS."""
        tc = ToolController()
        tc.register("loop_tool", "desc", {}, _mock_search)

        # Always return tool calls
        infinite_tc = LLMResponse(
            tool_calls=[ToolCall(id="tc", name="loop_tool", arguments={"query": "x"})],
            usage=TokenUsage(10, 10),
        )
        llm = _make_mock_llm([infinite_tc] * 20)

        loop = AgentLoop(llm_client=llm, tool_controller=tc)
        result = await loop.run("loop forever")

        assert "太长时间" in result.text
        assert result.rounds == 10  # MAX_TOOL_ROUNDS

    @pytest.mark.asyncio
    async def test_usage_tracking(self) -> None:
        llm = _make_mock_llm([
            LLMResponse(text="hi", usage=TokenUsage(100, 50)),
        ])
        loop = AgentLoop(llm_client=llm, tool_controller=ToolController())
        result = await loop.run("test")

        assert result.total_usage["input_tokens"] == 100
        assert result.total_usage["output_tokens"] == 50
