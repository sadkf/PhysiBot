# PhysiBot 技术架构文档

> 版本: 0.1.0 | 最后更新: 2026-04-05

---

## 1. 系统总览

PhysiBot 是一个 Claude Code 风格的自主 Agent，核心由 **Agent Loop + 五层 MD 记忆 + LLM Adapter** 组成，通过整合开源项目（Screenpipe / ActivityWatch / Home Assistant / NapCatQQ）获取感知和执行能力。

```
                    ┌──────────────────────────┐
                    │      QQ 私聊 (NapCatQQ)   │
                    └────────────┬─────────────┘
                                 │ OneBot v11 WebSocket
                                 ▼
┌─────────────────────────────────────────────────────────┐
│                    PhysiBot Core                         │
│                                                         │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ EventBus │→│Agent Loop │↔│ LLM      │  │ Tool    │ │
│  │ (asyncio)│  │Think→Act │  │ Adapter  │  │Controller│ │
│  └────┬────┘  │→Check    │  │MiniMax/  │  │(权限网关)│ │
│       │       └────┬─────┘  │Anthropic/│  └────┬────┘ │
│       │            │        │OpenAI    │       │       │
│       │            ▼        └──────────┘       │       │
│       │     ┌──────────────┐                   │       │
│       │     │ Memory System│                   │       │
│       │     │ L0-L4 五层   │                   │       │
│       │     │ JSONL + MD   │                   │       │
│       │     └──────────────┘                   │       │
│       │                                        │       │
└───────┼────────────────────────────────────────┼───────┘
        │ 感知源                                  │ 执行端
   ┌────┴────┐                              ┌────┴────┐
   │Screenpipe│                              │HA (IoT) │
   │AW       │                              │QQ 发送  │
   │剪贴板   │                              │pyautogui│
   └─────────┘                              └─────────┘
```

## 2. 模块划分

```
src/physi_core/
├── __init__.py
├── main.py                 # 入口：启动所有子系统
│
├── agent/                  # Agent 核心
│   ├── __init__.py
│   ├── loop.py             # Agent Loop (Think→Act→Check→Repeat)
│   ├── tools.py            # Tool Controller + 工具注册表 + 权限网关
│   └── prompts.py          # System Prompt 构建器（注入记忆）
│
├── memory/                 # 五层记忆系统
│   ├── __init__.py
│   ├── identity.py         # L0: 身份记忆 (JSONL 读写)
│   ├── short_term.py       # L1: 短期会话记忆
│   ├── mid_term.py         # L2: 中期活动摘要 (30min 片段 + 日/周)
│   ├── long_term.py        # L3: 长期用户画像
│   ├── index.py            # MEMORY.md 索引管理
│   └── consolidator.py     # AutoConsolidate: LLM 驱动的记忆整理
│
├── llm/                    # LLM 适配层
│   ├── __init__.py
│   ├── adapter.py          # 统一 LLM 调用接口
│   ├── providers.py        # 提供商配置 (MiniMax/Anthropic/OpenAI)
│   └── response.py         # 响应标准化 (tool_calls / text / thinking)
│
├── integrations/           # 外部系统对接
│   ├── __init__.py
│   ├── screenpipe.py       # Screenpipe REST API 客户端
│   ├── activitywatch.py    # ActivityWatch API 客户端
│   ├── homeassistant.py    # Home Assistant REST/WS 客户端
│   └── qq.py               # NapCatQQ OneBot v11 WebSocket
│
├── events/                 # 事件系统
│   ├── __init__.py
│   └── bus.py              # asyncio EventBus (进程内)
│
└── config/                 # 配置管理
    ├── __init__.py
    └── settings.py          # YAML 配置加载 + 校验
```

## 3. 核心流程

### 3.1 用户消息处理流程

```
QQ 私聊消息到达
    │
    ├── 1. qq.py: 过滤 → 只接受绑定用户的私聊
    ├── 2. EventBus: 发布 UserMessage 事件
    ├── 3. prompts.py: 构建上下文
    │      ├── 加载 PHYSI.md (L4)
    │      ├── 加载 identity/profile.jsonl (L0)
    │      ├── 加载 MEMORY.md (索引)
    │      ├── 加载 portrait.md (L3)
    │      ├── 加载今日摘要 + 最近片段 (L2)
    │      └── 加载当前会话 (L1)
    ├── 4. loop.py: Agent Loop 开始
    │      ├── 调用 LLM → 获取响应
    │      ├── 有 tool_calls? → tools.py 执行 → 结果反馈 → 继续循环
    │      └── 纯文本? → 返回响应
    ├── 5. qq.py: 发送回复
    ├── 6. short_term.py: 写入当前会话记录
    └── 7. (异步) mid_term.py: 10min 节流后刷新活动数据
```

### 3.2 定时器摘要流程

```
每 30 分钟触发
    │
    ├── 1. screenpipe.py: GET /search?content_type=ocr → 去重压缩
    ├── 2. activitywatch.py: 查询窗口活动统计
    ├── 3. 剪贴板历史收集
    ├── 4. LLM: 生成摘要 + 判断是否通知用户
    ├── 5. mid_term.py: 写入 segments/{timestamp}.md
    └── 6. 如需通知 → qq.py 发送私聊消息
```

### 3.3 记忆整理流程 (AutoConsolidate)

```
触发条件满足 (日合并/周审视/会话结束/手动)
    │
    ├── 1. consolidator.py: 读取待整理的记忆数据
    ├── 2. LLM: 判断价值、压缩、合并、发现矛盾
    ├── 3. long_term.py: 更新 L3 主题文件
    ├── 4. index.py: 更新 MEMORY.md 索引摘要
    └── 5. 回收 LLM 标记为"可回收"的片段
```

## 4. LLM Adapter 设计

```python
# 统一接口
class LLMClient:
    async def chat(messages, tools=None) -> LLMResponse

# LLMResponse 标准化
@dataclass
class LLMResponse:
    text: str | None           # 纯文本响应
    thinking: str | None       # 思维链（MiniMax M2.7 支持）
    tool_calls: list | None    # 工具调用请求
    usage: TokenUsage          # token 用量统计

# 提供商透明切换
config.yaml:
  provider: "minimax"  →  base_url: api.minimaxi.com/anthropic
  provider: "anthropic" → base_url: api.anthropic.com
  provider: "openai"    → base_url: api.openai.com/v1
```

## 5. 数据流向

```
感知数据（Screenpipe/AW/剪贴板）
    │ 本地 API，不经过网络
    ▼
去重 + 敏感过滤
    │ ~500-1000 tokens/30min
    ▼
LLM API（MiniMax 云端）
    │ 只发送文本摘要，不发截图
    ▼
记忆文件（本地 MD/JSONL）
    │ 用户可直接查看/编辑
    ▼
Agent Loop 注入上下文
    │ ~3900 tokens/轮
    ▼
QQ 消息回复
```

## 6. 关键设计决策

| 决策 | 为什么 |
|:---|:---|
| 不用 LangGraph | 过重；自研 Agent Loop ~400 行，完全可控 |
| 不用向量数据库 | MD/JSONL 人可读、git 可追踪、零运维 |
| 不发截图给 LLM | 太贵 + 隐私风险；OCR 文本已够用 |
| MiniMax 默认 | 国内延迟低、成本友好、兼容 Anthropic SDK |
| 30 分钟片段 | 粒度适中：比 1 小时更及时，比 10 分钟更经济 |
| LLM 驱动记忆管理 | 不做死板的"保留 X 天"，由 LLM 智能决定遗忘 |
| 仅 QQ 私聊 | MVP 聚焦；群聊消息量太大且无关 |
