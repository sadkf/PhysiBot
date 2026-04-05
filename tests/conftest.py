"""PhysiBot test configuration and shared fixtures."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary physi-data directory structure."""
    dirs = [
        "identity",
        "memory",
        "short_term",
        "mid_term/segments",
        "mid_term/daily",
        "mid_term/weekly",
    ]
    for d in dirs:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def sample_identity(tmp_data_dir: Path) -> Path:
    """Create a sample identity profile JSONL file."""
    profile_path = tmp_data_dir / "identity" / "profile.jsonl"
    entries = [
        {"key": "name", "value": "测试用户", "updated": "2026-04-05"},
        {"key": "nickname", "value": "小测", "updated": "2026-04-05"},
        {"key": "age", "value": 21, "updated": "2026-04-05"},
        {"key": "language", "value": "中文", "updated": "2026-04-05"},
    ]
    profile_path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n",
        encoding="utf-8",
    )
    return profile_path


@pytest.fixture
def sample_physi_md(tmp_data_dir: Path) -> Path:
    """Create a sample PHYSI.md instruction file."""
    physi_path = tmp_data_dir / "PHYSI.md"
    physi_path.write_text(
        "# PhysiBot 系统指令\n\n## 你是谁\n你是 PhysiBot。\n",
        encoding="utf-8",
    )
    return physi_path


@pytest.fixture
def sample_memory_md(tmp_data_dir: Path) -> Path:
    """Create a sample MEMORY.md index file."""
    memory_path = tmp_data_dir / "MEMORY.md"
    memory_path.write_text(
        "# 记忆索引\n\n## 用户身份\n→ identity/profile.jsonl\n测试用户，21岁\n",
        encoding="utf-8",
    )
    return memory_path
