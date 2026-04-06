"""Prompt builder — assembles the system prompt from all memory layers."""

from __future__ import annotations

import logging
from typing import Any

from physi_core.memory.identity import IdentityMemory
from physi_core.memory.index import MemoryIndex
from physi_core.memory.long_term import LongTermMemory

from physi_core import prompts

logger = logging.getLogger(__name__)


def build_system_prompt(
    physi_md_content: str,
    identity: IdentityMemory,
    memory_index: MemoryIndex,
    long_term: LongTermMemory,
    tools: list[dict[str, Any]] | None = None,
    today_summary: str = "",
    recent_segments: str = "",
    system_events: str = "",
    current_datetime: str = "",
    project_path: str = "",
) -> str:
    """Build the complete system prompt by assembling all memory layers.

    Args:
        tools: List of {"name": ..., "description": ...} dicts derived from
               ToolController so the template always matches reality.
    """
    # L0 和 L3 分开注入，不合并 — 结构化事实 vs 推断性画像职责不同
    identity_text = identity.to_prompt_text()
    portrait_text = long_term.to_prompt_text("portrait")

    tool_list = tools or []

    rendered = prompts.render(
        "system_prompt.j2",
        physi_md=physi_md_content.strip(),
        identity_prompt=identity_text.strip(),
        portrait_prompt=portrait_text.strip(),
        memory_index=memory_index.to_prompt_text().strip(),
        tools=tool_list,
        today_summary=today_summary.strip() or "无",
        recent_segments=recent_segments.strip(),
        system_events=system_events.strip(),
        current_datetime=current_datetime,
        project_path=project_path,
    )
    logger.debug("System prompt rendered: %d chars, %d tools", len(rendered), len(tool_list))
    return rendered


def load_physi_md(physi_md_path: str | None = None) -> str:
    """Load PHYSI.md content from disk. Returns empty string if not found."""
    if physi_md_path is None:
        return ""
    from pathlib import Path

    path = Path(physi_md_path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")
