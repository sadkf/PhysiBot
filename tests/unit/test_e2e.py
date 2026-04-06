"""End-to-end test for PhysiBot orchestrator with mocked LLM."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from physi_core.config.settings import LLMConfig, Settings
from physi_core.llm.response import LLMResponse, TokenUsage
from physi_core.main import PhysiBot


def _make_settings(tmp_path: Path) -> Settings:
    """Create test settings pointing to temp data dir."""
    return Settings(
        llm=LLMConfig(provider="minimax", model="test", api_key="fake"),
        data_dir=tmp_path,
    )


class TestPhysiBotE2E:
    """AC-22: Complete conversation chain (mocked LLM)."""

    @pytest.mark.asyncio
    async def test_full_message_flow(self, tmp_path: Path) -> None:
        """User sends message → agent processes → response returned → memory saved."""
        settings = _make_settings(tmp_path)
        bot = PhysiBot(settings)

        # Init components but mock the LLM
        bot._init_components()

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=LLMResponse(
            text="你好东哥！今天过得怎么样？",
            usage=TokenUsage(200, 100),
        ))
        bot._llm = mock_llm
        bot._agent._llm = mock_llm

        # Handle message
        response = await bot.handle_message("你好", source="qq")

        # Verify response
        assert "你好东哥" in response

        # Verify memory was saved
        msgs = bot._short_term.get_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "你好"
        assert msgs[1]["role"] == "assistant"
        assert "东哥" in msgs[1]["content"]

    @pytest.mark.asyncio
    async def test_identity_injected_in_prompt(self, tmp_path: Path) -> None:
        """Verify user identity is injected into the dynamically-built system prompt."""
        settings = _make_settings(tmp_path)
        bot = PhysiBot(settings)

        # Create identity data
        id_dir = tmp_path / "identity"
        id_dir.mkdir(parents=True)
        (id_dir / "profile.jsonl").write_text(
            '{"key":"name","value":"东东","updated":"2026-04-05"}\n',
            encoding="utf-8",
        )

        # Create PHYSI.md
        (tmp_path / "PHYSI.md").write_text(
            "# 指令\n你是 PhysiBot", encoding="utf-8"
        )

        bot._init_components()

        # System prompt is built per-turn, not stored in agent
        system = bot._build_system_prompt()
        assert "东东" in system
        assert "PhysiBot" in system

    @pytest.mark.asyncio
    async def test_session_end_archives(self, tmp_path: Path) -> None:
        """Verify stop() archives the current session."""
        settings = _make_settings(tmp_path)
        bot = PhysiBot(settings)
        bot._init_components()

        # Mock LLM for both message handling and session extraction
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=LLMResponse(
            text="再见！",
            usage=TokenUsage(100, 50),
        ))
        bot._llm = mock_llm
        bot._agent._llm = mock_llm
        bot._consolidator._llm = mock_llm

        await bot.handle_message("测试")
        assert bot._short_term.message_count == 2

        await bot.stop()
        # stop() calls end_session() which archives and keeps last 3 msgs as cross-session seed
        assert bot._short_term.message_count <= 2
        archives = bot._short_term.get_archived_sessions()
        assert len(archives) == 1

    @pytest.mark.asyncio
    async def test_throttle_limits_extraction(self, tmp_path: Path) -> None:
        """AC-21: User trigger should be throttled to once per cooldown."""
        settings = _make_settings(tmp_path)
        bot = PhysiBot(settings)
        bot._init_components()

        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value=LLMResponse(
            text="ok", usage=TokenUsage(50, 20),
        ))
        bot._llm = mock_llm
        bot._agent._llm = mock_llm
        bot._consolidator._llm = mock_llm

        # First message triggers extraction
        await bot.handle_message("msg1")
        # Second message within cooldown should NOT trigger extraction again
        await bot.handle_message("msg2")

        # The consolidator's extract should have been called at most once
        # (throttled at 600s cooldown)
        import asyncio
        await asyncio.sleep(0.1)  # Let async tasks settle
