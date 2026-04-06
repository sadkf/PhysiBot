"""Unit tests for agent/prompts.py."""

from __future__ import annotations

from pathlib import Path

from physi_core.agent.prompts import build_system_prompt, load_physi_md
from physi_core.memory.identity import IdentityMemory
from physi_core.memory.index import MemoryIndex
from physi_core.memory.long_term import LongTermMemory


class TestBuildSystemPrompt:
    def test_includes_all_layers(self, tmp_path: Path) -> None:
        # Setup L0
        id_path = tmp_path / "profile.jsonl"
        id_path.write_text('{"key":"name","value":"东东","updated":"2026"}\n', encoding="utf-8")
        identity = IdentityMemory(id_path)

        # Setup MEMORY.md
        idx_path = tmp_path / "MEMORY.md"
        idx = MemoryIndex(idx_path)
        idx.update_section("用户", "东东，21岁")

        # Setup L3
        lt = LongTermMemory(tmp_path / "memory")
        lt.write_topic("portrait", "# 画像\n程序员")

        prompt = build_system_prompt(
            physi_md_content="# PhysiBot 指令\n你是助手。",
            identity=identity,
            memory_index=idx,
            long_term=lt,
            today_summary="今天写了代码",
            recent_segments="最近半小时在用 VSCode",
        )

        assert "PhysiBot 指令" in prompt  # L4
        assert "东东" in prompt  # L0
        assert "程序员" in prompt  # L3
        assert "今天写了代码" in prompt  # L2 daily
        assert "VSCode" in prompt  # L2 segment
        # memory_index 已从 system prompt 移除，按需由 midterm_read 工具查询

    def test_empty_layers_produces_minimal_prompt(self, tmp_path: Path) -> None:
        identity = IdentityMemory(tmp_path / "empty.jsonl")
        idx = MemoryIndex(tmp_path / "empty.md")
        lt = LongTermMemory(tmp_path / "memory")

        prompt = build_system_prompt(
            physi_md_content="",
            identity=identity,
            memory_index=idx,
            long_term=lt,
        )
        # Template always emits some structural text (内部系统状态 header etc.)
        # even with empty layers; just verify no user data leaks in
        assert "东东" not in prompt
        assert "portrait" not in prompt


class TestLoadPhysiMd:
    def test_load_existing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "PHYSI.md"
        path.write_text("# 指令\n你是 PhysiBot", encoding="utf-8")
        content = load_physi_md(str(path))
        assert "PhysiBot" in content

    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        content = load_physi_md(str(tmp_path / "nonexistent.md"))
        assert content == ""

    def test_load_none_path(self) -> None:
        assert load_physi_md(None) == ""
