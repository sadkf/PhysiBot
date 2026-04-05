"""PhysiBot main entry point — orchestrates all subsystems."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from physi_core.config.settings import Settings, load_settings

logger = logging.getLogger("physi_core")


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
        self._screenpipe: Any = None
        self._aw: Any = None
        self._clipboard: Any = None
        self._privacy: Any = None
        self._qq: Any = None

    def _init_components(self) -> None:
        """Initialize all components."""
        from physi_core.agent.loop import AgentLoop
        from physi_core.agent.prompts import build_system_prompt, load_physi_md
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

        # Memory layers
        self._identity = IdentityMemory(d / "identity" / "profile.jsonl")
        self._short_term = ShortTermMemory(d / "short_term")
        self._mid_term = MidTermMemory(d / "mid_term")
        self._long_term = LongTermMemory(d / "memory")
        self._memory_index = MemoryIndex(d / "MEMORY.md")

        # LLM
        self._llm = LLMClient(self._settings.llm)

        # Consolidator
        self._consolidator = Consolidator(
            self._llm, self._mid_term, self._long_term, self._memory_index,
        )

        # Privacy filter
        from physi_core.integrations.privacy import PrivacyFilter
        self._privacy = PrivacyFilter(
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
        self._clipboard = ClipboardMonitor(
            poll_interval=cb.poll_interval
        ) if cb.enabled else None

        # Tools
        self._tools = ToolController()
        self._register_tools(self._tools)

        # Build system prompt
        physi_md = load_physi_md(str(d / "PHYSI.md"))
        system_prompt = build_system_prompt(
            physi_md_content=physi_md,
            identity=self._identity,
            memory_index=self._memory_index,
            long_term=self._long_term,
            today_summary=self._mid_term.get_today_summary(),
            recent_segments="\n---\n".join(
                self._mid_term.get_recent_segments(2)
            ),
        )

        # Agent Loop
        self._agent = AgentLoop(
            llm_client=self._llm,
            tool_controller=self._tools,
            system_prompt=system_prompt,
        )

        # Scheduler + Throttle
        self._scheduler = Scheduler()
        self._throttle = Throttle(
            cooldown_seconds=self._settings.agent.user_trigger_cooldown
        )

    def _register_tools(self, tc: Any) -> None:
        """Register all available tools."""
        from physi_core.agent.tools import PermissionLevel

        # ── Identity tools (L0) ──────────────────────

        async def identity_get(key: str) -> str:
            val = self._identity.get(key)
            if val is None:
                return f"未找到身份信息: {key}"
            return f"{key}: {val}"

        async def identity_set(key: str, value: str) -> str:
            self._identity.set(key, value)
            return f"已记录: {key} = {value}"

        async def identity_list() -> str:
            keys = self._identity.all_keys()
            if not keys:
                return "身份信息为空，还不了解用户"
            lines = ["当前已知身份信息:"]
            for k in keys:
                lines.append(f"  {k}: {self._identity.get(k)}")
            return "\n".join(lines)

        async def identity_delete(key: str) -> str:
            if self._identity.delete(key):
                return f"已删除: {key}"
            return f"未找到: {key}"

        tc.register(
            "identity_get", "获取用户的某项身份信息",
            {"type": "object", "properties": {
                "key": {
                    "type": "string",
                    "description": "信息键名，如: name, age, occupation",
                },
            }, "required": ["key"]},
            identity_get,
        )
        tc.register(
            "identity_set",
            "记录或更新用户的身份信息（姓名、年龄、偏好等）",
            {"type": "object", "properties": {
                "key": {
                    "type": "string",
                    "description": "英文小写下划线格式的键名",
                },
                "value": {
                    "type": "string",
                    "description": "信息内容（中文描述）",
                },
            }, "required": ["key", "value"]},
            identity_set,
        )
        tc.register(
            "identity_list", "列出当前已知的全部用户身份信息",
            {"type": "object", "properties": {}},
            identity_list,
        )
        tc.register(
            "identity_delete", "删除某项身份信息",
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
            if action == "replace":
                self._long_term.write_topic(topic, content)
            else:
                self._long_term.append_to_topic(topic, content)
            return f"Memory updated: {topic}"

        tc.register(
            "memory_read", "读取长期记忆中的某个主题文件",
            {"type": "object", "properties": {
                "topic": {"type": "string", "description": "主题名"}
            }, "required": ["topic"]},
            memory_read,
        )
        tc.register(
            "memory_write", "写入长期记忆",
            {"type": "object", "properties": {
                "topic": {"type": "string"},
                "content": {"type": "string"},
                "action": {"type": "string", "enum": ["append", "replace"]},
            }, "required": ["topic", "content"]},
            memory_write, PermissionLevel.CONFIRM,
        )

        # Screenpipe tool
        if self._screenpipe:
            async def screenpipe_search(
                minutes: int = 30, query: str = ""
            ) -> str:
                from physi_core.integrations.screenpipe import ScreenpipeClient
                frames = await self._screenpipe.search_ocr(
                    minutes=minutes, query=query or None,
                )
                unique = ScreenpipeClient.deduplicate(frames)
                return ScreenpipeClient.format_for_llm(unique)

            tc.register(
                "screenpipe_search", "搜索最近的屏幕 OCR 文本",
                {"type": "object", "properties": {
                    "minutes": {"type": "integer", "default": 30},
                    "query": {"type": "string", "default": ""},
                }},
                screenpipe_search,
            )

        # ActivityWatch tool
        if self._aw:
            async def aw_query(minutes: int = 30) -> str:
                from physi_core.integrations.activitywatch import (
                    ActivityWatchClient,
                )
                usages = await self._aw.get_app_usage(minutes)
                return ActivityWatchClient.format_for_llm(usages)

            tc.register(
                "aw_query", "查询最近的应用使用统计",
                {"type": "object", "properties": {
                    "minutes": {"type": "integer", "default": 30},
                }},
                aw_query,
            )

    # ── Perception Pipeline ────────────────────────

    async def _collect_perception_data(self) -> str:
        """Gather data from all perception sources."""
        parts: list[str] = []

        if self._screenpipe:
            try:
                from physi_core.integrations.screenpipe import ScreenpipeClient
                frames = await self._screenpipe.search_ocr(minutes=30)
                unique = ScreenpipeClient.deduplicate(frames)
                # Privacy: filter out sensitive apps and content
                if self._privacy:
                    unique = [
                        f for f in unique
                        if not self._privacy.should_skip_app(f.app_name)
                        and not self._privacy.contains_sensitive(f.text)
                    ]
                if unique:
                    text = ScreenpipeClient.format_for_llm(unique)
                    if self._privacy:
                        text = self._privacy.redact(text)
                    parts.append("## 屏幕活动 (OCR)\n" + text)
            except Exception:
                logger.warning("Screenpipe data collection failed")

        if self._aw:
            try:
                from physi_core.integrations.activitywatch import (
                    ActivityWatchClient,
                )
                usages = await self._aw.get_app_usage(minutes=30)
                if usages:
                    parts.append(
                        "## 应用统计\n"
                        + ActivityWatchClient.format_for_llm(usages)
                    )
            except Exception:
                logger.warning("ActivityWatch data collection failed")

        if self._clipboard:
            clip_text = self._clipboard.format_for_llm(3)
            if clip_text:
                if self._privacy:
                    clip_text = self._privacy.redact(clip_text)
                parts.append(clip_text)

        return "\n\n".join(parts) if parts else "无感知数据"

    # ── Timer Callbacks ────────────────────────────

    async def _on_segment_timer(self) -> None:
        """30-min timer: collect data → LLM summarize → write segment → maybe notify."""
        logger.info("⏰ Segment timer triggered")

        raw_data = await self._collect_perception_data()
        now = datetime.now(UTC)
        current_time = now.strftime("%H:%M")

        result = await self._consolidator.summarize_segment(
            raw_data=raw_data,
            current_time=current_time,
            continuous_hours=0,  # TODO: track from AW
        )

        # Write segment
        self._mid_term.write_segment(result.summary, ts=now)

        if result.should_notify and self._qq:
            msg = result.notify_message or "你已经工作很久了，休息一下吧 ☕"
            await self._qq.send_private_message(msg)
            logger.info("📢 Notification sent to user")

    async def _on_daily_merge(self) -> None:
        """Daily: merge today's segments into daily summary."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        logger.info("📅 Daily merge for %s", today)

        result = await self._consolidator.merge_daily(today)

        if result.recyclable:
            self._mid_term.cleanup_segments(result.recyclable)
            logger.info(
                "♻️ Recycled %d segments", len(result.recyclable)
            )

    # ── Message Handling ───────────────────────────

    async def handle_message(self, text: str, source: str = "cli") -> str:
        """Process a user message through the agent loop."""
        self._short_term.add_message("user", text, source=source)

        conversation = self._short_term.get_messages_for_llm()

        result = await self._agent.run(text, conversation[:-1])

        self._short_term.add_message(
            "assistant", result.text, thinking=result.thinking,
        )

        # Async: extract session info (throttled)
        asyncio.create_task(self._maybe_extract_session())

        in_t = result.total_usage["input_tokens"]
        out_t = result.total_usage["output_tokens"]
        logger.info(
            "Response: %d rounds, %d→%d tokens",
            result.rounds, in_t, out_t,
        )

        return result.text

    async def _maybe_extract_session(self) -> None:
        """Throttled: extract notable info from session."""
        async def _do_extract() -> None:
            msgs = self._short_term.get_messages()
            if len(msgs) < 2:
                return
            conv_text = "\n".join(
                f"{m['role']}: {m.get('content', '')}" for m in msgs[-10:]
            )
            await self._consolidator.extract_from_session(conv_text)

        await self._throttle.try_run(_do_extract)

    # ── Lifecycle ──────────────────────────────────

    async def start(self) -> None:
        """Start all background systems."""
        self._init_components()

        self._scheduler.start()

        si = self._settings.agent.segment_interval
        self._scheduler.add_interval(
            "segment_timer", self._on_segment_timer,
            interval_seconds=si,
            initial_delay=si,  # first run after one interval
        )
        self._scheduler.add_daily(
            "daily_merge", self._on_daily_merge,
            hour=23, minute=55,
        )

        logger.info("🤖 PhysiBot started")

    async def stop(self) -> None:
        """Graceful shutdown."""
        if self._scheduler:
            await self._scheduler.stop()

        # End session and extract
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

        logger.info("🤖 PhysiBot stopped")


async def cli_loop(settings: Settings) -> None:
    """Interactive CLI loop for development/testing."""
    bot = PhysiBot(settings)
    await bot.start()

    name = bot._identity.get("name", "用户")
    print("🤖 PhysiBot CLI — 输入消息开始对话 (输入 /quit 退出)")
    print(f"   LLM: {settings.llm.provider}/{settings.llm.model}")
    print(f"   身份: {name}")
    print(f"   定时器: 每 {settings.agent.segment_interval}s 采集一次")
    print()

    try:
        while True:
            try:
                user_input = await asyncio.to_thread(
                    input, "你: "
                )
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
                response = await bot.handle_message(user_input)
                print(f"🤖: {response}")
                print()
            except Exception as e:
                print(f"❌ 错误: {e}")
                logger.exception("Message handling failed")
    finally:
        await bot.stop()


def main() -> None:
    """Entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config_path = Path("physi-data/config.yaml")
    if not config_path.exists():
        print("⚠️  未找到 physi-data/config.yaml")
        print("   请复制 config.yaml.example 为 config.yaml 并填写配置")
        sys.exit(1)

    settings = load_settings(config_path)

    if not settings.llm.api_key:
        print("⚠️  请设置 LLM API Key")
        sys.exit(1)

    asyncio.run(cli_loop(settings))


if __name__ == "__main__":
    main()
