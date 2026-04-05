"""Unit tests for memory/identity.py (L0)."""

from __future__ import annotations

from pathlib import Path

from physi_core.memory.identity import IdentityMemory


class TestIdentityMemory:
    def test_load_valid_profile(self, sample_identity: Path) -> None:
        mem = IdentityMemory(sample_identity)
        assert mem.get("name") == "测试用户"
        assert mem.get("age") == 21
        assert len(mem) == 4

    def test_get_missing_key_returns_default(self, sample_identity: Path) -> None:
        mem = IdentityMemory(sample_identity)
        assert mem.get("nonexistent") is None
        assert mem.get("nonexistent", "fallback") == "fallback"

    def test_set_and_persist(self, tmp_path: Path) -> None:
        path = tmp_path / "profile.jsonl"
        mem = IdentityMemory(path)
        mem.set("name", "东东")
        mem.set("age", 22)

        # Reload from disk
        mem2 = IdentityMemory(path)
        assert mem2.get("name") == "东东"
        assert mem2.get("age") == 22

    def test_delete_key(self, tmp_path: Path) -> None:
        path = tmp_path / "profile.jsonl"
        mem = IdentityMemory(path)
        mem.set("name", "test")
        assert mem.delete("name") is True
        assert mem.get("name") is None
        assert mem.delete("nonexistent") is False

    def test_missing_file_starts_empty(self, tmp_path: Path) -> None:
        mem = IdentityMemory(tmp_path / "nonexistent.jsonl")
        assert len(mem) == 0
        assert mem.all_keys() == []

    def test_all_keys(self, sample_identity: Path) -> None:
        mem = IdentityMemory(sample_identity)
        keys = mem.all_keys()
        assert "name" in keys
        assert "age" in keys

    def test_to_prompt_text(self, sample_identity: Path) -> None:
        mem = IdentityMemory(sample_identity)
        text = mem.to_prompt_text()
        assert "测试用户" in text
        assert "用户身份信息" in text

    def test_to_prompt_text_empty(self, tmp_path: Path) -> None:
        mem = IdentityMemory(tmp_path / "empty.jsonl")
        assert mem.to_prompt_text() == ""

    def test_invalid_json_lines_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.jsonl"
        path.write_text(
            '{"key":"name","value":"ok","updated":"2026"}\n'
            "invalid json\n"
            '{"key":"age","value":1,"updated":"2026"}\n',
            encoding="utf-8",
        )
        mem = IdentityMemory(path)
        assert mem.get("name") == "ok"
        assert mem.get("age") == 1
        assert len(mem) == 2
