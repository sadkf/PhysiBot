"""PhysiBot main entry point — starts all subsystems."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from physi_core.config.settings import Settings, load_settings

logger = logging.getLogger("physi_core")


async def cli_loop(settings: Settings) -> None:
    """Simple CLI interaction loop for development/testing."""
    from physi_core.agent.loop import AgentLoop
    from physi_core.agent.prompts import build_system_prompt, load_physi_md
    from physi_core.agent.tools import ToolController
    from physi_core.llm.adapter import LLMClient
    from physi_core.memory.identity import IdentityMemory
    from physi_core.memory.index import MemoryIndex
    from physi_core.memory.long_term import LongTermMemory
    from physi_core.memory.short_term import ShortTermMemory

    data_dir = settings.data_dir

    # Initialize memory layers
    identity = IdentityMemory(data_dir / "identity" / "profile.jsonl")
    short_term = ShortTermMemory(data_dir / "short_term")
    memory_index = MemoryIndex(data_dir / "MEMORY.md")
    long_term = LongTermMemory(data_dir / "memory")

    # Load PHYSI.md
    physi_md = load_physi_md(str(data_dir / "PHYSI.md"))

    # Build system prompt
    system_prompt = build_system_prompt(
        physi_md_content=physi_md,
        identity=identity,
        memory_index=memory_index,
        long_term=long_term,
    )

    # Initialize LLM + Agent Loop
    llm_client = LLMClient(settings.llm)
    tool_controller = ToolController()

    agent = AgentLoop(
        llm_client=llm_client,
        tool_controller=tool_controller,
        system_prompt=system_prompt,
    )

    print("🤖 PhysiBot CLI — 输入消息开始对话 (输入 /quit 退出)")
    print(f"   LLM: {settings.llm.provider}/{settings.llm.model}")
    print(f"   身份: {identity.get('name', '未设置')}")
    print()

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("/quit", "/exit", "退出"):
            print("再见！")
            break

        # Record user message
        short_term.add_message("user", user_input, source="cli")

        # Run agent loop
        conversation = short_term.get_messages_for_llm()
        try:
            result = await agent.run(user_input, conversation[:-1])  # exclude current
        except Exception as e:
            print(f"❌ 错误: {e}")
            continue

        # Record and display response
        short_term.add_message("assistant", result.text, thinking=result.thinking)
        print(f"🤖: {result.text}")
        in_tok = result.total_usage["input_tokens"]
        out_tok = result.total_usage["output_tokens"]
        print(f"   [{in_tok}→{out_tok} tokens, {result.rounds} round(s)]")
        print()


def main() -> None:
    """Entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    config_path = Path("physi-data/config.yaml")
    if not config_path.exists():
        print("⚠️  未找到配置文件。请复制 physi-data/config.yaml.example 为 physi-data/config.yaml")
        print("   并填入你的 API Key。")
        sys.exit(1)

    settings = load_settings(config_path)

    if not settings.llm.api_key or settings.llm.api_key == "your-api-key-here":
        print("⚠️  请在 physi-data/config.yaml 中设置你的 LLM API Key。")
        sys.exit(1)

    asyncio.run(cli_loop(settings))


if __name__ == "__main__":
    main()
