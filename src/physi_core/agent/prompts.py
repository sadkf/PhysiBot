"""Prompt builder — assembles the system prompt from all memory layers."""

from __future__ import annotations

from physi_core.memory.identity import IdentityMemory
from physi_core.memory.index import MemoryIndex
from physi_core.memory.long_term import LongTermMemory


def build_system_prompt(
    physi_md_content: str,
    identity: IdentityMemory,
    memory_index: MemoryIndex,
    long_term: LongTermMemory,
    today_summary: str = "",
    recent_segments: str = "",
) -> str:
    """Build the complete system prompt by assembling all memory layers.

    Injection order:
    1. PHYSI.md (L4 instructions)  ~400 tokens
    2. Identity (L0 profile)        ~200 tokens
    3. MEMORY.md (index)            ~500 tokens
    4. Portrait (L3)                ~500 tokens
    5. Today summary (L2)           ~300 tokens
    6. Recent segments (L2)         ~200 tokens
    Total: ~2100 tokens (well under model limits)
    """
    parts: list[str] = []

    # L4: Core instructions
    if physi_md_content:
        parts.append(physi_md_content.strip())

    # L0: Identity facts
    identity_text = identity.to_prompt_text()
    if identity_text:
        parts.append(identity_text)

    # MEMORY.md: Index
    index_text = memory_index.to_prompt_text()
    if index_text:
        parts.append(index_text)

    # L3: User portrait
    portrait_text = long_term.to_prompt_text("portrait")
    if portrait_text:
        parts.append(portrait_text)

    # L2: Today's daily summary
    if today_summary:
        parts.append(f"## 今日活动\n{today_summary.strip()}")

    # L2: Recent 30-min segments
    if recent_segments:
        parts.append(f"## 最近活动\n{recent_segments.strip()}")

    return "\n\n---\n\n".join(parts)


def load_physi_md(physi_md_path: str | None = None) -> str:
    """Load PHYSI.md content from disk. Returns empty string if not found."""
    if physi_md_path is None:
        return ""
    from pathlib import Path

    path = Path(physi_md_path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
