"""MEMORY.md index management — lightweight pointer to all memory layers."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Max lines for the index to stay within ~500 tokens
MAX_INDEX_LINES = 40


class MemoryIndex:
    """Manages the MEMORY.md index file — a lightweight routing table for all memories."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._sections: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        """Parse MEMORY.md into sections."""
        if not self._path.exists():
            return

        content = self._path.read_text(encoding="utf-8")
        current_key = ""
        current_lines: list[str] = []

        for line in content.split("\n"):
            if line.startswith("## "):
                if current_key:
                    self._sections[current_key] = "\n".join(current_lines).strip()
                current_key = line[3:].strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_key:
            self._sections[current_key] = "\n".join(current_lines).strip()

    def get_section(self, key: str) -> str | None:
        """Get the content of a section by its heading."""
        return self._sections.get(key)

    def update_section(self, key: str, content: str) -> None:
        """Update or create a section and persist."""
        self._sections[key] = content.strip()
        self._save()

    def delete_section(self, key: str) -> bool:
        """Delete a section. Returns True if it existed."""
        if key in self._sections:
            del self._sections[key]
            self._save()
            return True
        return False

    def to_prompt_text(self) -> str:
        """Render the full index as text for LLM prompt injection."""
        if not self._sections:
            return ""
        header = "> 以下是你对用户的了解的摘要。详细信息在各主题文件中，按需读取。"
        lines = ["# 记忆索引", "", header]
        for key, content in self._sections.items():
            lines.append(f"\n## {key}")
            lines.append(content)
        return "\n".join(lines)

    @property
    def section_count(self) -> int:
        return len(self._sections)

    @property
    def total_lines(self) -> int:
        """Approximate line count of the rendered index."""
        return len(self.to_prompt_text().split("\n"))

    def _save(self) -> None:
        """Persist to MEMORY.md."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(self.to_prompt_text() + "\n", encoding="utf-8")
