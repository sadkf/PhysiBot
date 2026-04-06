# PhysiBot

**一个活在你身边的 AI 助手——它记得你、懂你、能替你操控物理世界。**

> 不止于消息。PhysiBot 通过 QQ 与你交流，知道你在做什么（屏幕感知），了解你的习惯（五层记忆），还能替你控制智能家居。

---

## 下载使用（国内用户，无需梯子）

### 方法一：下载发行版 ZIP（推荐小白）

从 Release 页找到最新版本，用以下镜像地址下载（直接复制到浏览器）：

```
# ghfast.top 镜像（推荐，速度快）
https://ghfast.top/https://github.com/YOUR_NAME/PhysiBot/releases/download/v0.1.0/PhysiBot-0.1.0.zip

# ghproxy.net 备用
https://ghproxy.net/https://github.com/YOUR_NAME/PhysiBot/releases/download/v0.1.0/PhysiBot-0.1.0.zip
```

> 将 `YOUR_NAME` 替换为实际 GitHub 用户名，版本号替换为最新版。

**ZIP 已包含：**
- Python 3.12 嵌入包（免安装，无需管理员权限）
- 所有 Python 依赖（完全离线可用）
- ActivityWatch（应用追踪）
- NapCat（QQ 消息中间件）

**首次启动时自动下载（需网络，仅一次）：**
- Screenpipe（屏幕 OCR 感知，约 500MB，通过 ghfast.top 镜像下载）

### 使用步骤

```
1. 解压 ZIP 到任意目录（路径不要有中文）
2. 双击 setup.bat         ← 填写 API Key 和 QQ 号（只需一次）
3. 双击 一键启动.bat      ← 以后每次启动用这个
```

> **NapCat 需要已安装 QQ（NTQQ）**。若未安装，请先从 qq.com 下载安装 QQ。

---

## 方法二：开发者 / 极客模式

```bash
git clone https://github.com/YOUR_NAME/PhysiBot.git
cd PhysiBot

# 安装依赖（自动走清华 PyPI 镜像）
uv sync

# 复制配置
cp physi-data/config.yaml.example physi-data/config.yaml
# 编辑 config.yaml，填写 LLM API Key 和 QQ 号

# 启动
uv run python -m physi_core
```

---

## 核心特性

- **五层记忆系统** — 身份事实 / 短期对话 / 中期活动 / 长期画像 / 系统指令
- **屏幕感知** — 通过 Screenpipe + ActivityWatch 了解你的电脑操作
- **IoT 控制** — 通过 Home Assistant 操控智能家居
- **QQ 原生** — 在 QQ 私聊中像朋友一样交流
- **智能记忆管理** — LLM 驱动的记忆压缩/合并/遗忘
- **模型无关** — 支持 MiniMax / Anthropic / OpenAI，一行配置切换

---

## 项目结构

```
PhysiBot/
├── src/physi_core/          # 核心代码
│   ├── agent/               # Agent Loop + Tools + Prompts
│   ├── memory/              # 五层记忆系统
│   ├── llm/                 # LLM 适配层
│   ├── integrations/        # Screenpipe / AW / HA / QQ
│   └── config/              # 配置管理
├── .github/workflows/       # CI/CD（自动构建发行版）
├── scripts/                 # 辅助脚本
├── physi-data/              # 用户数据（本地，不上传）
└── pyproject.toml
```

## 开发

```bash
uv sync --group dev
uv run pytest
uv run ruff format && uv run ruff check
```

## 发布新版本

```bash
git tag v0.2.0
git push origin v0.2.0
# GitHub Actions 自动构建 ZIP 并上传到 Releases
```

## License

MIT
