# AI Agent 开发项目规范

> 本文档定义 ai-agant 项目的开发规范和最佳实践

## 📋 目录

- [LLM 配置规范](#llm-配置规范)
- [代码组织规范](#代码组织规范)
- [环境变量规范](#环境变量规范)
- [命名规范](#命名规范)
- [注释规范](#注释规范)
- [文档规范](#文档规范)

---

## LLM 配置规范

### 🎯 核心原则

**所有章节必须使用统一的 LLM 配置，不得重复实现。**

### 📍 配置位置

```
ai-agant/
├── .env                    # ← 统一的 LLM 配置文件（所有章节共享）
├── llm/                    # ← LLM 通用封装模块
│   ├── __init__.py
│   └── client.py
└── chapterN/               # 各章节目录
    └── (章节代码)
```

### 🔧 使用方式

#### 方式一：使用通用封装（推荐）

```python
# 导入通用 LLM 客户端
from llm.client import get_llm_client

# 获取客户端（自动读取 .env 配置）
client = get_llm_client()

# 使用客户端
response = client.chat.completions.create(
    model=client.model_name,  # 使用配置的模型
    messages=[{"role": "user", "content": "你好"}]
)
```

#### 方式二：查看当前配置

```python
from llm.client import print_config

# 打印当前配置
print_config()
```

### ⚠️ 禁止事项

1. ❌ **禁止**在各章节中重复实现 LLM 客户端
2. ❌ **禁止**在各章节中创建独立的 `.env` 文件
3. ❌ **禁止**硬编码 API 密钥或端点地址
4. ❌ **禁止**使用特定提供商的专用 SDK

### ✅ 允许事项

1. ✅ 各章节可以使用 `.env` 中的配置
2. ✅ 各章节可以添加章节特定的环境变量（使用前缀）
3. ✅ 可以通过命令行参数覆盖环境变量

### 📝 支持的提供商

| 提供商 | LLM_PROVIDER | LLM_MODEL 示例 | 是否需要 BASE_URL |
|--------|---------------|-----------------|-------------------|
| Kimi | `kimi` | `kimi-k3` | 否 |
| Moonshot | `moonshot` | `kimi-k3` | 否 |
| OpenAI | `openai` | `gpt-4o` | 否 |
| DeepSeek | `deepseek` | `deepseek-chat` | 否 |
| Anthropic | `anthropic` | `claude-sonnet-4-20250514` | 否 |
| 阿里云 | `aliyun` | `qwen3.7-max-2026-05-20` | **是** |
| 自定义 | `custom` | 任意 | **是** |

---

## 代码组织规范

### 目录结构

```
ai-agant/
├── .env                    # 统一配置（所有章节共享）
├── .gitignore
├── README.md
├── llm/                    # LLM 通用封装
│   ├── __init__.py
│   └── client.py
├── chapter1/
├── chapter2/
│   ├── agent-status-bar/   # 状态栏实现（已完成，保留）
│   ├── local_llm_serving/
│   └── attention_visualization/
└── chapterN/
    ├── README.md           # 章节说明
    └── (章节代码)
```

### 文件命名

- Python 模块：小写字母 + 下划线 `my_module.py`
- 类名：大驼峰 `MyClass`
- 函数/变量：小写字母 + 下划线 `my_function`
- 常量：大写字母 + 下划线 `MY_CONSTANT`

---

## 环境变量规范

### 全局变量（在 ai-agant/.env 中定义）

```bash
# LLM 配置
API_KEY=xxx
LLM_PROVIDER=xxx
LLM_MODEL=xxx
BASE_URL=xxx

# 状态栏功能（全局）
ENABLE_TIMESTAMPS=true
ENABLE_TOOL_COUNTER=true
ENABLE_TODO_LIST=true
ENABLE_DETAILED_ERRORS=true
ENABLE_SYSTEM_STATE=true

# 执行选项
MAX_ITERATIONS=20
VERBOSE=false
COMMAND_TIMEOUT=30
```

### 章节特定变量（使用前缀）

如果某章节需要特定配置，使用章节前缀：

```bash
# chapter3 特定配置
CHAPTER3_SPECIAL_FEATURE=true
CHAPTER3_TIMEOUT=60
```

---

## 命名规范

### 类命名

```python
# ✅ 正确
class StatusBarAgent:
    pass

class SystemHintConfig:
    pass

# ❌ 错误
class statusbar_agent:
    pass
```

### 函数命名

```python
# ✅ 正确
def get_system_hint():
    pass

def execute_tool():
    pass

# ❌ 错误
def GetSystemHint():
    pass
def executeTool():
    pass
```

### 常量命名

```python
# ✅ 正确
MAX_ITERATIONS = 20
DEFAULT_TIMEOUT = 30

# ❌ 错误
maxIterations = 20
default_timeout = 30
```

---

## 注释规范

### 文件头注释

```python
"""
模块简短描述

更详细的描述（可选）。

使用示例:
    示例代码
"""
```

### 函数注释

```python
def function_name(param1: str, param2: int) -> bool:
    """
    函数简短描述

    Args:
        param1: 参数1说明
        param2: 参数2说明

    Returns:
        返回值说明

    Raises:
        ValueError: 错误说明
    """
    pass
```

### 行内注释

```python
# ✅ 正确
# 检查 API 密钥是否有效
if not api_key:
    raise ValueError("API 密钥未设置")

# ❌ 错误（无意义的注释）
# 设置 x
x = 1
```

---

## 文档规范

### README.md 要求

每个章节目录应包含 README.md，说明：

1. 章节主题
2. 学习目标
3. 项目列表
4. 快速开始
5. 配置说明

### 代码文档

- 所有公共函数必须有文档字符串
- 复杂逻辑必须添加注释说明
- 使用中文注释（保持项目一致性）

---

## 版本控制规范

### Git 提交信息

```
类型: 简短描述

详细说明（可选）

类型:
- feat: 新功能
- fix: 修复
- docs: 文档
- refactor: 重构
- style: 格式
- test: 测试
- chore: 构建/工具
```

### 分支管理

- `main`: 主分支，稳定代码
- `chapterN`: 章节开发分支
- `feature/xxx`: 功能分支

---

## 测试规范

### 测试文件命名

```
test_*.py              # 单元测试
test_*.py             # 集成测试
*_test.py             # 替代命名方式
```

### 测试组织

```
chapterN/
├── main.py
├── agent.py
├── test_*.py         # 与主要代码同级
└── tests/            # 或使用 tests/ 目录
    └── test_*.py
```

---

## 依赖管理规范

### requirements.txt

每个独立项目应包含 requirements.txt：

```txt
# 核心依赖
openai>=1.3.0
python-dotenv>=1.0.0

# 项目特定依赖
```

### 通用依赖

通用依赖放在 `/ai-agant/requirements.txt`：

```txt
# LLM 相关
openai>=1.3.0
python-dotenv>=1.0.0

# 数据处理
requests>=2.31.0

# 开发工具
pytest>=7.0.0
```

---

## 总结

遵循本规范可以：

1. ✅ 保持代码一致性
2. ✅ 减少重复工作
3. ✅ 便于协作维护
4. ✅ 提高代码质量

**核心原则：** 复用优先，DRY（Don't Repeat Yourself），KISS（Keep It Simple, Stupid）。
