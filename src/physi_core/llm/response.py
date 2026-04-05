"""Standardized LLM response types."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TokenUsage:
    """Token usage statistics."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ToolCall:
    """A single tool call from the LLM."""

    id: str
    name: str
    arguments: dict  # type: ignore[type-arg]

    def __str__(self) -> str:
        return f"ToolCall({self.name}, {self.arguments})"


@dataclass(frozen=True)
class LLMResponse:
    """Standardized response from any LLM provider."""

    text: str | None = None
    thinking: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    raw: dict | None = None  # type: ignore[type-arg]

    def has_tool_calls(self) -> bool:
        """Whether the response contains tool call requests."""
        return len(self.tool_calls) > 0

    @property
    def is_text_only(self) -> bool:
        """Whether this is a pure text response (no tools)."""
        return not self.has_tool_calls() and self.text is not None
