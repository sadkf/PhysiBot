# PhysiBot

**一个活在你身边的 AI 助手——它记得你、懂你，并能与你通过 QQ 等方式交流。**

> 本项目为 Python 应用，**不要求**事先安装 Node.js。只有在你自行接入 **NapCat（QQ 机器人）** 等依赖 Node 的组件时，才需要单独安装 Node.js LTS。

---

## 核心特性

- **五层记忆系统** — 身份记忆 / 短期对话 / 中期活动 / 长期画像 / 系统指令
- **屏幕与活动感知**（可选）— 通过 Screenpipe、ActivityWatch 了解本机操作，默认可在配置中关闭
- **IoT 控制**（可选）— 通过 Home Assistant 操控智能家居
- **QQ 对接**（可选）— 在私聊中与助手对话
- **模型无关** — 支持 MiniMax / Anthropic / OpenAI，一行配置切换

---

## 获取代码（无需 GitHub 账号）

任选其一即可，**不必**登录或绑定 GitHub：

1. **ZIP 下载**：在代码托管页面使用「Download ZIP / 下载源码包」，解压到任意英文路径（避免中文路径在部分环境下出问题）。
2. **国内镜像**：若你或维护者提供了 Gitee / GitCode 等镜像，从镜像克隆或下载 ZIP 即可。
3. **已安装 Git 的用户**：`git clone <镜像地址>`（地址以你实际使用的托管站为准）。

仓库里的 `physi-data/MEMORY.md` 与 `physi-data/memory/` 下的记忆文件在发布版中为空或仅作说明；**你的个人记忆只应留在本机**，首次使用请自行在对话中建立身份，或按文档初始化本地数据目录。

---

## 环境要求

| 组件 | 说明 |
|------|------|
| **Python** | 3.11 及以上（[python.org](https://www.python.org/downloads/) 或国内镜像站安装包） |
| **uv**（推荐） | 用于安装依赖与运行；也可用 `pip` + 虚拟环境（见下文） |
| **Node.js** | **仅在使用 NapCat 等需要 Node 的组件时**再安装 [Node.js LTS](https://nodejs.org/zh-cn)；国内用户可使用淘宝 NPM 镜像文档中的 Node 安装指引 |

---

## 快速开始（Windows 推荐）

在解压后的项目根目录打开 **PowerShell**：

```powershell
# 1）安装 uv（若尚未安装，任选一种）
# 官方安装脚本（需允许执行脚本时）:
# irm https://astral.sh/uv/install.ps1 | iex
# 或使用 pip:
python -m pip install -U uv

# 2）安装项目依赖
uv sync

# 3）准备配置
Copy-Item physi-data\config.yaml.example physi-data\config.yaml
# 用记事本或 VS Code 编辑 physi-data\config.yaml，至少填写 llm.api_key

# 4）运行
uv run python -m physi_core
```

可选：运行 `powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1` 检查本机 Python / uv 是否可用。

### 没有 uv 时（仅用 pip）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m physi_core
```

---

## macOS / Linux

```bash
# 安装 uv 后
uv sync
cp physi-data/config.yaml.example physi-data/config.yaml
# 编辑 physi-data/config.yaml
uv run python -m physi_core
```

---

## 配置说明（最小可运行）

- 复制 `physi-data/config.yaml.example` 为 `physi-data/config.yaml`。
- **至少**填写 `llm.api_key` 以及你所用平台的模型名（见示例中的 `provider` / `model`）。
- 示例配置中 **已默认关闭** Screenpipe 与 ActivityWatch，无需在本机安装感知服务即可先启动主程序；需要时再改为 `enabled: true` 并安装对应软件。
- QQ、Home Assistant 等为可选项，按注释填写即可。

---

## 开发

```bash
uv sync --group dev
uv run pytest
uv run ruff format
uv run ruff check
uv run mypy --strict src/
```

---

## 项目结构

```
PhysiBot/
├── src/physi_core/          # 核心代码
├── tests/                   # 测试
├── physi-data/              # 用户数据（敏感项已在 .gitignore 中忽略）
├── scripts/                 # 辅助脚本（如环境检查）
├── docs/                    # 技术文档
└── pyproject.toml
```

---

## 文档

- [技术架构](docs/architecture.md)
- [代码规范](docs/coding-standards.md)
- [TDD 开发指南](docs/tdd-guide.md)

---

## 开发路线（摘要）

- Phase 1–2：Agent、记忆、感知与 QQ 对接（持续迭代）
- 后续：长期记忆深化、IoT、打包与可视化等

---

## License

MIT
