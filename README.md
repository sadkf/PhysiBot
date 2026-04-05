# 🤖 PhysiBot

**一个活在你身边的 AI 助手——它记得你、懂你、能替你操控物理世界。**

> 不止于消息。PhysiBot 通过 QQ 与你交流，知道你在做什么（屏幕感知），了解你的习惯（五层记忆），还能替你控制智能家居。

---

## ✨ 核心特性

- 🧠 **五层记忆系统** — 身份记忆 / 短期对话 / 中期活动 / 长期画像 / 系统指令
- 👀 **屏幕感知** — 通过 Screenpipe + ActivityWatch 了解你的电脑操作
- 🏠 **IoT 控制** — 通过 Home Assistant 操控智能家居
- 💬 **QQ 原生** — 在 QQ 私聊中像朋友一样交流
- 🔄 **智能记忆管理** — LLM 驱动的记忆压缩/合并/遗忘，不做死板的定时删除
- 🔌 **模型无关** — 支持 MiniMax / Anthropic / OpenAI，一行配置切换

## 🚀 快速开始

```bash
# 克隆
git clone https://github.com/sadkf/PhysiBot.git
cd PhysiBot

# 安装依赖
uv sync

# 复制配置模板
cp physi-data/config.yaml.example physi-data/config.yaml
# 编辑 config.yaml，填入 API Key 等信息

# 运行
uv run python -m physi_core
```

## 🧪 开发

```bash
# 安装开发依赖
uv sync --group dev

# TDD: 先跑测试
uv run pytest

# 格式化 + Lint
uv run ruff format
uv run ruff check

# 类型检查
uv run mypy --strict src/
```

## 📁 项目结构

```
PhysiBot/
├── src/physi_core/          # 核心代码
│   ├── agent/               # Agent Loop + Tools + Prompts
│   ├── memory/              # 五层记忆系统
│   ├── llm/                 # LLM 适配层
│   ├── integrations/        # Screenpipe / AW / HA / QQ
│   ├── events/              # 事件总线
│   └── config/              # 配置管理
├── tests/                   # 测试
├── physi-data/              # 用户数据 (本地, 不上传)
├── docs/                    # 技术文档
└── pyproject.toml           # 项目配置
```

## 📖 文档

- [技术架构](docs/architecture.md)
- [代码规范](docs/coding-standards.md)
- [TDD 开发指南](docs/tdd-guide.md)

## 📋 开发路线

- [x] 项目规划 + PRD
- [ ] Phase 1: Agent Core + 记忆系统 MVP
- [ ] Phase 2: 感知接入 + QQ 对接
- [ ] Phase 3: 长期记忆 + IoT 接入
- [ ] Phase 4: 打包 exe + Dashboard
- [ ] Phase 5: 开源发布

## 📄 License

MIT
