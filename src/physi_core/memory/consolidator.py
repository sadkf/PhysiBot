"""AutoConsolidate — LLM-driven memory lifecycle management."""

from __future__ import annotations

import logging
from typing import Any

from physi_core.llm.adapter import LLMClient
from physi_core.memory.index import MemoryIndex
from physi_core.memory.long_term import LongTermMemory
from physi_core.memory.mid_term import MidTermMemory

logger = logging.getLogger(__name__)

# ── Prompt Templates ──────────────────────────────

SEGMENT_SUMMARIZE_PROMPT = """\
你是用户的私人助手 PhysiBot。以下是用户过去 30 分钟的电脑活动数据。
请完成两项任务：

## 任务 1: 活动摘要
用 3-5 句话描述用户这 30 分钟在做什么。只保留有意义的信息。
输出格式为 Markdown，包含"主要活动"和"应用使用"两小节。

## 任务 2: 是否需要发消息
根据以下规则判断，在摘要末尾加上一行：
NOTIFY: YES 或 NOTIFY: NO
- 用户连续使用电脑超过 2 小时 → YES + 提醒休息
- 当前时间超过凌晨 1 点且用户仍在活跃 → YES + 提醒睡觉
- 检测到异常行为 → YES + 主动询问
- 其他情况 → NO

[活动数据]
{data}

[当前时间] {current_time}
[用户已连续使用] {continuous_hours} 小时"""

DAILY_MERGE_PROMPT = """\
以下是今天所有的 30 分钟活动片段（共 {count} 个）。请完成：
1. 将它们压缩为一份日级摘要（格式：一句话总结 + 工作/生活/健康三段）
2. 标记哪些片段可以回收（已完全合并进摘要的普通片段）。
   重要事件（如用户生气、重要决定、里程碑）的片段不标记为回收。

输出格式：
先输出日摘要（Markdown），然后空一行，输出：
RECYCLABLE: segment1.md, segment2.md, ...

[今日片段]
{segments}"""

SESSION_EXTRACT_PROMPT = """\
以下是刚才与用户的完整对话。请判断：
1. 对话中有没有值得记住的新信息？（如偏好变化、新项目、情绪状态）
2. 如果有，指出应该写入哪个长期记忆文件，以及具体内容。

当前长期记忆文件列表: {topics}

输出格式（JSON）:
{{"updates": [{{"topic": "portrait", "action": "append", "content": "新发现..."}}]}}
如果没有新信息，输出: {{"updates": []}}

[对话内容]
{conversation}"""

WEEKLY_REVIEW_PROMPT = """\
以下是你对用户的全部长期记忆和本周的日摘要。
请像一个尽职的秘书一样审视这些记忆：

1. 矛盾检测：有没有互相矛盾的记忆？→ 以最新为准
2. 过时清理：有没有已经不再准确的信息？→ 更新或删除
3. 模式发现：本周有没有新的行为模式值得记录？
4. 画像演化：用户的关注点/心情/工作重心有没有变化？

输出需要修改的文件内容（JSON 格式）:
{{"updates": [{{"topic": "routines", "action": "replace", "content": "新内容..."}}]}}
如果不需要修改，输出: {{"updates": []}}

[长期记忆]
{long_term}

[本周日摘要]
{weekly_dailies}"""


class Consolidator:
    """LLM-driven memory consolidation engine."""

    def __init__(
        self,
        llm: LLMClient,
        mid_term: MidTermMemory,
        long_term: LongTermMemory,
        memory_index: MemoryIndex,
    ) -> None:
        self._llm = llm
        self._mid = mid_term
        self._lt = long_term
        self._idx = memory_index

    async def summarize_segment(
        self,
        raw_data: str,
        current_time: str,
        continuous_hours: float,
    ) -> SegmentResult:
        """Generate a 30-min activity summary from raw perception data."""
        prompt = SEGMENT_SUMMARIZE_PROMPT.format(
            data=raw_data,
            current_time=current_time,
            continuous_hours=f"{continuous_hours:.1f}",
        )

        response = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        )

        text = response.text or ""

        # Parse NOTIFY flag
        should_notify = False
        notify_message = ""
        lines = text.strip().split("\n")
        for i, line in enumerate(lines):
            if line.strip().startswith("NOTIFY:"):
                flag = line.strip().split(":", 1)[1].strip()
                should_notify = flag.upper().startswith("YES")
                if should_notify and i > 0:
                    # Use the summary as notification context
                    notify_message = "\n".join(lines[:i]).strip()
                # Remove the NOTIFY line from summary
                text = "\n".join(lines[:i]).strip()
                break

        return SegmentResult(
            summary=text,
            should_notify=should_notify,
            notify_message=notify_message,
            usage=response.usage,
        )

    async def merge_daily(self, date: str) -> DailyMergeResult:
        """Merge all segments of a day into a daily summary."""
        segments = self._mid.get_segments_for_day(date)
        if not segments:
            return DailyMergeResult(summary="", recyclable=[])

        segment_files = [p.name for p in self._mid.list_segments(date)]
        segments_text = "\n\n---\n\n".join(
            f"### {name}\n{content}"
            for name, content in zip(segment_files, segments, strict=False)
        )

        prompt = DAILY_MERGE_PROMPT.format(
            count=len(segments),
            segments=segments_text,
        )

        response = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )

        text = response.text or ""
        recyclable: list[str] = []

        # Parse RECYCLABLE line
        for line in text.split("\n"):
            if line.strip().startswith("RECYCLABLE:"):
                names = line.split(":", 1)[1].strip()
                recyclable = [n.strip() for n in names.split(",") if n.strip()]
                text = text.replace(line, "").strip()
                break

        # Write daily summary
        self._mid.write_daily(text, date)

        return DailyMergeResult(summary=text, recyclable=recyclable)

    async def extract_from_session(
        self, conversation_text: str
    ) -> list[dict[str, str]]:
        """Extract notable info from a conversation for L3 update."""
        topics = self._lt.list_topics()
        prompt = SESSION_EXTRACT_PROMPT.format(
            topics=", ".join(topics) if topics else "portrait, preferences, routines",
            conversation=conversation_text[:3000],  # Limit to ~1000 tokens
        )

        response = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        )

        updates = self._parse_json_updates(response.text or "")

        # Apply updates
        for update in updates:
            topic = update.get("topic", "")
            action = update.get("action", "")
            content = update.get("content", "")
            if not topic or not content:
                continue

            if action == "replace":
                self._lt.write_topic(topic, content)
            else:  # append
                self._lt.append_to_topic(topic, content)

            logger.info("L3 updated: %s (%s)", topic, action)

        return updates

    async def weekly_review(self) -> list[dict[str, str]]:
        """Deep review of L3 memory against this week's data."""
        # Gather L3 content
        all_lt = self._lt.read_all()
        lt_text = "\n\n".join(
            f"### {topic}\n{content}" for topic, content in all_lt.items()
        )

        # Gather this week's dailies
        dailies = self._mid.get_recent_dailies(7)
        dailies_text = "\n\n---\n\n".join(dailies) if dailies else "本周无日摘要"

        prompt = WEEKLY_REVIEW_PROMPT.format(
            long_term=lt_text or "无长期记忆",
            weekly_dailies=dailies_text,
        )

        response = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )

        updates = self._parse_json_updates(response.text or "")

        for update in updates:
            topic = update.get("topic", "")
            content = update.get("content", "")
            if topic and content:
                self._lt.write_topic(topic, content)
                logger.info("Weekly review updated: %s", topic)

        # Update MEMORY.md index
        self._refresh_index()

        return updates

    def _refresh_index(self) -> None:
        """Rebuild MEMORY.md summaries from current L3 state."""
        for topic in self._lt.list_topics():
            content = self._lt.read_topic(topic)
            if content:
                # Take first 2 lines as summary
                lines = content.strip().split("\n")
                summary = " ".join(lines[:2])[:100]
                self._idx.update_section(
                    topic, f"→ memory/{topic}.md\n{summary}"
                )

    @staticmethod
    def _parse_json_updates(text: str) -> list[dict[str, str]]:
        """Extract JSON updates array from LLM response text."""
        import json

        # Try to find JSON in the response
        try:
            # Direct parse
            data = json.loads(text)
            return data.get("updates", [])
        except json.JSONDecodeError:
            pass

        # Try to find JSON block in markdown
        for marker in ("```json", "```"):
            if marker in text:
                start = text.index(marker) + len(marker)
                end = text.index("```", start)
                try:
                    data = json.loads(text[start:end].strip())
                    return data.get("updates", [])
                except (json.JSONDecodeError, ValueError):
                    pass

        # Try to find { ... } pattern
        brace_start = text.find("{")
        brace_end = text.rfind("}") + 1
        if brace_start >= 0 and brace_end > brace_start:
            try:
                data = json.loads(text[brace_start:brace_end])
                return data.get("updates", [])
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse JSON updates from LLM response")
        return []


class SegmentResult:
    """Result of a 30-min segment summarization."""

    def __init__(
        self,
        summary: str,
        should_notify: bool,
        notify_message: str,
        usage: Any = None,
    ) -> None:
        self.summary = summary
        self.should_notify = should_notify
        self.notify_message = notify_message
        self.usage = usage


class DailyMergeResult:
    """Result of daily merge operation."""

    def __init__(self, summary: str, recyclable: list[str]) -> None:
        self.summary = summary
        self.recyclable = recyclable
