"""L0 Identity Memory — JSONL-based user profile storage."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class IdentityMemory:
    """Read/write user identity facts from a JSONL file.

    Each line: {"key": "name", "value": "东东", "updated": "2026-04-05"}
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load data from JSONL file."""
        if not self._path.exists():
            logger.info("Identity file not found at %s, starting empty", self._path)
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

    def to_prompt_text(self) -> str:
        """Format identity data for injection into LLM prompt."""
        if not self._data:
            return ""
        lines = ["## 用户身份信息"]
        for entry in self._data.values():
            lines.append(f"- {entry['key']}: {entry['value']}")
        return "\n".join(lines)

    def _save(self) -> None:
        """Persist to JSONL file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(entry, ensure_ascii=False) for entry in self._data.values()]
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def __len__(self) -> int:
        return len(self._data)
