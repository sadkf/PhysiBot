"""PhysiBot main entry point — orchestrates all subsystems."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from physi_core.config.settings import Settings, load_settings
from physi_core.observability import emit_event, initialize_observability, start_trace, end_trace

logger = logging.getLogger("physi_core")


def _extract_segment_totals(segments: list[str]) -> str:
    """从每个片段中只提取 【Total】 摘要行，大幅压缩注入上下文的大小。

    若某片段没有 【Total】 行，则取前 150 字符作为备选。
    """
    summaries: list[str] = []
    for seg in segments:
        for line in seg.splitlines():
            if "【Total】" in line or "**【Total" in line:
                summaries.append(line.strip().lstrip("*").lstrip("#").strip())
                break
        else:
            # 没有 Total 行，取纯文本前 150 字符
            plain = seg.strip()[:150]
            if plain:
                summaries.append(plain)
    return "\n".join(summaries)


class PhysiBot:
    """Top-level orchestrator: wires memory, LLM, perception, QQ, and timers."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._data_dir = settings.data_dir

        # Lazy-initialized components
        self._identity: Any = None
        self._short_term: Any = None
        self._mid_term: Any = None
        self._long_term: Any = None
        self._memory_index: Any = None
        self._llm: Any = None
        self._tools: Any = None
        self._agent: Any = None
        self._consolidator: Any = None
        self._scheduler: Any = None
        self._throttle: Any = None
        self._perception_throttle: Any = None
        self._screenpipe: Any = None
        self._aw: Any = None
        self._clipboard: Any = None
        self._privacy: Any = None
        self._qq: Any = None
        self._ha: Any = None
        self._napcat_manager: Any = None
        self._obs: Any = None

    def _init_components(self) -> None:
        """Initialize all components."""
        from physi_core.agent.loop import AgentLoop
        from physi_core.agent.tools import ToolController
        from physi_core.events.scheduler import Scheduler, Throttle
        from physi_core.integrations.activitywatch import ActivityWatchClient
        from physi_core.integrations.screenpipe import ScreenpipeClient
        from physi_core.llm.adapter import LLMClient
        from physi_core.memory.consolidator import Consolidator
        from physi_core.memory.identity import IdentityMemory
        from physi_core.memory.index import MemoryIndex
        from physi_core.memory.long_term import LongTermMemory
        from physi_core.memory.mid_term import MidTermMemory
        from physi_core.memory.short_term import ShortTermMemory

        d = self._data_dir
        self._obs = initialize_observability(d)

        # Memory layers
        self._identity = IdentityMemory(d / "identity" / "profile.jsonl")
        self._short_term = ShortTermMemory(d / "short_term")
        self._mid_term = MidTermMemory(d / "mid_term")
        self._long_term = LongTermMemory(d / "memory")
        self._memory_index = MemoryIndex(d / "MEMORY.md")

        # LLM (set_data_dir enables full I/O logging to llm_calls.jsonl)
        self._llm = LLMClient(self._settings.llm)
        self._llm.set_data_dir(d)

        # Consolidator
        self._consolidator = Consolidator(
            self._llm, self._mid_term, self._long_term, self._memory_index, self._identity,
        )

        # Privacy filter
        from physi_core.integrations.privacy import PrivacyFilter
        self._privacy = PrivacyFilter(
            enabled=self._settings.privacy.redact_sensitive,
            keywords=self._settings.privacy.sensitive_keywords,
            ignore_apps=self._settings.privacy.ignore_apps,
        )

        # Perception
        sp = self._settings.perception.screenpipe
        self._screenpipe = ScreenpipeClient(sp.api_url) if sp.enabled else None
        aw = self._settings.perception.activitywatch
        self._aw = ActivityWatchClient(aw.api_url) if aw.enabled else None

        # Clipboard
        from physi_core.integrations.clipboard import ClipboardMonitor
        cb = self._settings.perception.clipboard
        self._clipboard = ClipboardMonitor(poll_interval=cb.poll_interval) if cb.enabled else None

        # Home Assistant
        if self._settings.iot.enabled and self._settings.iot.token:
            from physi_core.integrations.homeassistant import HomeAssistantClient
            self._ha = HomeAssistantClient(
                self._settings.iot.url, self._settings.iot.token
            )

        # Tools
        self._tools = ToolController()
        self._register_tools(self._tools)
        if self._obs is not None:
            self._obs.set_tools(self._tools.list_tools(), self._tools.list_exposed_tools())

        # Agent Loop (no static system prompt — built fresh each turn)
        self._agent = AgentLoop(
            llm_client=self._llm,
            tool_controller=self._tools,
        )

        # Scheduler + Throttle
        self._scheduler = Scheduler()
        # Throttle for session extraction (per-message, 10 min cooldown)
        self._throttle = Throttle(
            cooldown_seconds=self._settings.agent.user_trigger_cooldown
        )
        # Separate throttle for background perception triggered by user messages
        self._perception_throttle = Throttle(
            cooldown_seconds=self._settings.agent.user_trigger_cooldown
        )

    def _current_datetime_str(self) -> str:
        """Return formatted local datetime string for prompt injection."""
        now_local = datetime.now().astimezone()
        weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][now_local.weekday()]
        return now_local.strftime(f"%Y-%m-%d %H:%M ({weekday_cn})")

    def _is_sleep_time(self) -> bool:
        """Return True if current local time is within the user's configured sleep window."""
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        sleep_str = self._identity.get("sleep_time")
        wake_str = self._identity.get("wakeup_time") or self._identity.get("wake_time")
        if not sleep_str or not wake_str:
            return False
        try:
            tz = ZoneInfo(self._identity.get("timezone") or "Asia/Shanghai")
            now = datetime.now(tz)
            sh, sm = map(int, str(sleep_str).split(":"))
            wh, wm = map(int, str(wake_str).split(":"))
            cur = now.hour * 60 + now.minute
            slp = sh * 60 + sm
            wke = wh * 60 + wm
            # Sleep window spans midnight (e.g. sleep 02:00, wake 10:00)
            if slp > wke:
                return cur >= slp or cur < wke
            return slp <= cur < wke
        except Exception:
            return False

    def _build_system_prompt(self, system_events: str = "") -> str:
        """Build a fresh system prompt with current memory layers and local time."""
        from physi_core.agent.prompts import build_system_prompt, load_physi_md
        # Derive tool list from ToolController so the prompt always matches reality
        tool_list = [
            {"name": t["function"]["name"], "description": t["function"].get("description", "")}
            for t in (self._tools.get_all_schemas() if self._tools else [])
        ]
        return build_system_prompt(
            physi_md_content=load_physi_md(str(self._data_dir / "PHYSI.md")),
            identity=self._identity,
            memory_index=self._memory_index,
            long_term=self._long_term,
            tools=tool_list,
            today_summary=self._mid_term.get_today_summary(),
            recent_segments=_extract_segment_totals(self._mid_term.get_recent_segments(3)),
            system_events=system_events,
            current_datetime=self._current_datetime_str(),
            project_path=str(Path.cwd()),
        )

    def _register_tools(self, tc: Any) -> None:
        """Register all available tools."""
        from physi_core.agent.tools import PermissionLevel
        from physi_core.memory.long_term import llm_blocked_topic_reply
        from physi_core.memory.work_projects_patch import apply_work_project_patch
        from pathlib import Path

        data_root = self._data_dir.resolve()

        async def lsfile(path: str = ".") -> str:
            """List files/directories under physi-data."""
            target = (data_root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
            if data_root not in target.parents and target != data_root:
                return f"拒绝访问: {target} (仅允许 physi-data 目录)"
            if not target.exists():
                return f"路径不存在: {target}"
            if target.is_file():
                return str(target)
            entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            if not entries:
                return f"{target} (空目录)"
            lines = [f"{target}"]
            for item in entries[:200]:
                prefix = "[DIR]" if item.is_dir() else "[FILE]"
                lines.append(f"{prefix} {item.name}")
            if len(entries) > 200:
                lines.append(f"... 还有 {len(entries) - 200} 项")
            return "\n".join(lines)

        async def readfile(path: str, max_lines: int = 200) -> str:
            """Read a text file under physi-data."""
            target = (data_root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
            if data_root not in target.parents and target != data_root:
                return f"拒绝访问: {target} (仅允许 physi-data 目录)"
            if not target.exists() or not target.is_file():
                return f"文件不存在: {target}"
            try:
                content = target.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return f"文件不是 UTF-8 文本: {target}"
            lines = content.splitlines()
            clipped = lines[:max(1, min(max_lines, 1000))]
            if len(lines) > len(clipped):
                clipped.append(f"... (已截断，剩余 {len(lines) - len(clipped)} 行)")
            return "\n".join(clipped) if clipped else "(空文件)"

        async def bash(command: str, timeout_sec: int = 20) -> str:
            """Execute shell command for on-demand diagnostics."""
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(data_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=max(1, min(timeout_sec, 120)))
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return "命令超时，已终止"
            text = (out or b"").decode("utf-8", errors="replace").strip()
            if not text:
                text = "(无输出)"
            if len(text) > 4000:
                text = text[:4000] + "\n... (输出已截断)"
            return f"[exit={proc.returncode}]\n{text}"

        tc.register(
            "lsfile",
            "列出目录内容（默认 physi-data 根目录）",
            {"type": "object", "properties": {"path": {"type": "string", "default": "."}}},
            lsfile,
        )
        tc.register(
            "readfile",
            "读取文本文件内容（physi-data 内）",
            {"type": "object", "properties": {
                "path": {"type": "string"},
                "max_lines": {"type": "integer", "default": 200},
            }, "required": ["path"]},
            readfile,
        )
        tc.register(
            "bash",
            "执行 shell 命令（工作目录为 physi-data）",
            {"type": "object", "properties": {
                "command": {"type": "string"},
                "timeout_sec": {"type": "integer", "default": 20},
            }, "required": ["command"]},
            bash,
        )

        # ── Identity tools (L0) ──────────────────────

        async def identity_get(key: str) -> str:
            val = self._identity.get(key)
            if val is None:
                return f"未找到元信息: {key}"
            return f"{key}: {val}"

        async def identity_set(key: str, value: str) -> str:
            self._identity.set(key, value)
            return f"已记录: {key} = {value}"

        async def identity_list() -> str:
            keys = self._identity.all_keys()
            if not keys:
                return "元信息为空，还不了解用户"
            lines = ["当前已知元信息:"]
            for k in keys:
                lines.append(f"  {k}: {self._identity.get(k)}")
            return "\n".join(lines)

        async def identity_delete(key: str) -> str:
            if self._identity.delete(key):
                return f"已删除: {key}"
            return f"未找到: {key}"

        tc.register(
            "identity_get", "查询用户某项元信息（账号/服务器/基本信息等结构化事实）",
            {"type": "object", "properties": {
                "key": {"type": "string", "description": "键名，如: qq_number, ssh_host, name, bilibili"},
            }, "required": ["key"]},
            identity_get,
        )
        tc.register(
            "identity_set",
            "记录结构化事实到 L0 元信息。适合：账号(qq_number/bilibili/github)、"
            "服务器(ssh_host/server_location)、基本信息(name/age/timezone)、"
            "作息(sleep_time/wakeup_time)。键名用英文 snake_case。"
            "性格/偏好/习惯规律请用 memory_write 写 L3。",
            {"type": "object", "properties": {
                "key": {"type": "string", "description": "英文 snake_case 键名"},
                "value": {"type": "string", "description": "事实内容"},
            }, "required": ["key", "value"]},
            identity_set,
        )
        tc.register(
            "identity_list", "列出所有已知的用户元信息（结构化事实）",
            {"type": "object", "properties": {}},
            identity_list,
        )
        tc.register(
            "identity_delete", "删除某项元信息",
            {"type": "object", "properties": {
                "key": {"type": "string"},
            }, "required": ["key"]},
            identity_delete, PermissionLevel.CONFIRM,
        )

        # ── Memory tools (L3) ────────────────────────

        async def memory_read(topic: str) -> str:
            content = self._long_term.read_topic(topic)
            return content or f"No memory found for topic: {topic}"

        async def memory_write(
            topic: str, content: str, action: str = "append"
        ) -> str:
            blocked = llm_blocked_topic_reply(topic)
            if blocked:
                return blocked
            if action == "replace":
                self._long_term.write_topic(topic, content)
            else:
                self._long_term.append_to_topic(topic, content)
            return f"Memory updated: {topic}"

        async def work_project_patch(
            project_heading: str, action: str, body: str = ""
        ) -> str:
            raw = self._long_term.read_topic("work_projects") or ""
            try:
                new_text = apply_work_project_patch(raw, project_heading, action, body)
            except ValueError as e:
                return str(e)
            self._long_term.write_topic("work_projects", new_text)
            self._memory_index.update_section(
                "work_projects",
                "-> memory/work_projects.md\n长期项目（定点维护）",
            )
            emit_event(
                "work_project_patch",
                heading=project_heading,
                action=action,
            )
            return f"已更新项目块: {project_heading}"

        tc.register(
            "work_project_patch",
            "对 memory/work_projects.md 中单个「## 项目名」区块定点增删改（add/update/remove），"
            "不整文件覆盖。改前可先 memory_read topic=work_projects。",
            {
                "type": "object",
                "properties": {
                    "project_heading": {"type": "string"},
                    "action": {"type": "string", "enum": ["add", "update", "remove"]},
                    "body": {"type": "string", "description": "该块正文，不含 ##；remove 可空"},
                },
                "required": ["project_heading", "action"],
            },
            work_project_patch,
            PermissionLevel.CONFIRM,
        )

        tc.register(
            "memory_read", "读取 L3 长期记忆某主题（推断性用户画像）",
            {"type": "object", "properties": {
                "topic": {"type": "string",
                          "description": "主题名: portrait/preferences/.../work_projects/segment_activity 等"}
            }, "required": ["topic"]},
            memory_read,
        )
        tc.register(
            "memory_write",
            "写入 L3 用户画像（推断性认知：性格/习惯/偏好规律/社交关系等）。"
            "账号、服务器、基本信息等结构化事实请用 identity_set 写 L0，不要写这里。"
            "topic 选: portrait/preferences/routines/skills_interests/social/health/emotional_patterns/iot_preferences。"
            "长期项目清单用 work_project_patch，勿 memory_write work_projects；勿写 segment_activity。",
            {"type": "object", "properties": {
                "topic": {"type": "string"},
                "content": {"type": "string"},
                "action": {"type": "string", "enum": ["append", "replace"]},
            }, "required": ["topic", "content"]},
            memory_write, PermissionLevel.CONFIRM,
        )

        # ── Mid-Term Memory tool (L2) ────────────────

        async def midterm_read(days: int = 1) -> str:
            """Query recent episodic memory: recent segments or daily summaries."""
            if days <= 1:
                segs = self._mid_term.get_recent_segments(4)
                return "\n\n---\n\n".join(segs) if segs else "暂无近期活动片段"
            dailies = self._mid_term.get_recent_dailies(min(days, 14))
            return "\n\n---\n\n".join(dailies) if dailies else "暂无日摘要记录"

        tc.register(
            "midterm_read",
            "查询最近的活动摘要。days=1 返回最近4个30分钟片段；days>1 返回最近N天的日摘要",
            {"type": "object", "properties": {
                "days": {
                    "type": "integer",
                    "description": "1=最近片段(默认), 2-14=查最近N天日摘要",
                    "default": 1,
                },
            }},
            midterm_read,
        )

        # ── Screenpipe tool ──────────────────────────

        if self._screenpipe:
            async def screenpipe_search(minutes: int = 30, query: str = "") -> str:
                from physi_core.integrations.screenpipe import ScreenpipeClient
                frames = await self._screenpipe.search_ocr(
                    minutes=minutes, query=query or None,
                )
                groups = ScreenpipeClient.group_and_deduplicate(frames)
                return ScreenpipeClient.format_for_llm(groups)

            tc.register(
                "screenpipe_search", "搜索最近的屏幕 OCR 文本",
                {"type": "object", "properties": {
                    "minutes": {"type": "integer", "default": 30},
                    "query": {"type": "string", "default": ""},
                }},
                screenpipe_search,
            )

        # ── ActivityWatch tool ───────────────────────

        if self._aw:
            async def aw_query(minutes: int = 30) -> str:
                from physi_core.integrations.activitywatch import ActivityWatchClient
                usages = await self._aw.get_app_usage(minutes)
                return ActivityWatchClient.format_for_llm(usages)

            tc.register(
                "aw_query", "查询最近的应用使用统计",
                {"type": "object", "properties": {
                    "minutes": {"type": "integer", "default": 30},
                }},
                aw_query,
            )

        # ── Home Assistant tools ─────────────────────

        if self._ha:
            async def ha_query(entity_id: str) -> str:
                state = await self._ha.get_state(entity_id)
                if not state:
                    return f"找不到设备: {entity_id}"
                return f"{state.friendly_name or entity_id}: {state.state}"

            async def ha_control(entity_id: str, action: str) -> str:
                if action == "on":
                    ok = await self._ha.turn_on(entity_id)
                elif action == "off":
                    ok = await self._ha.turn_off(entity_id)
                else:
                    return f"未知操作: {action}，支持: on, off"
                return "操作成功" if ok else "操作失败"

            async def ha_list(domain: str = "") -> str:
                entities = await self._ha.list_entities(domain or None)
                if not entities:
                    return "没有找到设备"
                lines = [f"- {e.entity_id}: {e.state} ({e.friendly_name})" for e in entities[:20]]
                return "\n".join(lines)

            tc.register(
                "ha_query", "查询智能家居设备当前状态",
                {"type": "object", "properties": {
                    "entity_id": {"type": "string", "description": "设备 entity_id，如 light.study_ceiling"},
                }, "required": ["entity_id"]},
                ha_query,
            )
            tc.register(
                "ha_control", "控制智能家居设备（打开或关闭）",
                {"type": "object", "properties": {
                    "entity_id": {"type": "string", "description": "设备 entity_id"},
                    "action": {"type": "string", "enum": ["on", "off"]},
                }, "required": ["entity_id", "action"]},
                ha_control, PermissionLevel.CONFIRM,
            )
            tc.register(
                "ha_list", "列出智能家居设备，可按 domain 过滤",
                {"type": "object", "properties": {
                    "domain": {"type": "string", "description": "设备类型，如 light, switch，留空列全部"},
                }},
                ha_list,
            )

    # ── Perception Pipeline ────────────────────────

    async def _collect_perception_data(self) -> str:
        """Gather data from all perception sources."""
        parts: list[str] = []
        ocr_count = 0
        dedup_count = 0
        aw_count = 0

        if self._screenpipe:
            try:
                from physi_core.integrations.screenpipe import ScreenpipeClient
                frames = await self._screenpipe.search_ocr(minutes=30)
                ocr_count = len(frames)
                # Privacy filter before grouping
                if self._privacy:
                    frames = [
                        f for f in frames
                        if not self._privacy.should_skip_app(f.app_name)
                        and not self._privacy.contains_sensitive(f.text)
                    ]
                groups = ScreenpipeClient.group_and_deduplicate(frames)
                dedup_count = sum(g.frame_count for g in groups)
                if groups:
                    text = ScreenpipeClient.format_for_llm(groups)
                    if self._privacy:
                        text = self._privacy.redact(text)
                    parts.append("## 屏幕活动 (OCR)\n" + text)
                logger.debug(
                    "OCR pipeline: %d raw → %d kept across %d windows",
                    ocr_count,
                    dedup_count,
                    len(groups),
                )
            except Exception:
                logger.warning("Screenpipe data collection failed")
                emit_event("perception.ocr.error")

        if self._aw:
            try:
                from physi_core.integrations.activitywatch import ActivityWatchClient
                usages = await self._aw.get_app_usage(minutes=30)
                aw_count = len(usages)
                if usages:
                    parts.append("## 应用统计\n" + ActivityWatchClient.format_for_llm(usages))
            except Exception:
                logger.warning("ActivityWatch data collection failed")
                emit_event("perception.aw.error")

        if self._clipboard:
            clip_text = self._clipboard.format_for_llm(3)
            if clip_text:
                if self._privacy:
                    clip_text = self._privacy.redact(clip_text)
                parts.append(clip_text)

        payload = {
            "ocr_frame_count": ocr_count,
            "ocr_after_dedup": dedup_count,
            "app_usage_count": aw_count,
            "parts_count": len(parts),
            "perception_preview": ("\n\n".join(parts))[:3000] if parts else "none",
        }
        emit_event("perception.snapshot", **payload)
        return "\n\n".join(parts) if parts else "无感知数据"

    async def _get_continuous_hours(self) -> float:
        """Get continuous non-AFK usage hours from ActivityWatch."""
        if not self._aw:
            return 0.0
        try:
            return await self._aw.get_continuous_usage_hours()
        except Exception:
            logger.warning("Failed to get continuous usage hours")
            return 0.0

    # ── Timer Callbacks ────────────────────────────

    async def _on_segment_timer(self) -> None:
        """Aligned 30-min timer: collect → summarize → write segment → maybe notify."""
        logger.info("Segment timer triggered")
        trace_id = start_trace("perception_segment")
        try:
            raw_data = await self._collect_perception_data()
            continuous_hours = await self._get_continuous_hours()
            current_time = datetime.now().strftime("%H:%M")

            result = await self._consolidator.summarize_segment(
                raw_data=raw_data,
                current_time=current_time,
                continuous_hours=continuous_hours,
            )

            self._mid_term.write_segment(result.summary, ts=datetime.now())

            # Persist high-signal structured outputs:
            # - stable facts -> metadata
            # - project progress -> long-term memory
            for item in (result.metadata_updates or []):
                key = str(item.get("key", "")).strip()
                value = str(item.get("value", "")).strip()
                if key and value:
                    self._identity.set(key, value)

            if result.active_projects or result.learning_topics:
                lines = [f"- [{datetime.now().strftime('%Y-%m-%d %H:%M')}] segment insight"]
                if result.active_projects:
                    lines.append(f"  projects: {', '.join(result.active_projects)}")
                if result.learning_topics:
                    lines.append(f"  topics: {', '.join(result.learning_topics)}")
                self._long_term.append_to_topic("segment_activity", "\n".join(lines))
                self._memory_index.update_section(
                    "segment_activity",
                    "-> memory/segment_activity.md\n定时片段 projects/topics 线索（机器追加）。",
                )

            if result.should_notify and self._qq:
                if self._is_sleep_time():
                    logger.info("Skipping notification during sleep window: %s", result.notify_message)
                else:
                    await self._qq.send_private_message(result.notify_message)
                    logger.info("Notification sent: %s", result.notify_message)

            end_trace(trace_id, "ok", notify=result.should_notify, projects=", ".join(result.active_projects or []))
        except Exception as e:
            logger.exception("Failed segment timer")
            end_trace(trace_id, "error", error=str(e))

    async def _on_daily_merge(self) -> None:
        """Daily: merge today's segments, clean up old files."""
        today = datetime.now().strftime("%Y-%m-%d")
        logger.info("Daily merge for %s", today)
        trace_id = start_trace("perception_daily")
        try:
            result = await self._consolidator.merge_daily(today)

            if result.recyclable:
                self._mid_term.cleanup_segments(result.recyclable)

            # TTL cleanup
            self._mid_term.cleanup_old_segments(max_days=3)
            self._mid_term.cleanup_old_dailies(max_days=30)
            end_trace(trace_id, "ok")
        except Exception as e:
            logger.exception("Failed daily merge")
            end_trace(trace_id, "error", error=str(e))

    async def _on_weekly_review(self) -> None:
        """Weekly: deep L3 review + write weekly summary + clean old weeklies."""
        logger.info("Weekly review triggered")
        trace_id = start_trace("perception_weekly")
        try:
            await self._consolidator.weekly_review()
            self._mid_term.cleanup_old_weeklies(max_weeks=12)
            end_trace(trace_id, "ok")
        except Exception as e:
            logger.exception("Failed weekly review")
            end_trace(trace_id, "error", error=str(e))

    # ── Aligned Segment Timer ──────────────────────

    async def _aligned_segment_loop(self) -> None:
        """Run segment timer aligned to :00 or :30 (+ 2 min buffer)."""
        while True:
            now = datetime.now()
            if now.minute < 30:
                target = now.replace(minute=30, second=0, microsecond=0)
            else:
                target = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            target += timedelta(minutes=2)

            wait = (target - now).total_seconds()
            logger.debug("Next segment in %.0fs (at %s)", wait, target.strftime("%H:%M"))
            await asyncio.sleep(wait)

            try:
                await self._on_segment_timer()
            except Exception:
                logger.exception("Segment timer failed")

    # ── Message Handling ───────────────────────────

    async def handle_message(self, text: str, source: str = "cli", system_events: str = "") -> str:
        """Process a user message through the agent loop."""
        logger.info("Handling message from %s: %s", source, text.strip()[:100])
        emit_event("message.received", source=source, text_preview=text.strip()[:200])
        self._short_term.add_message("user", text, source=source)

        conversation = self._short_term.get_messages_for_llm()
        system_prompt = self._build_system_prompt(system_events=system_events)
        emit_event(
            "llm.context.built",
            source=source,
            conversation_messages=len(conversation),
            system_prompt_len=len(system_prompt),
            # 看板折叠行只显示摘要，勿把整段 system/对话塞进 trace 事件
            system_prompt_preview=(system_prompt[:160] + "…") if len(system_prompt) > 160 else system_prompt,
            conversation_tail_roles=[m.get("role", "?") for m in conversation[-6:]],
        )

        result = await self._agent.run(text, conversation[:-1], system=system_prompt)

        self._short_term.add_message(
            "assistant", result.text, thinking=result.thinking,
        )

        # Async: extract session info (throttled)
        asyncio.create_task(self._maybe_extract_session())

        logger.info(
            "Response: %d rounds, %d→%d tokens",
            result.rounds,
            result.total_usage["input_tokens"],
            result.total_usage["output_tokens"],
        )
        emit_event(
            "message.responded",
            source=source,
            rounds=result.rounds,
            input_tokens=result.total_usage["input_tokens"],
            output_tokens=result.total_usage["output_tokens"],
            response_preview=result.text[:300],
        )

        return result.text

    async def _maybe_extract_session(self) -> None:
        """Throttled: extract notable info from session."""
        async def _do_extract() -> None:
            trace_id = start_trace("session_extract")
            try:
                msgs = self._short_term.get_messages()
                if len(msgs) < 2:
                    end_trace(trace_id, "ok", writes=0)
                    return
                conv_text = "\n".join(
                    f"{m['role']}: {m.get('content', '')}" for m in msgs[-10:]
                )
                result = await self._consolidator.extract_from_session(conv_text)
                end_trace(trace_id, "ok")
            except Exception as e:
                logger.exception("Failed session extract")
                end_trace(trace_id, "error", error=str(e))

        await self._throttle.try_run(_do_extract)

    # ── QQ Message Handler ─────────────────────────

    async def _on_qq_message(self, event: dict[str, Any]) -> None:
        """Handle incoming QQ private message.

        Per PRD Path B: respond immediately, then trigger perception in background.
        The agent can always call screenpipe_search / aw_query tools on demand.
        """
        from physi_core.integrations.qq import QQClient
        text = QQClient.extract_text(event)
        user_id = QQClient.extract_user_id(event)
        if not text.strip():
            return
            
        trace_id = start_trace("qq_message", text_preview=text[:200], user_id=user_id)
        try:
            emit_event("qq.message.in", user_id=user_id, text_preview=text[:200])
            response = await self.handle_message(text, source="qq")
            await self._qq.send_private_message(response, user_id=user_id or None)
            emit_event("qq.message.out", user_id=user_id, text_preview=response[:200])
            end_trace(trace_id, "ok", reply_preview=response[:200])
        except Exception as e:
            logger.exception("Failed to handle QQ message")
            emit_event("qq.message.error", user_id=user_id)
            end_trace(trace_id, "error", error=str(e))
            return

        # Background: throttled segment summarization (PRD Path B, 10-min cooldown)
        asyncio.create_task(
            self._perception_throttle.try_run(self._on_segment_timer)
        )

    # ── Lifecycle ──────────────────────────────────

    async def start(self) -> None:
        """Start all background systems."""
        self._init_components()
        if self._obs is not None and self._settings.monitor.enabled:
            self._obs.start_server(host=self._settings.monitor.host, port=self._settings.monitor.port)
            logger.info(
                "Monitor UI: http://%s:%d/",
                self._settings.monitor.host,
                self._settings.monitor.port,
            )

        # Aligned 30-min segment timer
        asyncio.create_task(self._aligned_segment_loop())

        # Daily merge at 23:55 UTC
        self._scheduler.start()
        self._scheduler.add_daily("daily_merge", self._on_daily_merge, hour=23, minute=55)

        # Weekly review on Sunday at 23:50 UTC
        self._scheduler.add_daily(
            "weekly_review_check",
            self._weekly_review_if_sunday,
            hour=23, minute=50,
        )

        # QQ client (Reverse WebSocket Server)
        owner_raw = self._settings.qq.owner_qq
        if isinstance(owner_raw, list):
            owner_list = [str(v) for v in owner_raw if str(v).strip()]
            primary_owner = owner_list[0] if owner_list else ""
        else:
            primary_owner = str(owner_raw).strip()
        talk_qqs = self._settings.qq.talk_qq or ([primary_owner] if primary_owner else [])
        if talk_qqs:
            from physi_core.integrations.qq import QQClient
            self._qq = QQClient(self._settings.qq.ws_url, talk_qqs)
            self._qq.on_private_message(self._on_qq_message)

            async def _qq_task() -> None:
                try:
                    await self._qq.start()
                except Exception:
                    logger.exception("QQ WebSocket server crashed")

            asyncio.create_task(_qq_task())
            # Give the server a moment to bind to the port
            await asyncio.sleep(1)
            logger.info(
                "QQ WS server started (ws_url=%s, owner_qq=%s, talk_qq=%s)",
                self._settings.qq.ws_url,
                primary_owner,
                talk_qqs,
            )

        # Autostart NapCatQQ after Server is ready (local reverse ws only)
        ws_host = ""
        try:
            ws_host = (urlparse(self._settings.qq.ws_url).hostname or "").lower()
        except ValueError:
            ws_host = ""
        if primary_owner and ws_host in {"localhost", "127.0.0.1", "0.0.0.0"}:
            from physi_core.integrations.napcat import NapCatManager
            self._napcat_manager = NapCatManager(
                self._data_dir,
                primary_owner,  # NapCat logs in with the primary QQ
                self._settings.qq.ws_url,
            )
            if not await self._napcat_manager.start():
                logger.error("Failed to start NapCatQQ manager.")

        logger.info("PhysiBot started")

    async def _weekly_review_if_sunday(self) -> None:
        """Trigger weekly review only on Sundays."""
        if datetime.now().weekday() == 6:  # Sunday
            await self._on_weekly_review()

    async def stop(self) -> None:
        """Graceful shutdown."""
        if self._scheduler:
            await self._scheduler.stop()

        if self._qq:
            await self._qq.stop()
            
        if self._napcat_manager:
            await self._napcat_manager.stop()
        if self._obs is not None:
            self._obs.stop_server()

        if self._short_term and self._short_term.message_count > 0:
            try:
                msgs = self._short_term.get_messages()
                conv = "\n".join(
                    f"{m['role']}: {m.get('content', '')}" for m in msgs
                )
                await self._consolidator.extract_from_session(conv)
            except Exception:
                logger.warning("Final session extraction failed")
            self._short_term.end_session()

        logger.info("PhysiBot stopped")


async def server_loop(settings: Settings) -> None:
    """Server mode: start all services and run until interrupted (no stdin needed).

    Used when stdin is not a TTY — e.g. launched as a background subprocess.
    """
    bot = PhysiBot(settings)
    await bot.start()
    logger.info("PhysiBot running in server mode (Ctrl+C to stop)")
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await bot.stop()


async def cli_loop(settings: Settings) -> None:
    """Interactive CLI loop for development/testing."""
    bot = PhysiBot(settings)
    await bot.start()

    name = bot._identity.get("name") or "用户"
    print("PhysiBot CLI — 输入消息开始对话 (输入 /quit 退出)")
    print(f"   LLM: {settings.llm.provider}/{settings.llm.model}")
    print(f"   身份: {name}")
    print()

    try:
        while True:
            try:
                user_input = await asyncio.to_thread(input, "你: ")
                user_input = user_input.strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                break

            if not user_input:
                continue
            if user_input.lower() in ("/quit", "/exit", "退出"):
                print("再见！")
                break

            try:
                trace_id = start_trace("cli_message", text_preview=user_input[:200])
                response = await bot.handle_message(user_input)
                print(f"🤖: {response}")
                print()
                end_trace(trace_id, "ok", reply_preview=response[:200])
            except Exception as e:
                print(f"❌ 错误: {e}")
                logger.exception("Message handling failed")
                end_trace(trace_id, "error", error=str(e))
    finally:
        await bot.stop()


def main() -> None:
    """Entry point."""
    logs_dir = Path("physi-data/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    runtime_log = logs_dir / "runtime.log"

    # Force UTF-8 on stdout so Chinese log entries don't garble on Windows (GBK terminal)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(runtime_log, encoding="utf-8"),
        ],
    )
    for _noisy in ("httpx", "httpcore", "websockets", "asyncio"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)

    config_path = Path("physi-data/config.yaml")
    if not config_path.exists():
        print("⚠️  未找到 physi-data/config.yaml")
        print("   请复制 config.yaml.example 为 config.yaml 并填写配置")
        sys.exit(1)

    settings = load_settings(config_path)

    if not settings.llm.api_key:
        print("⚠️  请设置 LLM API Key")
        sys.exit(1)

    if "--cli" in sys.argv:
        asyncio.run(cli_loop(settings))
    else:
        asyncio.run(server_loop(settings))


if __name__ == "__main__":
    main()
