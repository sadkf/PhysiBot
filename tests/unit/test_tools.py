"""Unit tests for agent/tools.py."""

from __future__ import annotations

import pytest

from physi_core.agent.tools import PermissionLevel, ToolController


async def mock_search(query: str) -> str:
    return f"Found results for: {query}"


async def mock_ha_control(entity_id: str, action: str) -> str:
    return f"Executed {action} on {entity_id}"


async def mock_failing_tool() -> str:
    raise RuntimeError("Device offline")


class TestToolController:
    def test_register_and_list(self) -> None:
        tc = ToolController()
        tc.register("search", "Search screen", {"type": "object"}, mock_search)
        assert tc.tool_count == 1
        assert "search" in tc.list_tools()

    def test_get_tool(self) -> None:
        tc = ToolController()
        tc.register("search", "desc", {}, mock_search)
        tool = tc.get_tool("search")
        assert tool is not None
        assert tool.name == "search"

    def test_get_unknown_tool(self) -> None:
        tc = ToolController()
        assert tc.get_tool("nonexistent") is None

    @pytest.mark.asyncio
    async def test_execute_safe_tool(self) -> None:
        tc = ToolController()
        tc.register("search", "desc", {}, mock_search)
        result = await tc.execute("search", {"query": "test"})
        assert result.success is True
        assert "Found results for: test" in result.output

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self) -> None:
        tc = ToolController()
        result = await tc.execute("nonexistent", {})
        assert result.success is False
        assert "Unknown tool" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_denied_tool(self) -> None:
        tc = ToolController()
        tc.register("danger", "desc", {}, mock_search, PermissionLevel.DENY)
        result = await tc.execute("danger", {"query": "x"})
        assert result.success is False
        assert "denied" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_execute_failing_tool_catches_error(self) -> None:
        tc = ToolController()
        tc.register("fail", "desc", {}, mock_failing_tool)
        result = await tc.execute("fail", {})
        assert result.success is False
        assert "offline" in (result.error or "")

    def test_is_dangerous(self) -> None:
        # Permission confirmation is currently disabled; all tools are treated as safe.
        tc = ToolController()
        tc.register("safe", "desc", {}, mock_search, PermissionLevel.SAFE)
        tc.register("confirm", "desc", {}, mock_ha_control, PermissionLevel.CONFIRM)
        assert tc.is_dangerous("safe") is False
        assert tc.is_dangerous("confirm") is False
        assert tc.is_dangerous("unknown") is False

    def test_is_denied(self) -> None:
        tc = ToolController()
        tc.register("blocked", "desc", {}, mock_search, PermissionLevel.DENY)
        tc.register("safe", "desc", {}, mock_search, PermissionLevel.SAFE)
        assert tc.is_denied("blocked") is True
        assert tc.is_denied("safe") is False

    def test_get_all_schemas(self) -> None:
        tc = ToolController()
        tc.register(
            "search",
            "Search stuff",
            {"type": "object", "properties": {"q": {"type": "string"}}},
            mock_search,
        )
        schemas = tc.get_all_schemas()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "search"
