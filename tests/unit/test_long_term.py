"""Unit tests for memory/long_term.py (L3)."""

from __future__ import annotations

from pathlib import Path

from physi_core.memory.long_term import LongTermMemory


class TestLongTermMemory:
    def test_write_and_read_topic(self, tmp_path: Path) -> None:
        mem = LongTermMemory(tmp_path / "memory")
        mem.write_topic("portrait", "# 用户画像\n\n程序员，21岁")
        content = mem.read_topic("portrait")
        assert content is not None
        assert "程序员" in content

    def test_read_nonexistent_topic(self, tmp_path: Path) -> None:
        mem = LongTermMemory(tmp_path / "memory")
        assert mem.read_topic("nonexistent") is None

    def test_append_to_topic(self, tmp_path: Path) -> None:
        mem = LongTermMemory(tmp_path / "memory")
        mem.write_topic("preferences", "喜欢简洁")
        mem.append_to_topic("preferences", "不喜欢表情包")
        content = mem.read_topic("preferences")
        assert content is not None
        assert "简洁" in content
        assert "表情包" in content

    def test_list_topics(self, tmp_path: Path) -> None:
        mem = LongTermMemory(tmp_path / "memory")
        mem.write_topic("portrait", "content")
        mem.write_topic("routines", "content")
        topics = mem.list_topics()
        assert "portrait" in topics
        assert "routines" in topics

    def test_read_all(self, tmp_path: Path) -> None:
        mem = LongTermMemory(tmp_path / "memory")
        mem.write_topic("a", "content a")
        mem.write_topic("b", "content b")
        all_data = mem.read_all()
        assert len(all_data) == 2
        assert all_data["a"] == "content a"

    def test_delete_topic(self, tmp_path: Path) -> None:
        mem = LongTermMemory(tmp_path / "memory")
        mem.write_topic("temp", "temp content")
        assert mem.delete_topic("temp") is True
        assert mem.delete_topic("temp") is False
        assert mem.read_topic("temp") is None

    def test_to_prompt_text(self, tmp_path: Path) -> None:
        mem = LongTermMemory(tmp_path / "memory")
        mem.write_topic("portrait", "# 画像\n程序员")
        text = mem.to_prompt_text("portrait")
        assert "程序员" in text

    def test_to_prompt_text_nonexistent(self, tmp_path: Path) -> None:
        mem = LongTermMemory(tmp_path / "memory")
        assert mem.to_prompt_text("nonexistent") == ""
