# PhysiBot TDD 开发指南

> 本项目采用 **Test-Driven Development (TDD)** 开发模式。
> 规则：**先写测试，再写实现，最后重构。**

---

## 1. TDD 工作流

```
每个功能点的开发流程:

    ┌──────────────┐
    │  1. RED      │  写一个会失败的测试
    │  测试先行    │  明确这个功能"应该"怎样工作
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │  2. GREEN    │  写最少的代码让测试通过
    │  最小实现    │  不要过度设计，先让测试变绿
    └──────┬───────┘
           │
    ┌──────▼───────┐
    │  3. REFACTOR │  在测试保护下重构代码
    │  清理优化    │  提取函数、消除重复、改善命名
    └──────┬───────┘
           │
           └──→ 回到 1，下一个功能点
```

## 2. 测试分类

### 单元测试 (Unit Tests)

```
tests/unit/
├── test_identity.py          # L0 身份记忆
├── test_short_term.py        # L1 短期记忆
├── test_mid_term.py          # L2 中期记忆
├── test_long_term.py         # L3 长期记忆
├── test_index.py             # MEMORY.md 索引
├── test_consolidator.py      # AutoConsolidate
├── test_llm_adapter.py       # LLM 适配层
├── test_llm_response.py      # 响应解析
├── test_agent_loop.py        # Agent Loop
├── test_tools.py             # Tool Controller
├── test_prompts.py           # Prompt 构建
├── test_settings.py          # 配置加载
└── test_event_bus.py         # 事件总线
```

**规则**:
- 不依赖网络、不依赖外部服务
- 外部调用全部 mock
- 每个测试 < 1 秒
- 覆盖率目标: ≥ 80%

### 集成测试 (Integration Tests)

```
tests/integration/
├── test_screenpipe_client.py   # 需要 Screenpipe 运行
├── test_aw_client.py           # 需要 ActivityWatch 运行
├── test_ha_client.py           # 需要 Home Assistant 运行
├── test_qq_client.py           # 需要 NapCatQQ 运行
└── test_llm_real.py            # 真实 LLM API 调用
```

**规则**:
- 标记 `@pytest.mark.integration`
- CI 中可选执行（需要环境变量配置）
- 本地开发时按需手动运行

## 3. 测试编写规范

### 命名

```python
# 格式: test_<被测方法>_<场景>_<期望结果>

def test_load_identity_with_valid_file_returns_profile():
    ...

def test_load_identity_with_missing_file_returns_empty():
    ...

def test_agent_loop_with_tool_call_executes_tool():
    ...

def test_agent_loop_with_dangerous_tool_requires_confirmation():
    ...
```

### 结构 (AAA 模式)

```python
def test_identity_loads_profile_correctly():
    # Arrange — 准备测试数据
    profile_content = '{"key": "name", "value": "东东", "updated": "2026-04-05"}\n'
    tmp_file = tmp_path / "profile.jsonl"
    tmp_file.write_text(profile_content, encoding="utf-8")

    # Act — 执行被测代码
    identity = IdentityMemory(tmp_file)
    result = identity.get("name")

    # Assert — 验证结果
    assert result == "东东"
```

### Mock 外部依赖

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_agent_loop_calls_llm():
    # Arrange
    mock_llm = AsyncMock()
    mock_llm.chat.return_value = LLMResponse(
        text="你好东哥",
        thinking=None,
        tool_calls=None,
        usage=TokenUsage(input=100, output=50)
    )

    loop = AgentLoop(llm_client=mock_llm)

    # Act
    result = await loop.run("你好")

    # Assert
    mock_llm.chat.assert_called_once()
    assert result == "你好东哥"
```

### Fixture 复用

```python
# tests/conftest.py

@pytest.fixture
def sample_identity(tmp_path):
    """创建一个包含基本用户信息的临时身份文件"""
    content = "\n".join([
        '{"key": "name", "value": "测试用户", "updated": "2026-04-05"}',
        '{"key": "age", "value": 21, "updated": "2026-04-05"}',
    ])
    path = tmp_path / "identity" / "profile.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    return path

@pytest.fixture
def mock_llm_client():
    """返回一个 mock 的 LLM 客户端"""
    client = AsyncMock(spec=LLMClient)
    client.chat.return_value = LLMResponse(
        text="mock response",
        thinking=None,
        tool_calls=None,
        usage=TokenUsage(input=0, output=0)
    )
    return client
```

## 4. 开发节奏示例

以 "L0 身份记忆" 模块为例：

```
Step 1: RED — 写失败的测试
─────────────────────────────
# tests/unit/test_identity.py

def test_load_profile_returns_dict(tmp_path):
    profile = tmp_path / "profile.jsonl"
    profile.write_text('{"key":"name","value":"东东","updated":"2026-04-05"}\n')
    
    mem = IdentityMemory(profile)
    assert mem.get("name") == "东东"

运行: pytest → FAIL (IdentityMemory 还不存在)

Step 2: GREEN — 最小实现
─────────────────────────────
# src/physi_core/memory/identity.py

class IdentityMemory:
    def __init__(self, path):
        self._data = {}
        for line in path.read_text().strip().split("\n"):
            item = json.loads(line)
            self._data[item["key"]] = item["value"]
    
    def get(self, key):
        return self._data.get(key)

运行: pytest → PASS ✅

Step 3: REFACTOR — 优化
─────────────────────────────
- 添加类型标注
- 处理文件不存在的情况
- 添加 set() 方法用于更新
- 确保测试仍然通过

Step 4: 继续 RED — 下一个功能点
─────────────────────────────
def test_set_identity_persists_to_file(tmp_path):
    ...
def test_identity_handles_missing_file(tmp_path):
    ...
def test_identity_filters_invalid_lines(tmp_path):
    ...
```

## 5. 验收标准 (Acceptance Criteria)

### Phase 1 验收 — Agent Core + 记忆 MVP

| # | 验收条件 | 测试类型 | 通过标准 |
|:---:|:---|:---|:---|
| AC-1 | L0 身份记忆可读写 JSONL | Unit | `IdentityMemory` 正确加载、查询、更新、持久化 |
| AC-2 | L1 短期记忆可记录完整对话 | Unit | 写入/读取包含 thinking + tool_calls 的 JSONL |
| AC-3 | L4 指令记忆加载 PHYSI.md | Unit | 正确解析 Markdown 为 system prompt |
| AC-4 | MEMORY.md 索引读写 | Unit | 加载索引、更新摘要行、控制总行数 |
| AC-5 | LLM Adapter 调用 MiniMax | Unit+Integration | Mock 通过 + 真实 API 调用返回有效响应 |
| AC-6 | LLM Adapter 调用 Anthropic | Unit | Mock 通过，接口兼容 |
| AC-7 | LLM Adapter 调用 OpenAI | Unit | Mock 通过，接口兼容 |
| AC-8 | Agent Loop 基础循环 | Unit | 纯文本 → 直接返回；tool_call → 执行 → 反馈 → 继续 |
| AC-9 | Agent Loop 高危操作拦截 | Unit | 标记为 dangerous 的工具需要确认 |
| AC-10 | Prompt 构建器正确注入记忆 | Unit | System prompt 包含 L0+L4+MEMORY.md+portrait |
| AC-11 | 命令行交互可用 | E2E | 在终端输入消息 → 获得 LLM 回复 → 对话记入 L1 |
| AC-12 | 配置文件加载 | Unit | YAML 正确解析，缺失字段有默认值 |

### Phase 2 验收 — 感知 + QQ

| # | 验收条件 | 测试类型 | 通过标准 |
|:---:|:---|:---|:---|
| AC-13 | Screenpipe 客户端拉取 OCR | Unit+Integration | Mock 通过 + 真实 API 返回数据 |
| AC-14 | ActivityWatch 客户端查询 | Unit+Integration | Mock 通过 + 真实 API 返回统计 |
| AC-15 | 数据去重压缩 | Unit | 相似帧合并，输出 < 1000 tokens |
| AC-16 | L2 中期记忆 30min 摘要 | Unit | 原始数据 → LLM → segment MD |
| AC-17 | 定时器 30min 触发 | Unit | Timer 按时触发，生成正确的 segment 文件 |
| AC-18 | LLM 判断是否通知 | Unit | 久坐 >2h → notify=true；正常 → false |
| AC-19 | QQ WebSocket 连接 | Integration | 连接 NapCat → 收发消息 |
| AC-20 | QQ 私聊过滤 | Unit | 只处理绑定用户的私聊；群聊忽略 |
| AC-21 | 用户消息异步触发 + 10min 节流 | Unit | 首次触发成功；10min 内重复不触发 |
| AC-22 | 完整 QQ 对话链路 | E2E | QQ 消息 → Agent → 回复 → 记入 L1 |

### Phase 3 验收 — 长期记忆 + IoT

| # | 验收条件 | 测试类型 | 通过标准 |
|:---:|:---|:---|:---|
| AC-23 | L3 长期记忆读写 | Unit | 多个主题 MD 文件正确读写 |
| AC-24 | AutoConsolidate 会话后 | Unit | 对话结束 → LLM 提取新信息 → 更新 L3 |
| AC-25 | AutoConsolidate 每日 | Unit | 片段 → LLM 压缩 → 日摘要 + L3 更新 |
| AC-26 | AutoConsolidate 每周 | Unit | 日摘要 → LLM 审视 → 周摘要 + 画像更新 |
| AC-27 | Home Assistant 设备查询 | Integration | 列出设备、查状态 |
| AC-28 | Home Assistant 设备控制 | Integration | 开灯/关灯操作成功 |
| AC-29 | 跨域联动场景 | E2E | 久坐检测 → 自动提醒 + 可选灯光调整 |

## 6. 持续集成

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run ruff format --check
      - run: uv run ruff check
      - run: uv run mypy --strict src/
      - run: uv run pytest tests/unit/ --cov=src --cov-report=term --cov-fail-under=80
```
