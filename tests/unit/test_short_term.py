"""Unit tests for memory/short_term.py (L1)."""

from __future__ import annotations

from pathlib import Path

from physi_core.memory.short_term import ShortTermMemory


class TestShortTermMemory:
    def test_add_and_get_messages(self, tmp_path: Path) -> None:
        mem = ShortTermMemory(tmp_path / "short_term")
        mem.add_message("user", "你好")
        mem.add_message("assistant", "你好东哥！")

        msgs = mem.get_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "你好"
        assert msgs[1]["role"] == "assistant"

    def test_message_has_timestamp(self, tmp_path: Path) -> None:
        mem = ShortTermMemory(tmp_path / "st")
        mem.add_message("user", "test")
        assert "ts" in mem.get_messages()[0]

    def test_thinking_and_tool_calls_recorded(self, tmp_path: Path) -> None:
        mem = ShortTermMemory(tmp_path / "st")
        mem.add_message(
            "assistant",
            thinking="let me think...",
            tool_calls=[{"name": "search", "args": {"q": "test"}}],
        )
        msg = mem.get_messages()[0]
        assert msg["thinking"] == "let me think..."
        assert msg["tool_calls"][0]["name"] == "search"

    def test_tool_result_recorded(self, tmp_path: Path) -> None:
        mem = ShortTermMemory(tmp_path / "st")
        mem.add_message("tool", tool_name="search", tool_result="found 5 results")
        msg = mem.get_messages()[0]
        assert msg["role"] == "tool"
        assert msg["name"] == "search"
        assert msg["result"] == "found 5 results"

    def test_persistence_across_reload(self, tmp_path: Path) -> None:
        d = tmp_path / "st"
        mem1 = ShortTermMemory(d)
        mem1.add_message("user", "first")
        mem1.add_message("assistant", "second")

        mem2 = ShortTermMemory(d)
        assert mem2.message_count == 2
        assert mem2.get_messages()[0]["content"] == "first"

    def test_end_session_archives(self, tmp_path: Path) -> None:
        d = tmp_path / "st"
        mem = ShortTermMemory(d)
        mem.add_message("user", "hello")
        mem.end_session()

        assert mem.message_count == 0
        archives = mem.get_archived_sessions()
        assert len(archives) == 1

    def test_get_messages_for_llm(self, tmp_path: Path) -> None:
        mem = ShortTermMemory(tmp_path / "st")
        mem.add_message("user", "你好")
        mem.add_message("assistant", "嗨！")

        llm_msgs = mem.get_messages_for_llm()
        assert llm_msgs == [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "嗨！"},
        ]

    def test_message_count(self, tmp_path: Path) -> None:
        mem = ShortTermMemory(tmp_path / "st")
        assert mem.message_count == 0
        mem.add_message("user", "one")
        assert mem.message_count == 1
