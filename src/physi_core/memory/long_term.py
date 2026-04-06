"""L3 Long-Term Memory — persistent user portrait in Markdown topic files."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 仅机器定时追加；LLM 不得写入（避免与感知合并逻辑冲突）
LLM_BLOCKED_TOPICS = frozenset({"segment_activity"})


def llm_blocked_topic_reply(topic: str) -> str | None:
    """若该主题禁止 LLM 写入，返回给模型的错误文案；否则 None。"""
    key = topic.strip().lower()
    if key == "segment_activity":
        return (
            "拒绝写入 topic=segment_activity：该文件仅由定时感知任务机器追加。"
        )
    if key == "work_projects":
        return (
            "work_projects 请用 work_project_patch 按「## 项目名」区块定点增删改，"
            "勿用 memory_write 整文件覆盖。"
        )
    return None


class LongTermMemory:
    """Manages L3 long-term user portrait stored as multiple .md topic files."""

    # L3 主题文件 — 仅存「推断性」用户画像，结构化事实（账号/服务器等）存 L0
    # portrait         : 性格标签、交流风格、总体印象
    # preferences      : 口味、审美、讨厌什么
    # routines         : 作息规律、日常习惯
    # skills_interests : 技术栈、爱好、学习方向
    # social           : 重要人际关系
    # health           : 健康习惯、久坐/睡眠模式
    # emotional_patterns: 情绪触发点、压力表现
    # iot_preferences  : 智能家居使用偏好
    DEFAULT_TOPICS = [
        "portrait",
        "preferences",
        "routines",
        "skills_interests",
        "social",
        "health",
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
