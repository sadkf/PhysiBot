"""Unit tests for llm/response.py."""

from __future__ import annotations

from physi_core.llm.response import LLMResponse, TokenUsage, ToolCall


class TestTokenUsage:
    def test_total_tokens(self) -> None:
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150

    def test_defaults_to_zero(self) -> None:
        usage = TokenUsage()
        assert usage.total_tokens == 0


class TestToolCall:
    def test_str(self) -> None:
        tc = ToolCall(id="1", name="screenpipe_search", arguments={"query": "test"})
        assert "screenpipe_search" in str(tc)


class TestLLMResponse:
    def test_text_only_response(self) -> None:
        resp = LLMResponse(text="hello")
        assert resp.is_text_only is True
        assert resp.has_tool_calls() is False

    def test_tool_call_response(self) -> None:
        tc = ToolCall(id="1", name="search", arguments={})
        resp = LLMResponse(tool_calls=[tc])
        assert resp.is_text_only is False
        assert resp.has_tool_calls() is True

    def test_empty_response(self) -> None:
        resp = LLMResponse()
        assert resp.text is None
        assert resp.has_tool_calls() is False
        assert resp.is_text_only is False

    def test_thinking_field(self) -> None:
        resp = LLMResponse(text="answer", thinking="let me think...")
        assert resp.thinking == "let me think..."
        assert resp.is_text_only is True

    def test_frozen(self) -> None:
        resp = LLMResponse(text="hello")
        try:
            resp.text = "world"  # type: ignore[misc]
            assert False, "Should be frozen"
        except AttributeError:
            pass
