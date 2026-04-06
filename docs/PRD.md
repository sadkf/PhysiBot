# PhysiBot — 产品需求文档 (PRD)

> **一句话定位**：一个活在你身边的 AI 助手，它记得你、懂你、能替你操控物理世界——不止于消息。

---

## 1 · 产品愿景 (Vision)

### 我们要解决什么问题？

当前所有 AI 助手都有一个致命缺陷：**它们不知道你是谁。**

每次对话都是从零开始，它不知道你叫什么、在做什么、喜欢什么。它不知道你刚熬夜到 3 点，不知道你的书房灯还亮着，不知道你已经在电脑前坐了 4 个小时。

**PhysiBot 的目标是：成为第一个"认识你"的 AI 助手。**

它会：
- 记得你的名字、习惯、偏好
- 知道你此刻在做什么（屏幕感知）
- 感知你的物理环境（IoT 设备）
- 在 QQ 上像朋友一样跟你聊天
- 在你需要时主动出现，不需要时安静旁观

### 核心定位

```
                 传统 AI 助手              PhysiBot
               ┌─────────────┐         ┌──────────────┐
  记忆         │  ❌ 无记忆   │         │ ✅ 五层记忆   │
  感知         │  ❌ 看不见   │         │ ✅ 屏幕+IoT  │
  行动         │  ❌ 只能聊天 │         │ ✅ 控制设备   │
  主动性       │  ❌ 被动问答 │         │ ✅ 主动关怀   │
  交互方式     │  网页/App    │         │ QQ 好友       │
               └─────────────┘         └──────────────┘
```

---

## 2 · 目标用户 (Target Users)

### 核心用户画像

**小王，22 岁，程序员/大学生**
- 每天在电脑前 10+ 小时
- 经常忘记休息、忘记喝水
- 希望有人提醒他该休息了
- 家里有几个智能设备但懒得设自动化
- 用 QQ 跟朋友聊天，不想再装新 App
- 在意隐私，不想数据上云
- 折腾能力强，愿意运行一个 exe

### 次要用户

- **远程办公者**：需要记录工作内容、自动整理日报
- **数码爱好者**：喜欢折腾智能家居 + AI 的极客
- **效率追求者**：希望 AI 理解自己的工作流并辅助优化

---

## 3 · 产品目标 (Goals)

### 最终交付形态

> **一个开箱即用的 .exe 文件。**

用户双击运行，弹出配置界面，填入 API Key、QQ 号等基本信息，点击"启动"。

所有依赖（Python runtime、Screenpipe、ActivityWatch 等）通过启动脚本自动解压/安装到程序目录下。无需用户手动安装任何环境。

```
PhysiBot/
├── PhysiBot.exe                 # 主程序入口
├── start.bat                    # 启动脚本（处理依赖检查/安装）
├── runtime/                     # 内嵌 Python 运行时
├── vendor/                      # 捆绑依赖
│   ├── screenpipe/              # Screenpipe 本体
│   ├── activitywatch/           # ActivityWatch 本体
│   └── napcat/                  # NapCatQQ 本体
├── physi-core/                  # 核心代码
├── physi-data/                  # 用户数据（记忆、配置）
│   ├── config.yaml              # 配置文件
│   ├── identity/                # 元信息记忆
│   ├── MEMORY.md                # 记忆索引
│   ├── memory/                  # 主题记忆
│   ├── short_term/              # 短期对话记录
│   ├── mid_term/                # 中期活动摘要
│   └── transcripts/             # 会话归档
└── logs/                        # 运行日志
```

### 不需要担心合规

这是一个面向极客用户的自部署工具，只有主动搜索并下载的人才会使用。不在任何应用商店上架，不做商业推广。类似于 fiddler、wireshark 等开发者工具的分发模式。

---

## 4 · 记忆系统设计 (Memory Architecture) ⭐ 核心

> **设计灵感**：参考 Claude Code 泄露源码的多层记忆架构 + 认知科学中的人类记忆模型（感觉记忆 → 工作记忆 → 长期记忆），设计出一套适合"贴心助手"场景的五层记忆系统。

### 4.1 记忆层级总览

```
┌─────────────────────────────────────────────────────┐
│                  PhysiBot 五层记忆系统                │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │  L0 · 身份记忆 (Identity Memory)            │    │
│  │  "我叫张三，21 岁"                          │    │
│  │  格式: JSONL  |  注入: 每轮  |  更新: 用户  │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │  L1 · 短期记忆 (Short-Term / Working)       │    │
│  │  "刚才那段对话他说了什么"                    │    │
│  │  格式: JSONL  |  窗口: 最近 5 轮  |  全量   │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │  L2 · 中期记忆 (Mid-Term / Episodic)        │    │
│  │  "这周用户在做一个 Python 项目"              │    │
│  │  格式: MD     |  窗口: 7 天  |  每小时摘要  │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │  L3 · 长期记忆 (Long-Term / User Portrait)  │    │
│  │  "用户是个夜猫子，喜欢听 Lo-fi"              │    │
│  │  格式: MD     |  永久  |  周期性提炼         │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │  L4 · 指令记忆 (Instruction / PHYSI.md)     │    │
│  │  "Agent 的行为准则和工具说明"                │    │
│  │  格式: MD     |  注入: 每轮  |  开发者维护   │    │
│  └─────────────────────────────────────────────┘    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 4.2 各层详细设计

---

#### L0 · 身份记忆 (Identity Memory)

**目的**：让 Agent 知道"你是谁"——用户的基本信息和硬性偏好。

**存储格式**：JSONL（每行一条事实，纯粹的 key-value，机器友好）

**文件位置**：`physi-data/identity/profile.jsonl`

```jsonl
{"key": "name", "value": "张三", "updated": "2026-04-05"}
{"key": "nickname", "value": "东东", "updated": "2026-04-05"}
{"key": "age", "value": 21, "updated": "2026-04-05"}
{"key": "gender", "value": "male", "updated": "2026-04-05"}
{"key": "occupation", "value": "大三学生/独立开发者", "updated": "2026-04-05"}
{"key": "language", "value": "中文", "updated": "2026-04-05"}
{"key": "timezone", "value": "Asia/Shanghai", "updated": "2026-04-05"}
{"key": "wakeup_time", "value": "10:00", "updated": "2026-04-05"}
{"key": "sleep_time", "value": "02:00", "updated": "2026-04-05"}
{"key": "qq_number", "value": "123456789", "updated": "2026-04-05"}
{"key": "call_me", "value": "叫我东哥就行", "updated": "2026-04-05"}
{"key": "pet_peeve", "value": "讨厌表情包轰炸和过度热情", "updated": "2026-04-05"}
```

**注入策略**：
- **每轮对话**注入到 System Prompt 中
- 文件通常只有 10-30 行，token 消耗可忽略（<200 tokens）
- 用户可通过对话更新（"帮我记住我不喜欢蓝光"）
- 也可直接编辑 JSONL 文件

**扩展文件**（可选）：

```
physi-data/identity/
├── profile.jsonl          # 基础信息
├── devices.jsonl          # 已绑定设备清单
├── contacts.jsonl         # 重要联系人（Agent 需要知道的）
└── boundaries.jsonl       # 红线规则（绝对不能做的事）
```

`devices.jsonl` 示例：
```jsonl
{"device": "书房吸顶灯", "entity_id": "light.study_ceiling", "location": "书房", "type": "light"}
{"device": "客厅温湿度计", "entity_id": "sensor.living_room_temp", "location": "客厅", "type": "sensor"}
{"device": "智能插座", "entity_id": "switch.study_plug", "location": "书房", "type": "switch"}
```

`boundaries.jsonl` 示例：
```jsonl
{"rule": "never_do", "description": "绝不主动查看或记忆包含密码、银行卡号的屏幕内容"}
{"rule": "never_do", "description": "绝不在凌晨 2-9 点主动发消息打扰用户"}
{"rule": "ask_first", "description": "控制家电设备前必须先征得用户同意"}
{"rule": "ask_first", "description": "分享用户的屏幕活动给第三方前必须确认"}
```

---

#### L1 · 短期记忆 (Short-Term Memory)

**目的**：保留最近几轮对话的完整上下文，包括 thinking 块、tool calls、结果——让 Agent 拥有"刚才发生了什么"的清晰记忆。

**存储格式**：JSONL（每行一个完整的 message 对象）

**文件位置**：`physi-data/short_term/`

```
physi-data/short_term/
├── current_session.jsonl      # 当前进行中的会话
├── session_2026-04-05_14-30.jsonl  # 历史会话（保留最近 5 个）
├── session_2026-04-05_10-15.jsonl
└── ...
```

**单条记录格式**：

```jsonl
{"ts": "2026-04-05T14:30:22Z", "role": "user", "content": "我上午都干了啥", "source": "qq", "qq_group": null}
{"ts": "2026-04-05T14:30:23Z", "role": "assistant", "thinking": "用户想回忆上午的活动。我需要查询 Screenpipe 和 ActivityWatch 的数据...", "content": null, "tool_calls": [{"name": "screenpipe_search", "args": {"query": "上午活动", "time_range": "today_morning"}}]}
{"ts": "2026-04-05T14:30:25Z", "role": "tool", "name": "screenpipe_search", "result": "9:00-10:30: VSCode 编写 Python 代码, 10:30-11:00: Chrome 浏览 GitHub, 11:00-12:00: VSCode 继续编码"}
{"ts": "2026-04-05T14:30:27Z", "role": "assistant", "thinking": "数据已获取，整理成人话告诉用户", "content": "东哥，你上午挺充实的：\n- 9 点到 10 点半在 VSCode 里写 Python\n- 中间逛了半小时 GitHub\n- 然后又码了一小时的代码\n总共编程约 2.5 小时 💪"}
```

**注入策略**：
- **当前会话** (`current_session.jsonl`) 全量注入到消息列表中
- **前一个会话**：注入最后 3 条消息作为"上次聊到哪里了"的提示
- 更早的会话：不注入，除非用户主动问起（Agent 通过工具按需读取）
- 会话超过 50 轮时，自动触发**摘要压缩**：保留头 5 轮 + 尾 10 轮 + 中间压缩为摘要

**会话生命周期**：

```
新消息到达 → 写入 current_session.jsonl
    │
    ├── 会话继续 → 追加记录
    │
    └── 会话结束（静默 30 分钟 / 用户说"拜拜"）
            │
            ├── current → 重命名为 session_{timestamp}.jsonl
            ├── 触发中期记忆提取（见 L2）
            ├── 清理超过 5 个的旧会话文件
            └── 新建空的 current_session.jsonl
```

---

#### L2 · 中期记忆 (Mid-Term / Episodic Memory) ⭐ 核心创新

**目的**：记住"这一周用户在做什么"——通过 **每 30 分钟** 定时监控 + AI 摘要，构建用户近期生活的连续叙事。

**这是 PhysiBot 区别于所有其他 AI 助手的核心能力。**

**存储格式**：Markdown（结构化但人可读）

**文件位置**：`physi-data/mid_term/`

```
physi-data/mid_term/
├── segments/                       # 每 30 分钟活动摘要片段
│   ├── 2026-04-05_0900.md         # 4月5日 09:00-09:30
│   ├── 2026-04-05_0930.md         # 4月5日 09:30-10:00
│   ├── 2026-04-05_1000.md
│   └── ...
├── daily/                          # 每日汇总
│   ├── 2026-04-05.md
│   ├── 2026-04-04.md
│   └── ...
└── weekly/                         # 每周汇总
    ├── 2026-W14.md
    └── ...
```

##### 30 分钟片段摘要示例 (`segments/2026-04-05_1430.md`)：

```markdown
# 2026-04-05 14:30-15:00 活动片段

## 主要活动
- 在 VSCode 中编辑 `memory/manager.py`，添加 JSONL 解析逻辑
- 切换到 Chrome 查阅 MiniMax Function Calling 文档 (2 次)

## 应用使用
- VSCode: 22 分钟
- Chrome: 6 分钟
- QQ: 2 分钟（回复了小李一条消息）

## 状态评估
- 用户处于编码高专注状态，窗口切换少
- 已连续编程 2 小时，建议关注

## 是否需要通知用户: 否
（用户在高专注状态，非紧急情况不打扰）
```

##### 日摘要示例 (`daily/2026-04-05.md`)：

```markdown
# 2026-04-05 (周六) 日报

## 一句话总结
东哥今天全天在推进 PhysiBot 项目，干了大约 8 小时代码，中间和朋友聊了聊周末安排。

## 工作
- 主要项目: PhysiBot（physi-core 目录下的 agent 和 memory 模块）
- 参考了 Anthropic API / MiniMax 文档
- 生产力较高，代码编辑密集

## 生活
- 10:00 起床，比平时早
- 12:30-13:30 午休
- 和朋友 "小李" 聊了周末聚会
- 22:30 后切换到 B 站看视频

## 健康
- 连续编程超 3 小时 x2 次（已通过 QQ 提醒休息）
- 全天久坐约 8 小时
```

##### 级联压缩机制

```
30 分钟片段 (segments/*.md)
    │  保留 3 天，第 4 天自动删除
    │
    ▼  每天 23:59 触发
日摘要 (daily/*.md)
    │  将今天所有 30 分钟片段 → LLM 压缩为一日总结
    │  保留 30 天
    │
    ▼  每周日 23:59 触发
周摘要 (weekly/*.md)
    │  将本周 7 个日摘要 → LLM 压缩为一周总结
    │  保留 12 周（3 个月）
    │
    ▼  过期的周摘要
提炼为长期记忆 → L3 用户画像更新
```

**注入策略**：
- 每次对话注入：**今日摘要**（如果有）+ **最近 2 个 30 分钟片段**的要点
- Agent 可通过 `memory_read_midterm` 工具按需查看更早的摘要
- 更早的片段不直接注入，只在用户问到某个具体时段时按需加载

---

#### L3 · 长期记忆 (Long-Term / User Portrait)

**目的**：AI 对用户的全局画像——它"认识"你的程度。这是让 PhysiBot 感觉"是朋友"的关键。

**存储格式**：Markdown（多个主题文件）

**文件位置**：`physi-data/memory/`

```
physi-data/memory/
├── portrait.md             # 用户画像总览
├── preferences.md          # 偏好（口味、风格、讨厌的东西）
├── routines.md             # 日常作息与习惯
├── skills_interests.md     # 技能与兴趣爱好
├── social.md               # 社交关系图谱
├── health.md               # 健康习惯（久坐、作息）
├── work_projects.md        # 正在进行的项目
├── emotional_patterns.md   # 情绪模式（什么时候容易烦躁）
└── iot_preferences.md      # 设备使用偏好
```

**用户画像示例** (`memory/portrait.md`)：

```markdown
# 用户画像 — 张三

> 最后更新: 2026-04-05

## 核心标签
程序员 | 大三学生 | 夜猫子 | 独立开发者 | 务实主义者

## 性格特征
- 直来直去，不喜欢绕弯子
- 务实，注重能用 > 完美
- 有幽默感，但不喜欢过度热情
- 折腾精神强，愿意尝试新事物
- 有时会因忘记休息而影响健康

## 交流偏好
- 叫他"东哥"
- 简洁回复，不要长篇大论
- 可以偶尔开玩笑，但不要用表情包轰炸
- 技术话题可以直来直去说术语
- 生活话题用轻松口吻

## 当前关注
- 正在开发 PhysiBot 项目（AI + IoT 助手）
- 对 Agent 架构和记忆系统很感兴趣
- 在考虑毕设方向

## AI 使用习惯
- 喜欢把 AI 当团队伙伴用
- 倾向于给出需求让 AI 完成，而不是手把手指导
- 讨厌 AI 说"作为一个 AI 语言模型..."
```

**更新机制**：

```
触发条件（任一）:
├── 每个对话会话结束后
├── 每日摘要（L2）生成后
├── 用户显式告知新信息时
└── 每周日 AutoConsolidate 定时执行

更新流程:
1. 读取当前 portrait.md 等文件内容
2. 读取最新的对话记录 / 日摘要
3. LLM Prompt: "基于以下新信息，更新用户画像。
                只修改有变化的部分，删除已过时的信息。
                保持简洁，每个文件不超过 50 行。"
4. 写回文件
5. 更新 MEMORY.md 索引的摘要行
```

**注入策略**：
- 每轮对话注入 `MEMORY.md` 索引（轻量指针，~300 tokens）
- `portrait.md` 全文注入（~500 tokens）
- 其他主题文件由 Agent 通过 `memory_read` 工具**按需加载**

---

#### L4 · 指令记忆 (Instruction Memory / PHYSI.md)

**目的**：Agent 的"宪法"——定义它是谁、能做什么、不能做什么。

**存储格式**：Markdown

**文件位置**：`physi-data/PHYSI.md`

**始终注入**，每轮对话作为 System Prompt 的核心部分。

```markdown
# PhysiBot 系统指令

## 你是谁
你是 PhysiBot，用户的私人 AI 助手。你通过 QQ 与用户交流，
你了解用户的电脑操作（通过 Screenpipe）和物理环境（通过 Home Assistant）。
你像一个贴心的朋友，而不是冷冰冰的客服。

## 行为准则
1. 说话简洁自然，像朋友之间的聊天
2. 称呼用户时使用他设定的昵称
3. 主动关心但不过度打扰——通过学习找到平衡点
4. 对用户的记忆是"提示"而非"真理"，行动前验证实际状态
5. 高危操作必须先征得同意（IoT 控制、电脑操作、信息分享）

## 你能做什么
- 查询用户的屏幕活动历史（screenpipe_search）
- 查询应用使用统计（aw_query）
- 控制智能家居设备（ha_control, ha_query）
- 读写记忆系统（memory_read, memory_write）
- 发送 QQ 消息和通知（qq_send）

## 你绝不做什么
- 绝不记忆密码、银行卡号等敏感信息
- 绝不在深夜（用户设定的睡眠时段）主动发消息
- 绝不在未经确认时控制设备
- 绝不说"作为一个 AI 语言模型"这种话
- 绝不对外泄露用户的任何数据
```

---

#### MEMORY.md — 记忆索引（始终加载）

**文件位置**：`physi-data/MEMORY.md`

这是 Claude Code 架构中的关键设计：一个轻量级索引文件，告诉 Agent "你记得什么，但不需要全部装进脑子"。

```markdown
# PhysiBot 记忆索引

> 以下是你对用户的了解的摘要。详细信息在各主题文件中，按需读取。

## 用户身份
→ identity/profile.jsonl
张三，21岁，大三学生/独立开发者，昵称"小张"。夜猫子，通常 2 点睡 10 点起。

## 用户画像
→ memory/portrait.md
务实的程序员，说话直来直去。正在开发 PhysiBot 项目。不喜欢过度热情的回复。

## 偏好
→ memory/preferences.md
简洁回复，偶尔幽默，不要表情包轰炸。技术话题用术语。

## 作息
→ memory/routines.md
通常 10 点开始工作，12:30 午休，晚上 10 点后切换娱乐模式。经常忘记休息。

## 设备
→ identity/devices.jsonl
书房: 吸顶灯 + 智能插座; 客厅: 温湿度计

## 本周动态
→ mid_term/weekly/2026-W14.md
本周主要在开发 PhysiBot 项目，推进了记忆系统和 Agent Loop 的设计。

## 今日
→ mid_term/daily/2026-04-05.md
今天全天在写代码，8 小时+，已提醒休息 2 次。晚上和朋友聊了周末安排。
```

**索引预算**：严格控制在 **~30 行 / ~500 tokens** 以内。超出时自动压缩较旧的条目。

---

### 4.3 记忆系统的上下文注入汇总

每轮对话时，System Prompt 的组成：

```
┌─ System Prompt 构成（每轮注入）──────────────────────────┐
│                                                         │
│  1. PHYSI.md (指令)                    ~400 tokens       │
│  2. identity/profile.jsonl (身份)       ~200 tokens       │
│  3. MEMORY.md (记忆索引)               ~500 tokens       │
│  4. memory/portrait.md (用户画像)       ~500 tokens       │
│  5. 今日摘要 (mid_term/daily)          ~300 tokens       │
│  6. 当前会话上下文 (short_term)         ~2000 tokens      │
│                                                         │
│  合计: ~3900 tokens / 轮                                 │
│  远低于 MiniMax M2.7 的 1M token 上下文窗口              │
└─────────────────────────────────────────────────────────┘
```

### 4.4 数据提取管线——精确到字节的成本核算 ⭐

> 核心原则：**绝不发截图给 LLM。** 用两个现成 API + 一个轻量轮询完成全部采集。

#### Step 1: 从 Screenpipe 提取 OCR 文本（本地 REST API，零成本）

```python
# 请求：拉取过去 30 分钟的 OCR 文本
import httpx, datetime

end = datetime.datetime.now(datetime.timezone.utc)
start = end - datetime.timedelta(minutes=30)

resp = httpx.get("http://localhost:3030/search", params={
    "content_type": "ocr",        # 只要 OCR 文本，不要音频
    "start_time": start.isoformat(),
    "end_time":   end.isoformat(),
    "limit": 50,                   # 最多 50 条（事件驱动，通常 10-30 条/30min）
})
data = resp.json()
```

**Screenpipe 返回数据结构**：
```json
{
  "data": [
    {
      "type": "OCR",
      "content": {
        "text": "def agent_loop(initial_input, context):",
        "app_name": "Code.exe",
        "window_name": "loop.py - PhysiBot - Visual Studio Code"
      },
      "timestamp": "2026-04-05T14:32:15Z"
    }
  ],
  "pagination": {"limit": 50, "offset": 0, "total": 23}
}
```

**数据量实测**：
- Screenpipe 使用**事件驱动**采集（鼠标点击/窗口切换/打字时才抓），不是持续截屏
- 每个 OCR 帧：~1-5 KB 文本
- **30 分钟典型活跃操作**：约 15-30 个帧 → 原始 OCR 文本约 **20-80 KB**
- 但大量帧的 OCR 文本是**重复的**（同一个窗口内容只变化部分文字）

**去重压缩**（发给 LLM 前）：
```python
def deduplicate_ocr(frames):
    """去重：相邻帧如果 OCR 文本相似度 > 80%，只保留最后一帧"""
    unique = []
    for frame in frames:
        if not unique or similarity(frame.text, unique[-1].text) < 0.8:
            unique.append(frame)
    return unique

# 去重后：30 分钟通常剩 5-15 个不同帧
# 提取关键信息：只保留 app_name + window_name + OCR 前 200 字符
def extract_summary(frames):
    lines = []
    for f in frames:
        lines.append(f"[{f.timestamp}] {f.app_name} | {f.window_name}")
        lines.append(f"  内容摘要: {f.text[:200]}")
    return "\n".join(lines)

# 最终发给 LLM 的文本量：~500-1500 字符 → ~200-500 tokens
```

#### Step 2: 从 ActivityWatch 提取应用使用统计（本地 REST API，零成本）

```python
from aw_client import ActivityWatchClient
from datetime import datetime, timedelta

client = ActivityWatchClient("physi-collector")
end = datetime.now()
start = end - timedelta(minutes=30)

# 查询窗口活动（已自动过滤 AFK 时段）
events = client.query(
    f'events = query_bucket("aw-watcher-window_{client.hostname}");'
    f'events = filter_period_intersect(events, '
    f'  query_bucket("aw-watcher-afk_{client.hostname}"));'
    f'RETURN = sort_by_duration(merge_events_by_keys(events, ["app"]));'
)
```

**AW 返回数据结构**：
```json
[
  {"data": {"app": "Code.exe", "title": "loop.py"}, "duration": 1234.5},
  {"data": {"app": "chrome.exe", "title": "MiniMax API"}, "duration": 456.7},
  {"data": {"app": "QQ.exe", "title": "小李"}, "duration": 120.3}
]
```

**数据量**：30 分钟通常 3-8 个应用条目 → 格式化后 ~50-100 tokens

#### Step 3: 剪贴板历史（自研轻量轮询，零成本）

```python
import pyperclip, time

clipboard_history = []
last_content = ""

def poll_clipboard():
    """每 5 秒检查一次剪贴板，有变化就记录"""
    current = pyperclip.paste()
    if current != last_content and len(current) < 5000:  # 过滤超大复制
        if not contains_sensitive(current):  # 过滤敏感内容
            clipboard_history.append({
                "ts": time.time(),
                "preview": current[:200]  # 只保留前 200 字
            })
```

**数据量**：30 分钟内通常 0-10 次复制 → ~50-200 tokens

#### 汇总：发给 LLM 的数据包

```
┌── 30 分钟摘要请求（发给 MiniMax API）────────────────┐
│                                                     │
│  [System Prompt]  (~200 tokens)                     │
│  "基于以下 30 分钟的活动数据，完成两个任务：         │
│   1. 用 3-5 句话描述用户在做什么                     │
│   2. 判断是否需要给用户发 QQ 消息（回答 是/否+原因） │
│   判断标准：久坐>2h要提醒，深夜>1am要提醒，          │
│   发现异常状态要通知，其余不打扰。"                  │
│                                                     │
│  [Screenpipe OCR 摘要]  (~200-500 tokens)            │
│  [ActivityWatch 统计]   (~50-100 tokens)             │
│  [剪贴板记录]           (~50-200 tokens)             │
│  [当前连续使用时长]     (~20 tokens)                 │
│                                                     │
│  总 Input: ~520-1020 tokens                         │
│  总 Output: ~150-300 tokens                         │
│                                                     │
└─────────────────────────────────────────────────────┘
```

#### 精确成本计算

```
MiniMax-M2.7 定价:
  Input:  $0.30 / 1M tokens  ≈ ¥2.16 / 1M tokens
  Output: $1.20 / 1M tokens  ≈ ¥8.64 / 1M tokens

每次 30 分钟摘要:
  Input 成本:  800 tokens × ¥2.16/1M  = ¥0.0017
  Output 成本: 200 tokens × ¥8.64/1M  = ¥0.0017
  单次合计: ≈ ¥0.0034 （不到 3 分 4 厘）

每日成本 (假设活跃 14 小时 = 28 次摘要):
  28 × ¥0.0034 = ¥0.095 ≈ ¥0.10/天

每月成本: ¥3.0

加上日摘要(1次/天) + 周摘要(1次/周):
  日摘要: ~2000 input + ~500 output = ¥0.0086/次
  周摘要: ~3000 input + ~800 output = ¥0.0134/次
  月增: ¥0.26 + ¥0.05 = ¥0.31

中期记忆总月成本: ≈ ¥3.3/月 🎉
```

**敏感内容过滤**：
- OCR 文本和剪贴板内容在发给 LLM 前，过滤 `boundaries.jsonl` 中定义的敏感关键词
- 检测到银行/密码类应用窗口时，跳过该帧的 OCR 文本
- 用户可在配置中设置"不监控"的应用列表（`ignore_apps: ["KeePass", "1Password"]`）

---

### 4.5 触发架构 (Trigger Architecture) ⭐

> 两条触发路径：**定时器路径**（每 30 分钟）和 **用户消息路径**（异步触发，10 分钟节流）

#### 总览

```
┌────────────────────────────────────────────────────────────────┐
│                     PhysiBot 触发架构                          │
│                                                                │
│  路径 A: 定时器触发 (Timer Trigger)                            │
│  ─────────────────────────────────────                         │
│  每 30 分钟 → 采集数据 → LLM 摘要 → 写入 segment MD           │
│                                    → LLM 判断是否通知用户      │
│                                    → 是 → 发 QQ 私聊消息       │
│                                    → 否 → 静默                 │
│                                                                │
│  路径 B: 用户消息触发 (User Message Trigger)                   │
│  ────────────────────────────────────────                      │
│  QQ 私聊消息到达 → 立即响应（Agent Loop）                      │
│                  → 异步触发一次数据摘要（后台，不阻塞回复）     │
│                  → 10 分钟内不重复触发                          │
│                                                                │
│  ⚠️ 只处理 QQ 私聊消息，群聊/其他消息全部忽略                  │
└────────────────────────────────────────────────────────────────┘
```

#### 路径 A: 定时器触发（每 30 分钟）

```python
import asyncio
from datetime import datetime

async def timer_trigger_loop():
    """每 30 分钟触发一次活动摘要"""
    while True:
        # 等待到下一个整半点（:00 或 :30）+ 2 分钟缓冲
        now = datetime.now()
        next_half = now.replace(second=0, microsecond=0)
        if now.minute < 30:
            next_half = next_half.replace(minute=30)
        else:
            next_half = next_half.replace(minute=0) + timedelta(hours=1)
        wait_seconds = (next_half - now).total_seconds() + 120  # +2min 缓冲
        await asyncio.sleep(wait_seconds)

        # 1. 采集过去 30 分钟数据
        raw_data = await collect_30min_data()

        # 2. 发给 LLM 生成摘要 + 判断是否通知
        result = await llm_summarize_and_judge(raw_data)

        # 3. 写入 segment MD
        write_segment_md(result.summary)

        # 4. 如果 LLM 建议通知用户
        if result.should_notify:
            await qq_send_private(result.notification_message)
```

**LLM 摘要 Prompt（定时器路径专用）**：

```
你是用户的私人助手 PhysiBot。以下是用户过去 30 分钟的电脑活动数据。
请完成两项任务：

## 任务 1: 活动摘要
用 3-5 句话描述用户这 30 分钟在做什么。只保留有意义的信息。

## 任务 2: 是否需要发消息
根据以下规则判断，回答 JSON 格式 {"notify": true/false, "reason": "...", "message": "..."}:
- 用户连续使用电脑超过 2 小时 → 提醒休息
- 当前时间超过凌晨 1 点且用户仍在活跃 → 提醒睡觉
- 检测到异常行为（如反复崩溃、反复搜索错误） → 主动询问
- 其他情况 → 不打扰 (notify: false)

[活动数据]
{data}

[当前时间] {current_time}
[用户已连续使用] {continuous_hours} 小时
```

#### 路径 B: 用户消息触发（异步，10 分钟节流）

```python
from datetime import datetime, timedelta

last_async_trigger_time = None

async def on_qq_private_message(message):
    """收到 QQ 私聊消息时的处理"""
    global last_async_trigger_time

    # ===== 前台：立即响应用户 =====
    # 1. 构建上下文（注入记忆）
    context = build_context()  # L0+L1+L4+MEMORY.md+portrait+今日摘要
    # 2. 进入 Agent Loop → 尽快回复
    response = await agent_loop(message.text, context)
    # 3. 发送回复
    await qq_send_private(response)

    # ===== 后台：异步触发数据摘要 =====
    now = datetime.now()
    should_trigger = (
        last_async_trigger_time is None or
        (now - last_async_trigger_time) > timedelta(minutes=10)
    )

    if should_trigger:
        last_async_trigger_time = now
        # 异步任务，不阻塞主流程
        asyncio.create_task(async_context_refresh())

async def async_context_refresh():
    """后台刷新：采集最近数据，更新当前 segment 和今日摘要"""
    raw_data = await collect_recent_data(minutes=15)  # 最近 15 分钟
    result = await llm_quick_summarize(raw_data)       # 用更短的 prompt
    append_to_current_segment(result.summary)
    # 注意：这里不判断是否通知，因为用户正在主动对话中
```

#### QQ 消息过滤规则

```python
async def on_onebot_event(event):
    """OneBot v11 事件处理入口"""

    # ❌ 忽略所有非消息事件
    if event["post_type"] != "message":
        return

    # ❌ 忽略群聊消息（只做私聊）
    if event["message_type"] != "private":
        return

    # ❌ 忽略非绑定用户的消息
    if str(event["user_id"]) != config.owner_qq:
        return

    # ✅ 只处理来自绑定用户的 QQ 私聊消息
    await on_qq_private_message(event)
```

#### 触发频率与成本一览

| 触发源 | 频率 | 单次 LLM 成本 | 日上限 | 日成本 |
|:---|:---|:---|:---|:---|
| 定时器 (30min) | 28 次/天 (14h 活跃) | ¥0.0034 | 28 次 | ¥0.095 |
| 用户消息 (异步) | 最多 84 次/天 (10min 节流) | ¥0.002 (短 prompt) | ~10-20 次实际 | ¥0.02-0.04 |
| 日摘要 | 1 次/天 | ¥0.009 | 1 次 | ¥0.009 |
| 周摘要 | 1 次/周 | ¥0.013 | 0.14 次 | ¥0.002 |
| **中期记忆合计** | — | — | — | **~¥0.13-0.15/天** |
| 对话本身 | 用户活跃时 | ~¥0.01/轮 | ~50 轮 | ¥0.5 |
| **全部合计** | — | — | — | **~¥0.7/天 ≈ ¥21/月** |

---

### 4.6 记忆生命周期管理 (Memory Lifecycle)

> **核心理念**：不做"保留 X 天然后删除"的死板管理。所有记忆的生老病死都由 LLM 智能决策——就像人脑一样，遗忘是有选择性的，而不是按日历删除的。

#### 设计哲学：LLM 驱动的记忆管理

```
传统方案（死板）:                      PhysiBot（智能）:
├── "保留 7 天，到期删除"              ├── "LLM 判断这条记忆还有没有价值"
├── "最多保留 30 条"                   ├── "LLM 决定是压缩、合并还是丢弃"
├── "按时间戳 FIFO 淘汰"              ├── "重要的记忆永远保留，垃圾立即压缩"
└── 无脑删除 → 丢失关键信息            └── 智能遗忘 → 只留精华
```

#### 各层管理策略

| 记忆层 | 管理方式 | 触发时机 | LLM 的角色 |
|:---|:---|:---|:---|
| **L0 身份记忆** | 永久保留，用户/Agent 可更新 | 对话中发现新事实时 | 判断是否是值得记住的身份信息 |
| **L1 短期记忆** | 会话结束时 LLM 评估是否有值得提取的内容 → 升级到 L3 | 会话结束 | 从对话中提取关键信息，决定哪些升级为长期记忆 |
| **L2 片段** | 积累到一定量后 LLM 压缩合并 → 日摘要 | 每日合并 / 片段积累 >20 个 | 将多个片段压缩为有意义的日级叙事 |
| **L2 日摘要** | LLM 周期性审视，将有价值的模式 → 提炼入 L3 | 周合并 / 日摘要积累 >10 个 | 识别行为模式、提炼长期画像 |
| **L2 周摘要** | LLM 判断：仍然相关 → 保留；已过时 → 压缩为一句话追加到 L3 | 月度审视 | 判断"一个月前的事还重要吗" |
| **L3 长期记忆** | 永久保留，LLM 周期性审视去重/去矛盾/更新 | 周审视 + 会话后增量 | 整理画像、解决矛盾、删除过时信息 |
| **L4 指令** | 永久保留，开发者/用户维护 | 手动 | N/A |

#### AutoConsolidate——LLM 驱动的记忆整理

```
┌─────────────────────────────────────────────────────────┐
│           AutoConsolidate 触发与执行                     │
│                                                         │
│  触发条件（任一）:                                       │
│  ├── 每日 23:59 → 自动执行                              │
│  ├── 每周日 23:59 → 深度执行                            │
│  ├── 会话结束后 → 轻量执行                              │
│  ├── 手动触发（用户说"整理一下你的记忆"）               │
│  └── 片段数量 > 阈值 → 自动触发压缩                     │
│                                                         │
│  决策完全交给 LLM，不做硬编码的删除规则                  │
└─────────────────────────────────────────────────────────┘
```

##### 会话结束 → 轻量合并

```
LLM Prompt:
"以下是刚才与用户的完整对话。请判断：
 1. 对话中有没有值得记住的新信息？（如偏好变化、新的项目、情绪状态）
 2. 如果有，应该写入哪个长期记忆文件？（portrait/preferences/routines/...）
 3. 输出需要追加或修改的内容。如果没有新信息，回复'无更新'。"
```

##### 每日 → 标准合并

```
LLM Prompt:
"以下是今天所有的 30 分钟活动片段（共 N 个）。请完成：
 1. 将它们压缩为一份日级摘要（格式：一句话总结 + 工作/生活/健康三段）
 2. 检查今天有没有值得更新到用户画像的信息
 3. 对于已经合并进日摘要的片段，标记为'可回收'
 
 注意：如果某个片段记录了重要事件（如用户生气、重要决定、第一次使用某工具），
 即使已经合并，也不要标记为可回收——保留原始细节。"
```

##### 每周 → 深度整理

```
LLM Prompt:
"以下是你对用户的全部长期记忆（L3 所有文件）和本周的日摘要。
 请像一个尽职的秘书一样审视这些记忆：

 1. 矛盾检测：有没有互相矛盾的记忆？（如偏好冲突）→ 以最新为准
 2. 过时清理：有没有已经不再准确的信息？→ 更新或删除
 3. 模式发现：本周有没有新的行为模式值得记录？
 4. 重要性评估：现有的周摘要中，哪些仍然有价值？哪些可以压缩为一句话？
 5. 画像演化：用户的关注点/心情/工作重心有没有变化？

 输出：需要修改的文件及其新内容。保持每个文件简洁。"
```

#### 这意味着什么？

- **不会丢失重要信息**：即使是两个月前的片段，如果 LLM 认为它仍有价值（比如记录了用户的重要经历），就不会被删除
- **垃圾自动消失**：无意义的重复片段（"用户又在 VSCode 写代码了"×20）会被 LLM 自动压缩为一句话
- **画像持续进化**：不是每周机械式覆盖，而是 LLM 像人一样渐进式地加深对用户的理解
- **存储自然收敛**：因为 LLM 会持续压缩，磁盘使用会自然趋于稳定，不需要硬上限

#### 存储估算

由于 LLM 持续压缩，存储不会线性增长：

| 数据类型 | 1 个月 | 6 个月 | 1 年 |
|:---|:---|:---|:---|
| L1 短期会话 | ~7 MB | ~15 MB (压缩后) | ~25 MB (压缩后) |
| L2 片段+摘要 | ~5 MB | ~8 MB (老的被压缩) | ~10 MB |
| L3 长期画像 | ~30 KB | ~50 KB | ~80 KB |
| **合计** | **~12 MB** | **~23 MB** | **~35 MB** |

因为 LLM 持续做压缩和合并，存储增长是**亚线性**的——用一年可能只占 35 MB。

---

### 4.7 记忆系统的"活"的感觉

让记忆系统"活起来"的关键设计：

| 特性 | 实现 | 给用户的感觉 |
|:---|:---|:---|
| **记住你说过的话** | L1 短期记忆完整保留对话 | "刚才不是说过吗" → 它真记得 |
| **知道你在干什么** | L2 中期记忆每 30 分钟摘要 | "你今天写了 6 小时代码了" |
| **了解你的习惯** | L3 长期记忆提炼模式 | "你通常这个点该休息了" |
| **记住你的偏好** | L0 身份记忆精确事实 | "好的东哥" / 不会再用表情包 |
| **学习与成长** | AutoConsolidate 周期提炼 | 用越久，越懂你 |
| **可检视的大脑** | 纯 MD/JSONL 文件 | 打开文件夹就能看到它记了什么 |
| **可编辑的记忆** | 直接编辑文件即生效 | 删一行它就忘了 |

---

## 5 · 功能规格 (Feature Spec)

### P0 — 核心功能（MVP 必须）

| 功能 | 描述 | 依赖 |
|:---|:---|:---|
| **QQ 私聊对话** | 在 QQ 私聊中与 PhysiBot 自然聊天（仅私聊，不做群聊） | NapCatQQ |
| **记忆系统** | 五层记忆，每轮注入上下文 | 自研 |
| **屏幕感知** | 查询"我之前在做什么" | Screenpipe |
| **LLM 调用** | 支持 MiniMax / Anthropic / OpenAI | LLM Adapter |
| **配置界面** | 首次运行的配置向导（API Key、QQ 号等） | 自研 |
| **开箱即用 exe** | 双击运行，依赖自动安装 | Nuitka/PyInstaller |

### P1 — 重要功能（第二阶段）

| 功能 | 描述 | 依赖 |
|:---|:---|:---|
| **中期记忆** | 每小时活动摘要 + 日/周汇总 | Screenpipe + AW |
| **主动通知** | 久坐提醒、深夜提醒、异常检测 | MABWiser + 监控 |
| **IoT 控制** | 通过 HA 控制智能家居设备 | Home Assistant |
| **跨域联动** | 屏幕行为 + IoT 设备联动场景 | HA + Screenpipe |

### P2 — 加分功能（第三阶段）

| 功能 | 描述 | 依赖 |
|:---|:---|:---|
| **Dashboard** | Web 控制面板 + 记忆浏览器 | FastAPI + React |
| **多渠道** | Discord / 微信 适配 | 备选 |
| **语音交互** | 语音消息识别 + TTS 回复 | MiniMax 语音 API |
| **日报生成** | 自动生成今日工作日报 | L2 日摘要 |

---

## 6 · 用户体验流程 (UX Flow)

### 首次启动

```
双击 PhysiBot.exe
    │
    ├── 检测依赖 → 缺失则自动安装到 vendor/ 目录
    │
    ├── 弹出配置向导
    │   ├── Step 1: "告诉我你的名字和基本信息" → 写入 identity/profile.jsonl
    │   ├── Step 2: "选择 LLM 提供商" → MiniMax(推荐) / Anthropic / OpenAI
    │   ├── Step 3: "输入 API Key" → 测试连通性
    │   ├── Step 4: "输入你的 QQ 号" → 配置 NapCatQQ
    │   ├── Step 5: "是否连接 Home Assistant？" → 可选跳过
    │   └── Step 6: "启动 ✓"
    │
    └── 后台启动 Screenpipe + AW + NapCatQQ
        │
        └── QQ 收到第一条消息: "嗨东哥！我是 PhysiBot，你的私人助手。
                                我已经准备好了，有什么需要随时叫我~ 😊"
```

### 日常使用场景

```
场景 1: 主动关怀
───────────────────────────────────────
[14:30] 用户已连续编程 2.5 小时

PhysiBot (Agent Loop):
  1. 中期监控检测到：用户已久坐 2.5 小时
  2. 查询 MABWiser：此时提醒的历史接受率 → 78%
  3. 查询 L0 身份记忆：用户不希望深夜被打扰 → 当前是下午，OK
  4. 决定：发送提醒

PhysiBot → QQ: "东哥，你已经连续写了 2 个半小时代码了，
                去倒杯水活动一下？💧"

用户: "好，谢了"

PhysiBot → MABWiser: 奖励 +1（用户接受了提醒）
PhysiBot → memory_write: "用户接受了下午的久坐提醒"


场景 2: 上下文查询
───────────────────────────────────────
用户 → QQ: "我昨天晚上在查什么来着？"

PhysiBot (Agent Loop):
  1. 理解意图：查询昨天晚上的活动
  2. 调用 memory_read_midterm("daily/2026-04-04.md")
  3. 调用 screenpipe_search("昨天晚上", time_range="2026-04-04 20:00~23:59")
  4. 综合结果

PhysiBot → QQ: "昨天晚上你主要在查两个东西：
                1. Screenpipe 的 MCP Server 文档（大概 8-9 点）
                2. MiniMax 的 Function Calling 用法（9-10 点）
                后面 10 点半就去 B 站了 😄"


场景 3: IoT 联动
───────────────────────────────────────
用户 → QQ: "关掉书房的灯"

PhysiBot (Agent Loop):
  1. 理解意图：关灯
  2. 查询 identity/devices.jsonl → 找到 light.study_ceiling
  3. 检查权限 → 关灯是 ask_first 操作
  4. 但用户刚刚主动要求的 → 视为已确认

PhysiBot → ha_control("light.study_ceiling", "turn_off")
PhysiBot → QQ: "好嘞，书房灯已经关了 🌙"
```

---

## 7 · 技术约束 (Constraints)

| 约束 | 说明 |
|:---|:---|
| **LLM 不部署本地** | 只通过云 API 调用，降低硬件门槛 |
| **不使用向量数据库** | 纯 MD/JSONL 文件记忆，简洁可控 |
| **不使用 Agent 框架** | 不依赖 LangGraph/CrewAI 等，自研轻量 Agent Loop |
| **不做截图分析** | 用 OCR 文本 + 窗口标题替代，控制 token 成本 |
| **Windows 优先** | MVP 仅支持 Windows（Screenpipe 跨平台，但 exe 分发方式限定 Windows） |
| **单用户设计** | 不考虑多用户/多租户场景 |

---

## 8 · 成功指标 (Success Metrics)

### MVP 阶段

| 指标 | 目标 |
|:---|:---|
| 从双击 exe 到 QQ 收到第一条消息 | < 5 分钟 |
| 用户问"我上午做了什么"的回答准确率 | > 80% |
| 每轮对话 token 消耗 | < 5000 tokens |
| 每小时监控摘要 LLM 成本 | < ¥0.05 |
| 记忆注入后 Agent 记住用户名字 | 100% |

### 成熟阶段

| 指标 | 目标 |
|:---|:---|
| 用户使用 7 天后，画像准确率 | > 70% |
| 主动提醒的用户接受率 | > 60% |
| 仓库 GitHub Stars | 1000+ (发布后 3 个月) |
| 用户月均活跃对话天数 | > 20 天 |

---

## 9 · 开发优先级路线图 (Roadmap)

```
Week 1-2: Agent Core + 记忆系统 MVP
├── LLM Adapter (MiniMax/Anthropic/OpenAI)
├── Agent Loop (Think→Act→Check)
├── L0 身份记忆 + L4 指令记忆
├── L1 短期记忆（对话记录读写）
└── 命令行交互验证

Week 3-4: 感知 + QQ
├── Screenpipe 对接 + 工具注册
├── ActivityWatch 对接
├── NapCatQQ WebSocket 对接
├── L2 中期记忆（小时/日摘要）
└── QQ 完整对话链路

Week 5-6: 长期记忆 + IoT
├── L3 长期记忆（用户画像）
├── MEMORY.md 索引机制
├── AutoConsolidate 记忆合并
├── Home Assistant 对接
└── 跨域联动演示场景

Week 7-8: 打包 + Dashboard
├── Nuitka/PyInstaller .exe 打包
├── start.bat 依赖自动安装脚本
├── 首次配置向导
├── Dashboard MVP（可选）
└── 测试 + Bug 修复

Week 9-10: 发布
├── 文档 + Demo 视频
├── GitHub 开源发布
└── 社区推广
```

---

## 10 · 附录

### A. 记忆文件格式规范

| 文件类型 | 格式 | 编码 | 换行 |
|:---|:---|:---|:---|
| 身份信息 | JSONL | UTF-8 | LF |
| 短期对话 | JSONL | UTF-8 | LF |
| 中/长期记忆 | Markdown | UTF-8 | LF |
| 指令/索引 | Markdown | UTF-8 | LF |
| 配置 | YAML | UTF-8 | LF |

### B. 记忆系统与 Claude Code 的对比

| 维度 | Claude Code | PhysiBot |
|:---|:---|:---|
| L0 对应 | — | 身份记忆 (JSONL)，**新增** |
| L1 对应 | 会话上下文 | 短期记忆 (JSONL) |
| L2 对应 | — | 中期记忆 (小时/日/周摘要)，**新增** |
| L3 对应 | Topic Files | 长期记忆 (用户画像 MD) |
| L4 对应 | CLAUDE.md | PHYSI.md |
| 索引 | MEMORY.md | MEMORY.md (**借鉴**) |
| 合并 | AutoDream | AutoConsolidate (**借鉴**) |
| 场景差异 | 代码项目知识 | **用户个人生活与行为** |

### C. 关于"活的助手"的哲学

```
死的助手:                              活的助手（PhysiBot）:
├── 每次都问"你叫什么名字？"            ├── "嗨东哥"
├── 不知道你在做什么                    ├── "你今天写了 6 小时代码了"
├── 不知道你的习惯                      ├── "你通常这个点该喝水了"
├── 只能被动等你提问                    ├── 在合适的时机主动关心
├── 记忆是黑盒                          ├── 打开文件夹就能看到它记了什么
└── 换个设备就失忆了                    └── 复制 physi-data 文件夹就能迁移
```
