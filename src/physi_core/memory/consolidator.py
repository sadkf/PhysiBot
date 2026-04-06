"""AutoConsolidate — LLM 驱动的记忆生命周期管理。

所有 LLM 交互通过工具调用完成，不做字符串解析。
Prompt 统一存放在 physi_core/prompts/*.j2 模板文件中。
Tool schema 统一存放在 physi_core/prompts/tool_schemas.py 中。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from physi_core import prompts as prompt_store
from physi_core.llm.adapter import LLMClient
from physi_core.memory.identity import IdentityMemory
from physi_core.memory.index import MemoryIndex
from physi_core.memory.long_term import (
    LLM_BLOCKED_TOPICS,
    LongTermMemory,
    llm_blocked_topic_reply,
)
from physi_core.memory.mid_term import MidTermMemory
from physi_core.observability import emit_event
from physi_core.memory.work_projects_patch import apply_work_project_patch
from physi_core.prompts.tool_schemas import (
    identity_set_schema,
    memory_write_schema,
    work_project_patch_schema,
    write_daily_schema,
    write_segment_schema,
    write_weekly_schema,
)

logger = logging.getLogger(__name__)

AsyncToolFn = Callable[..., Coroutine[Any, Any, str]]


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class SegmentResult:
    summary: str
    should_notify: bool
    notify_message: str
    active_projects: list[str] | None = None
    learning_topics: list[str] | None = None
    metadata_updates: list[dict[str, str]] | None = None


@dataclass
class DailyMergeResult:
    summary: str
    recyclable: list[str]


# ── Consolidator ──────────────────────────────────────────────────────────────
# Tool schemas are imported from physi_core.prompts.tool_schemas (single source of truth).

class Consolidator:
    """LLM 驱动的记忆整合引擎。

    各阶段职责：
    - summarize_segment : 感知数据 → 30 分钟片段 + 通知决策
    - merge_daily       : 当日片段 → 日摘要 + 可回收列表
    - extract_from_session : 对话 → L3 长期记忆 + L0 元信息
    - weekly_review     : L3 全量 + 近 7 天日摘要 → 深度整理 + 周摘要
    """

    def __init__(
        self,
        llm: LLMClient,
        mid_term: MidTermMemory,
        long_term: LongTermMemory,
        memory_index: MemoryIndex,
        identity: IdentityMemory | None = None,
    ) -> None:
        self._llm = llm
        self._mid = mid_term
        self._lt = long_term
        self._idx = memory_index
        self._identity = identity

    # ── Public API ────────────────────────────────────────────────────────────

    async def summarize_segment(
        self,
        raw_data: str,
        current_time: str,
        continuous_hours: float,
    ) -> SegmentResult:
        """生成 30 分钟活动摘要并决定是否通知用户。"""
        emit_event(
            "consolidator.segment.start",
            data_len=len(raw_data),
            data_preview=raw_data[:500],
            current_time=current_time,
            continuous_hours=continuous_hours,
        )

        result: dict[str, Any] = {
            "summary": "",
            "should_notify": False,
            "notify_message": "",
            "active_projects": [],
            "learning_topics": [],
            "metadata_updates": [],
        }

        async def write_segment(
            summary: str,
            should_notify: bool,
            notify_message: str = "",
            active_projects: list[str] | None = None,
            learning_topics: list[str] | None = None,
            metadata_updates: list[dict[str, str]] | None = None,
        ) -> str:
            result["summary"] = summary
            result["should_notify"] = should_notify
            result["notify_message"] = notify_message
            result["active_projects"] = active_projects or []
            result["learning_topics"] = learning_topics or []
            result["metadata_updates"] = metadata_updates or []
            emit_event(
                "consolidator.segment.written",
                summary_preview=summary[:300],
                should_notify=should_notify,
                notify_message=notify_message,
                active_projects=active_projects or [],
                learning_topics=learning_topics or [],
                metadata_updates_count=len(metadata_updates or []),
            )
            return "ok"

        prompt = prompt_store.render(
            "segment_summarize.j2",
            data=raw_data,
            current_time=current_time,
            continuous_hours=continuous_hours,
        )
        logger.debug("summarize_segment: prompt %d chars", len(prompt))
        await self._forced_tool_call(
            prompt=prompt,
            tool_schema=write_segment_schema(),
            tool_fn=write_segment,
            system=(
                "你是活动摘要助手。根据提供的屏幕 OCR 文本和活动数据，"
                "调用 write_segment 工具写入结构化的 30 分钟活动摘要。"
                "summary 用 Markdown 格式，简洁描述用户在这段时间做了什么。"
                "metadata_updates 只写真正稳定的身份/偏好事实，不写临时状态。"
            ),
        )
        return SegmentResult(**result)

    async def merge_daily(self, date: str) -> DailyMergeResult:
        """将当天所有片段合并为日摘要。"""
        segments = self._mid.get_segments_for_day(date)
        if not segments:
            emit_event("consolidator.daily.skip", date=date, reason="no_segments")
            return DailyMergeResult(summary="", recyclable=[])

        segment_files = [p.name for p in self._mid.list_segments(date)]
        segments_text = "\n\n---\n\n".join(
            f"### {name}\n{content}"
            for name, content in zip(segment_files, segments, strict=False)
        )

        emit_event(
            "consolidator.daily.start",
            date=date,
            segment_count=len(segments),
            segments_preview=segments_text[:500],
        )

        result: dict[str, Any] = {"summary": "", "recyclable": []}

        async def write_daily_summary(
            summary: str,
            recyclable_files: list[str] | None = None,
        ) -> str:
            result["summary"] = summary
            result["recyclable"] = recyclable_files or []
            self._mid.write_daily(summary, date)
            emit_event(
                "consolidator.daily.written",
                date=date,
                summary_preview=summary[:300],
                recyclable_count=len(recyclable_files or []),
            )
            return "ok"

        prompt = prompt_store.render(
            "daily_merge.j2",
            count=len(segments),
            segments=segments_text,
        )
        logger.debug("merge_daily %s: prompt %d chars, %d segments", date, len(prompt), len(segments))
        await self._forced_tool_call(
            prompt=prompt,
            tool_schema=write_daily_schema(),
            tool_fn=write_daily_summary,
            max_tokens=2048,
            system=(
                "你是日摘要助手。将今天所有 30 分钟片段合并为一份精炼的日摘要，"
                "调用 write_daily_summary 工具写入结果。"
                "summary 用 Markdown 格式，聚焦核心工作和学习内容，去除重复。"
                "recyclable_files 列出可以归档删除的冗余片段文件名。"
            ),
        )
        return DailyMergeResult(**result)

    async def extract_from_session(self, conversation_text: str) -> int:
        """从对话中提取有价值信息，写入 L3 长期记忆和 L0 元信息。"""
        topics = self._lt.list_topics()
        safe_topics = [t for t in topics if t.lower() not in LLM_BLOCKED_TOPICS]
        topic_hint = (
            ", ".join(safe_topics)
            if safe_topics
            else "portrait, preferences, routines, skills_interests, social"
        )

        emit_event(
            "consolidator.session_extract.start",
            conv_len=len(conversation_text),
            conv_preview=conversation_text[:400],
            existing_topics=topics,
        )

        write_count = 0
        writes: list[dict[str, str]] = []

        async def memory_write(topic: str, content: str, action: str = "append") -> str:
            nonlocal write_count
            blocked = llm_blocked_topic_reply(topic)
            if blocked:
                logger.warning("Session extract rejected L3 write: %s", topic)
                emit_event("consolidator.memory_write.rejected", topic=topic, reason="blocked_topic")
                return blocked
            if action == "replace":
                self._lt.write_topic(topic, content)
            else:
                self._lt.append_to_topic(topic, content)
            write_count += 1
            writes.append({"layer": "L3", "topic": topic, "action": action, "preview": content[:150]})
            logger.info("L3 updated via session extract: %s (%s)", topic, action)
            emit_event(
                "consolidator.memory_write",
                layer="L3",
                topic=topic,
                action=action,
                content_preview=content[:150],
            )
            return f"已写入: {topic}"

        async def identity_set(key: str, value: str) -> str:
            nonlocal write_count
            if self._identity is None:
                return "identity disabled"
            self._identity.set(key, value)
            write_count += 1
            writes.append({"layer": "L0", "key": key, "value": value})
            logger.info("L0 updated via session extract: %s", key)
            emit_event("consolidator.identity_set", key=key, value=value)
            return f"已记录: {key}"

        async def work_project_patch(
            project_heading: str, action: str, body: str = ""
        ) -> str:
            nonlocal write_count
            raw = self._lt.read_topic("work_projects") or ""
            try:
                new_text = apply_work_project_patch(raw, project_heading, action, body)
            except ValueError as e:
                return str(e)
            self._lt.write_topic("work_projects", new_text)
            self._idx.update_section(
                "work_projects",
                "-> memory/work_projects.md\n长期项目（定点维护）",
            )
            write_count += 1
            writes.append(
                {
                    "layer": "L3",
                    "topic": "work_projects",
                    "action": f"patch:{action}",
                    "preview": f"{project_heading}…",
                }
            )
            emit_event(
                "consolidator.work_project_patch",
                heading=project_heading,
                action=action,
            )
            return f"已更新项目块: {project_heading}"

        system = prompt_store.render("session_extract.j2")
        tool_schemas = [
            memory_write_schema(),
            identity_set_schema(),
            work_project_patch_schema(),
        ]
        tool_fns: dict[str, AsyncToolFn] = {
            "memory_write": memory_write,
            "identity_set": identity_set,
            "work_project_patch": work_project_patch,
        }

        prompt = (
            f"当前已有的记忆主题：{topic_hint}\n\n"
            f"[对话内容]\n{conversation_text[:4000]}"
        )
        await self._tool_loop(
            system=system,
            prompt=prompt,
            tool_schemas=tool_schemas,
            tool_fns=tool_fns,
        )
        if write_count > 0:
            self._refresh_index()

        emit_event(
            "consolidator.session_extract.done",
            write_count=write_count,
            writes=writes,
        )
        return write_count

    async def weekly_review(self) -> None:
        """深度整理 L3 记忆，写入周摘要。"""
        all_lt = self._lt.read_all()
        lt_text = "\n\n".join(
            f"### {topic}\n{content}" for topic, content in all_lt.items()
        ) or "暂无长期记忆"

        dailies = self._mid.get_recent_dailies(7)
        dailies_text = "\n\n---\n\n".join(dailies) if dailies else "本周无日摘要"

        emit_event(
            "consolidator.weekly.start",
            lt_topics=list(all_lt.keys()),
            dailies_count=len(dailies),
            lt_preview=lt_text[:400],
        )

        updated_topics: list[str] = []

        async def memory_write(topic: str, content: str, action: str = "replace") -> str:
            blocked = llm_blocked_topic_reply(topic)
            if blocked:
                logger.warning("Weekly review rejected L3 write: %s", topic)
                emit_event("consolidator.memory_write.rejected", topic=topic, reason="blocked_topic")
                return blocked
            if action == "replace":
                self._lt.write_topic(topic, content)
            else:
                self._lt.append_to_topic(topic, content)
            updated_topics.append(topic)
            logger.info("Weekly review updated L3: %s", topic)
            emit_event(
                "consolidator.memory_write",
                layer="L3",
                topic=topic,
                action=action,
                content_preview=content[:150],
            )
            return f"已更新: {topic}"

        async def write_weekly_summary(summary: str) -> str:
            self._mid.write_weekly(summary)
            logger.info("Weekly summary written")
            emit_event("consolidator.weekly.summary_written", summary_preview=summary[:300])
            return "ok"

        async def work_project_patch(
            project_heading: str, action: str, body: str = ""
        ) -> str:
            raw = self._lt.read_topic("work_projects") or ""
            try:
                new_text = apply_work_project_patch(raw, project_heading, action, body)
            except ValueError as e:
                return str(e)
            self._lt.write_topic("work_projects", new_text)
            self._idx.update_section(
                "work_projects",
                "-> memory/work_projects.md\n长期项目（定点维护）",
            )
            updated_topics.append("work_projects")
            emit_event(
                "consolidator.work_project_patch",
                heading=project_heading,
                action=action,
            )
            return f"已更新项目块: {project_heading}"

        system = prompt_store.render("weekly_review.j2")
        await self._tool_loop(
            system=system,
            prompt=f"[长期记忆]\n{lt_text}\n\n[近7天日摘要]\n{dailies_text}",
            tool_schemas=[
                memory_write_schema(),
                write_weekly_schema(),
                work_project_patch_schema(),
            ],
            tool_fns={
                "memory_write": memory_write,
                "write_weekly_summary": write_weekly_summary,
                "work_project_patch": work_project_patch,
            },
            max_tokens=2048,
        )
        self._refresh_index()
        emit_event("consolidator.weekly.done", updated_topics=updated_topics)

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _forced_tool_call(
        self,
        prompt: str,
        tool_schema: dict[str, Any],
        tool_fn: AsyncToolFn,
        max_tokens: int = 1024,
        system: str = "",
    ) -> None:
        """强制 LLM 调用指定工具一次，然后执行它。"""
        tool_name = tool_schema["function"]["name"]
        emit_event(
            "consolidator.llm_call",
            mode="forced",
            tool=tool_name,
            prompt_preview=prompt[:400],
        )
        response = await self._llm.chat(
            messages=[{"role": "user", "content": prompt}],
            system=system,
            tools=[tool_schema],
            tool_choice=tool_name,
            max_tokens=max_tokens,
        )
        for tc in response.tool_calls:
            if tc.name == tool_name:
                emit_event(
                    "consolidator.tool_exec",
                    tool=tool_name,
                    args_preview=str(tc.arguments)[:300],
                )
                await tool_fn(**tc.arguments)
                return
        logger.error("Forced tool call '%s' was not invoked by LLM", tool_name)
        emit_event("consolidator.llm_call.failed", tool=tool_name)

    async def _tool_loop(
        self,
        system: str,
        prompt: str,
        tool_schemas: list[dict[str, Any]],
        tool_fns: dict[str, AsyncToolFn],
        max_rounds: int = 6,
        max_tokens: int = 1024,
    ) -> None:
        """运行迷你 agent 循环，直到 LLM 停止调用工具。"""
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        available_tools = [s["function"]["name"] for s in tool_schemas]

        emit_event(
            "consolidator.llm_call",
            mode="loop",
            tools=available_tools,
            prompt_preview=prompt[:400],
        )

        for round_idx in range(max_rounds):
            response = await self._llm.chat(
                messages=messages,
                system=system,
                tools=tool_schemas,
                max_tokens=max_tokens,
            )
            if not response.has_tool_calls():
                logger.debug("consolidator _tool_loop: no more tool calls after round %d", round_idx + 1)
                break

            tool_use_blocks = [
                {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
                for tc in response.tool_calls
            ]
            messages.append({"role": "assistant", "content": tool_use_blocks})

            tool_results = []
            for tc in response.tool_calls:
                fn = tool_fns.get(tc.name)
                if fn is None:
                    logger.warning("Unknown tool in consolidator loop: %s", tc.name)
                    output = f"未知工具: {tc.name}"
                else:
                    emit_event(
                        "consolidator.tool_exec",
                        tool=tc.name,
                        args_preview=str(tc.arguments)[:300],
                    )
                    output = await fn(**tc.arguments)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": output,
                })
            messages.append({"role": "user", "content": tool_results})

    def _refresh_index(self) -> None:
        """根据 L3 当前内容重建 MEMORY.md 索引摘要。"""
        for topic in self._lt.list_topics():
            content = self._lt.read_topic(topic)
            if content:
                lines = content.strip().split("\n")
                summary = " ".join(lines[:2])[:100]
                self._idx.update_section(topic, f"-> memory/{topic}.md\n{summary}")
                logger.debug("Index refreshed: %s", topic)
