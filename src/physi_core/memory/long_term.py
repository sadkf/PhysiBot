"""L3 Long-Term Memory — persistent user portrait in Markdown topic files."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class LongTermMemory:
    """Manages L3 long-term user portrait stored as multiple .md topic files."""

    # Default topic files
    DEFAULT_TOPICS = [
        "portrait",
        "preferences",
        "routines",
        "skills_interests",
        "social",
        "health",
        "work_projects",
        "emotional_patterns",
        "iot_preferences",
    ]

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)

    def read_topic(self, topic: str) -> str | None:
        """Read a topic file's content. Returns None if file doesn't exist."""
        path = self._dir / f"{topic}.md"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def write_topic(self, topic: str, content: str) -> None:
        """Write/overwrite a topic file."""
        path = self._dir / f"{topic}.md"
        path.write_text(content, encoding="utf-8")
        logger.info("Updated L3 topic: %s (%d chars)", topic, len(content))

    def append_to_topic(self, topic: str, content: str) -> None:
        """Append content to a topic file."""
        path = self._dir / f"{topic}.md"
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(existing.rstrip() + "\n\n" + content + "\n", encoding="utf-8")

    def list_topics(self) -> list[str]:
        """List all existing topic file names (without .md extension)."""
        return sorted(p.stem for p in self._dir.glob("*.md"))

    def read_all(self) -> dict[str, str]:
        """Read all topic files into a dict."""
        result = {}
        for path in sorted(self._dir.glob("*.md")):
            result[path.stem] = path.read_text(encoding="utf-8")
        return result

    def to_prompt_text(self, topic: str = "portrait") -> str:
        """Load a specific topic for prompt injection. Default: portrait."""
        content = self.read_topic(topic)
        if not content:
            return ""
        return content

    def delete_topic(self, topic: str) -> bool:
        """Delete a topic file. Returns True if it existed."""
        path = self._dir / f"{topic}.md"
        if path.exists():
            path.unlink()
            return True
        return False
