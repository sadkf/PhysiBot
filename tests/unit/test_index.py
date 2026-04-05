"""Unit tests for memory/index.py (MEMORY.md)."""

from __future__ import annotations

from pathlib import Path

from physi_core.memory.index import MemoryIndex


class TestMemoryIndex:
    def test_load_existing_index(self, tmp_path: Path) -> None:
        path = tmp_path / "MEMORY.md"
        path.write_text(
            "# 记忆索引\n\n## 用户身份\n测试用户，21岁\n\n## 偏好\n喜欢简洁\n",
            encoding="utf-8",
        )
        idx = MemoryIndex(path)
        assert idx.section_count == 2
        assert "测试用户" in (idx.get_section("用户身份") or "")

    def test_missing_file_starts_empty(self, tmp_path: Path) -> None:
        idx = MemoryIndex(tmp_path / "nonexistent.md")
        assert idx.section_count == 0

    def test_update_section_and_persist(self, tmp_path: Path) -> None:
        path = tmp_path / "MEMORY.md"
        idx = MemoryIndex(path)
        idx.update_section("用户身份", "→ identity/profile.jsonl\n东东，21岁")
        idx.update_section("偏好", "简洁回复")

        idx2 = MemoryIndex(path)
        assert idx2.section_count == 2
        assert "东东" in (idx2.get_section("用户身份") or "")

    def test_delete_section(self, tmp_path: Path) -> None:
        path = tmp_path / "MEMORY.md"
        idx = MemoryIndex(path)
        idx.update_section("test", "content")
        assert idx.delete_section("test") is True
        assert idx.delete_section("nonexistent") is False
        assert idx.section_count == 0

    def test_to_prompt_text(self, tmp_path: Path) -> None:
        path = tmp_path / "MEMORY.md"
        idx = MemoryIndex(path)
        idx.update_section("用户身份", "东东，21岁")
        idx.update_section("偏好", "简洁")

        text = idx.to_prompt_text()
        assert "记忆索引" in text
        assert "用户身份" in text
        assert "东东" in text

    def test_to_prompt_text_empty(self, tmp_path: Path) -> None:
        idx = MemoryIndex(tmp_path / "empty.md")
        assert idx.to_prompt_text() == ""

    def test_get_missing_section(self, tmp_path: Path) -> None:
        idx = MemoryIndex(tmp_path / "x.md")
        assert idx.get_section("nonexistent") is None
