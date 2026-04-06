"""L0 Metadata Memory — JSONL-based user profile storage."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class IdentityMemory:
    """Read/write user metadata facts from a JSONL file.

    Each line: {"key": "name", "value": "东东", "updated": "2026-04-05"}
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load data from JSONL file."""
        if not self._path.exists():
            logger.info("Metadata file not found at %s, starting empty", self._path)
            return

        for line_num, line in enumerate(
            self._path.read_text(encoding="utf-8").strip().split("\n"), 1
        ):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if "key" in entry:
                    self._data[entry["key"]] = entry
            except json.JSONDecodeError:
                logger.warning("Skipping invalid JSON at line %d in %s", line_num, self._path)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value by key."""
        entry = self._data.get(key)
        return entry["value"] if entry else default

    def set(self, key: str, value: Any) -> None:
        """Set a value and persist."""
        self._data[key] = {
            "key": key,
            "value": value,
            "updated": datetime.now(UTC).strftime("%Y-%m-%d"),
        }
        self._save()

    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if key existed."""
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def all_keys(self) -> list[str]:
        """Return all stored keys."""
        return list(self._data.keys())

    # 分类键名映射（用于 to_prompt_text 分组展示）
    _CATEGORIES: dict[str, list[str]] = {
        "基本信息": ["name", "nickname", "call_me", "age", "gender", "occupation", "language", "timezone"],
        "作息偏好": ["wakeup_time", "sleep_time", "pet_peeve"],
        "账号 & 联系方式": ["qq_number", "wechat", "email", "github", "bilibili", "douyin", "twitter"],
        "服务器 & 基础设施": ["ssh_host", "ssh_user", "server_location", "server_os", "nas_host"],
    }

    def to_prompt_text(self) -> str:
        """Format metadata for injection into LLM prompt, grouped by category."""
        if not self._data:
            return ""
        used: set[str] = set()
        sections: list[str] = []

        for category, keys in self._CATEGORIES.items():
            items = [(k, self._data[k]["value"]) for k in keys if k in self._data]
            if items:
                sections.append(f"**{category}**")
                for k, v in items:
                    sections.append(f"- {k}: {v}")
                used.update(k for k, _ in items)

        # 剩余未分类的 key
        remaining = [(k, e["value"]) for k, e in self._data.items() if k not in used]
        if remaining:
            sections.append("**其他**")
            for k, v in remaining:
                sections.append(f"- {k}: {v}")

        return "\n".join(sections)

    def _save(self) -> None:
        """Persist to JSONL file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(entry, ensure_ascii=False) for entry in self._data.values()]
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def __len__(self) -> int:
        return len(self._data)
