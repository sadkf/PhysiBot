"""Integration test: real MiniMax API call."""

from __future__ import annotations

from pathlib import Path

import pytest

from physi_core.config.settings import load_settings
from physi_core.llm.adapter import LLMClient

# Resolve config path relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "physi-data" / "config.yaml"


@pytest.mark.integration
class TestMiniMaxIntegration:
    """Tests that actually call the MiniMax API. Run with: pytest -m integration"""

    @pytest.fixture
    def llm_client(self) -> LLMClient:
        if not CONFIG_PATH.exists():
            pytest.skip(f"Config not found: {CONFIG_PATH}")
        settings = load_settings(CONFIG_PATH)
        if (
            not settings.llm.api_key
            or settings.llm.api_key == "your-api-key-here"
        ):
            pytest.skip("No API key configured")
        return LLMClient(settings.llm)

    @pytest.mark.asyncio
    async def test_simple_chat(self, llm_client: LLMClient) -> None:
        """Basic chat completion works."""
        response = await llm_client.chat(
            messages=[{"role": "user", "content": "说一个字"}],
            max_tokens=10,
        )
        assert response.text is not None
        assert len(response.text) > 0
        assert response.usage.total_tokens > 0
        print(f"\n  ✅ Response: {response.text}")
        print(f"  📊 Tokens: {response.usage.total_tokens}")

    @pytest.mark.asyncio
    async def test_chat_with_system(self, llm_client: LLMClient) -> None:
        """System prompt injection works."""
        response = await llm_client.chat(
            messages=[{"role": "user", "content": "你叫什么？"}],
            system="你是 PhysiBot，一个私人 AI 助手。请用一句话回答。",
            max_tokens=100,
        )
        assert response.text is not None
        print(f"\n  ✅ Response: {response.text}")

    @pytest.mark.asyncio
    async def test_chat_with_tools(self, llm_client: LLMClient) -> None:
        """Tool calling works."""
        tools = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取天气信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名",
                        },
                    },
                    "required": ["city"],
                },
            },
        }]
        response = await llm_client.chat(
            messages=[
                {"role": "user", "content": "北京今天天气怎么样？"},
            ],
            tools=tools,
            max_tokens=200,
        )
        assert response.has_tool_calls() or response.text is not None
        if response.has_tool_calls():
            print(f"\n  🔧 Tool call: {response.tool_calls[0]}")
        else:
            print(f"\n  ✅ Response: {response.text}")
