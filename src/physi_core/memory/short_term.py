"""L1 Short-Term Memory — session-based conversation history."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ShortTermMemory:
    """Manages conversation session records in JSONL format.

    - current_session.jsonl: active conversation
    - session_{timestamp}.jsonl: archived sessions
    """

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)
        self._current_path = self._dir / "current_session.jsonl"
        self._messages: list[dict[str, Any]] = []
        self._load_current()

    def _load_current(self) -> None:
        """Load current session from disk."""
        if not self._current_path.exists():
            return
        for line in self._current_path.read_text(encoding="utf-8").strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                self._messages.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Skipping invalid JSON in current session")

    def add_message(
        self,
        role: str,
        content: str | None = None,
        *,
        thinking: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_name: str | None = None,
        tool_result: str | None = None,
        source: str = "cli",
    ) -> None:
        """Append a message to the current session and persist."""
        msg: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "role": role,
        }
        if content is not None:
            msg["content"] = content
        if thinking is not None:
            msg["thinking"] = thinking
        if tool_calls is not None:
            msg["tool_calls"] = tool_calls
        if tool_name is not None:
            msg["name"] = tool_name
        if tool_result is not None:
            msg["result"] = tool_result
        if role == "user":
            msg["source"] = source

        self._messages.append(msg)
        self._persist_current()

    def get_messages(self) -> list[dict[str, Any]]:
        """Return all messages in the current session."""
        return list(self._messages)

    def get_messages_for_llm(self) -> list[dict[str, Any]]:
        """Return messages formatted for LLM API (role + content only)."""
        result: list[dict[str, Any]] = []
        for msg in self._messages:
            entry: dict[str, Any] = {"role": msg["role"]}
            if "content" in msg and msg["content"]:
                entry["content"] = msg["content"]
            elif "result" in msg:
                entry["content"] = msg["result"]
            else:
                entry["content"] = ""
            result.append(entry)
        return result

    def end_session(self) -> None:
        """Archive current session and start fresh."""
        if not self._messages:
            return

        # Archive
        ts = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M")
        archive_path = self._dir / f"session_{ts}.jsonl"
        if self._current_path.exists():
            self._current_path.rename(archive_path)

        # Cleanup old archives (keep most recent by count, let LLM decide importance)
        self._messages = []
        self._persist_current()

    def get_archived_sessions(self) -> list[Path]:
        """List archived session files, newest first."""
        sessions = sorted(self._dir.glob("session_*.jsonl"), reverse=True)
        return sessions

    @property
    def message_count(self) -> int:
        """Number of messages in current session."""
        return len(self._messages)

    def _persist_current(self) -> None:
        """Write current session to disk."""
        lines = [json.dumps(m, ensure_ascii=False) for m in self._messages]
        self._current_path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")
