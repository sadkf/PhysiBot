"""Clipboard monitor — periodic polling with change detection."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


class ClipboardMonitor:
    """Polls the system clipboard for text changes.

    Stores a rolling history of copied text (dedup'd, last N unique entries).
    """

    def __init__(
        self,
        poll_interval: int = 5,
        max_history: int = 20,
    ) -> None:
        self._interval = poll_interval
        self._history: deque[ClipboardEntry] = deque(maxlen=max_history)
        self._last_text: str = ""
        self._running = False

    async def start(self) -> None:
        """Start polling loop."""
        self._running = True
        while self._running:
            try:
                text = await self._read_clipboard()
                if text and text != self._last_text:
                    self._last_text = text
                    self._history.append(ClipboardEntry(
                        text=text,
                        timestamp=datetime.now(UTC).isoformat(),
                    ))
            except Exception:
                logger.debug("Clipboard read failed (expected if no text)")
            await asyncio.sleep(self._interval)

    def stop(self) -> None:
        self._running = False

    async def _read_clipboard(self) -> str:
        """Read current clipboard text, non-blocking."""
        try:
            import pyperclip

            return await asyncio.to_thread(pyperclip.paste)
        except Exception:
            return ""

    def get_recent(self, count: int = 5) -> list[str]:
        """Get the most recent N unique clipboard entries."""
        entries = list(self._history)[-count:]
        return [e.text for e in entries]

    def format_for_llm(self, count: int = 5) -> str:
        """Format recent clipboard history for LLM context."""
        entries = list(self._history)[-count:]
        if not entries:
            return ""
        lines = ["## 最近剪贴板"]
        for e in entries:
            preview = e.text[:100]
            lines.append(f"- [{e.timestamp}] {preview}")
        return "\n".join(lines)

    @property
    def entry_count(self) -> int:
        return len(self._history)


class ClipboardEntry:
    """A single clipboard history entry."""

    def __init__(self, text: str, timestamp: str) -> None:
        self.text = text
        self.timestamp = timestamp
