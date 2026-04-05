# PhysiBot 代码规范

> 本文档定义项目的代码风格、命名约定、提交规范和质量门禁。
> 所有贡献者必须遵守。

---

## 1. 语言与运行时

| 项目 | 规范 |
|:---|:---|
| 语言 | Python 3.11+ |
| 包管理 | `pyproject.toml` (PEP 621) + `uv` |
| 异步 | 全局使用 `asyncio`，入口 `asyncio.run()` |
| 类型标注 | 全部代码使用 type hints，CI 通过 `mypy --strict` |

## 2. 代码风格

### 格式化

```toml
# pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.format]
quote-style = "double"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "ANN", "S", "B", "A", "COM", "C4", "PT"]
```

- **格式化工具**: `ruff format`
- **Lint 工具**: `ruff check`
- **行宽**: 100 字符
- **引号**: 双引号 `"`
- **缩进**: 4 空格

### 命名约定

| 对象 | 风格 | 示例 |
|:---|:---|:---|
| 模块/文件 | snake_case | `short_term.py`, `llm_adapter.py` |
| 类 | PascalCase | `AgentLoop`, `MemoryManager` |
| 函数/方法 | snake_case | `build_context()`, `load_identity()` |
| 常量 | UPPER_SNAKE | `MAX_TOKENS`, `DEFAULT_MODEL` |
| 异步函数 | snake_case + `async` | `async def fetch_ocr_data()` |
| 私有成员 | `_` 前缀 | `_client`, `_parse_response()` |
| 测试函数 | `test_` 前缀 | `test_agent_loop_returns_text()` |

### 导入顺序

```python
# 1. 标准库
import asyncio
from datetime import datetime
from pathlib import Path

# 2. 第三方库
import httpx
from anthropic import Anthropic

# 3. 项目内部
from physi_core.memory.identity import IdentityMemory
from physi_core.llm.adapter import LLMClient
```

## 3. 模块设计原则

### 依赖方向

```
config ← llm ← memory ← agent
                  ↑         ↑
           integrations   events
```

- **config**: 不依赖任何其他模块
- **llm**: 只依赖 config
- **memory**: 依赖 config + llm（AutoConsolidate 需要 LLM）
- **agent**: 依赖所有模块（顶层编排）
- **integrations**: 依赖 config（独立客户端封装）
- **events**: 依赖 config（独立事件总线）

### 每个模块必须

1. 有 `__init__.py` 暴露公开 API
2. 有对应的 `tests/unit/test_{module}.py`
3. 类使用 `@dataclass` 或 `Protocol` 定义接口
4. 外部 API 调用封装为独立客户端类，便于 mock

## 4. 异步规范

```python
# ✅ 正确：使用 async/await
async def fetch_screenpipe_data(start: datetime, end: datetime) -> list[OCRFrame]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(...)
        return parse_response(resp)

# ❌ 错误：在 async 函数中使用阻塞调用
async def bad_example():
    import requests  # 阻塞！
    resp = requests.get(...)  # 会阻塞事件循环

# ✅ 如需调用同步 API
async def call_sync_api():
    result = await asyncio.to_thread(sync_function, args)
```

## 5. 错误处理

```python
# 自定义异常继承树
class PhysiBotError(Exception): ...
class LLMError(PhysiBotError): ...
class LLMRateLimitError(LLMError): ...
class LLMAuthError(LLMError): ...
class MemoryError(PhysiBotError): ...
class IntegrationError(PhysiBotError): ...
class ToolExecutionError(PhysiBotError): ...

# ✅ 具体异常 + context
try:
    resp = await self._client.messages.create(...)
except anthropic.RateLimitError as e:
    raise LLMRateLimitError(f"Rate limited by {self.provider}") from e

# ❌ 裸 except
try:
    ...
except:  # 永远不要这样
    pass
```

## 6. 日志规范

```python
import logging

logger = logging.getLogger(__name__)

# 级别使用规范
logger.debug("Loading identity from %s", path)       # 调试细节
logger.info("Agent loop completed in %.2fs", elapsed) # 正常操作
logger.warning("Screenpipe not reachable, skipping")   # 可恢复问题
logger.error("LLM call failed: %s", error)             # 需要关注的错误
logger.critical("Config file missing, cannot start")   # 致命错误
```

## 7. Git 提交规范

### Conventional Commits

```
<type>(<scope>): <description>

[optional body]
[optional footer]
```

| Type | 说明 |
|:---|:---|
| `feat` | 新功能 |
| `fix` | Bug 修复 |
| `test` | 添加/修改测试 |
| `refactor` | 重构（不改变行为） |
| `docs` | 文档变更 |
| `chore` | 构建/工具/CI 变更 |

**示例**:
```
feat(memory): implement L0 identity JSONL reader
test(memory): add unit tests for identity loader
fix(llm): handle MiniMax rate limit with retry
docs: update architecture diagram
```

### 分支策略

```
main          ← 稳定版本，CI 必须通过
├── dev       ← 日常开发，功能合入
├── feat/xxx  ← 功能分支
└── fix/xxx   ← 修复分支
```

## 8. 质量门禁 (CI Checks)

每次 PR 必须通过：

```yaml
checks:
  - ruff format --check     # 格式检查
  - ruff check              # Lint
  - mypy --strict           # 类型检查
  - pytest --cov=80         # 测试覆盖率 ≥ 80%
  - pytest -m "not slow"    # 单元测试必须全过
```
