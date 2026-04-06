"""Privacy filter — sensitive data detection and removal before LLM injection."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Built-in patterns that should NEVER be sent to LLM
BUILTIN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b\d{13,19}\b"),  # Bank card numbers (13-19 digits)
    re.compile(r"\b\d{3}[-.\s]?\d{4}[-.\s]?\d{4}\b"),  # Phone-like
    re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    ),  # Email
    re.compile(r"-----BEGIN.*KEY-----"),  # PEM keys
]


class PrivacyFilter:
    """Filters sensitive content before sending to LLM."""

    def __init__(
        self,
        enabled: bool = True,
        keywords: list[str] | None = None,
        ignore_apps: list[str] | None = None,
    ) -> None:
        self._enabled = enabled
        self._keywords = [k.lower() for k in (keywords or [])]
        self._ignore_apps = [a.lower() for a in (ignore_apps or [])]

    def should_skip_app(self, app_name: str) -> bool:
        """Check if an app should be excluded from monitoring."""
        return app_name.lower() in self._ignore_apps

    def contains_sensitive(self, text: str) -> bool:
        """Check if text contains sensitive keywords or patterns."""
        if not self._enabled:
            return False
        lower = text.lower()

        # Keyword check
        for kw in self._keywords:
            if kw in lower:
                return True

        # Pattern check
        for pattern in BUILTIN_PATTERNS:
            if pattern.search(text):
                return True

        return False

    def redact(self, text: str) -> str:
        """Remove sensitive content from text, replacing with [REDACTED]."""
        if not self._enabled:
            return text
        result = text

        # Redact builtin patterns
        for pattern in BUILTIN_PATTERNS:
            result = pattern.sub("[REDACTED]", result)

        # Redact lines containing sensitive keywords
        lines = result.split("\n")
        cleaned: list[str] = []
        for line in lines:
            lower = line.lower()
            if any(kw in lower for kw in self._keywords):
                cleaned.append("[REDACTED - 含敏感词]")
            else:
                cleaned.append(line)

        return "\n".join(cleaned)

    def filter_frames(
        self, frames: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        """Filter a list of OCR frames, removing sensitive ones."""
        result = []
        for frame in frames:
            app = frame.get("app_name", "")
            if self.should_skip_app(app):
                continue
            text = frame.get("text", "")
            if self.contains_sensitive(text):
                continue
            result.append(frame)
        return result
