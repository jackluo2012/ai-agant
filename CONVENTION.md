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

---

## 代码迁移规范

### 迁移检查清单

当从外部项目迁移代码到 ai-agant 项目时，必须完成以下步骤：

#### 1. LLM 客户端迁移

**必须做：**
```python
# ❌ 删除原有的 LLM 客户端初始化
# from openai import OpenAI
# self.client = OpenAI(api_key=..., base_url=...)

# ✅ 改用统一客户端
from llm.client import get_llm_client
self.client = get_llm_client()
self.model = self.client.model_name
```

#### 2. 配置文件迁移

**必须做：**
- 删除独立的 `.env` 文件
- 删除独立的 `config.py` 中的 LLM 配置
- 使用根目录的 `.env` 和 `llm.client`

**可以保留：**
- 实验特定配置（如 `MAX_ITERATIONS`、`CONTEXT_WINDOW_SIZE`）
- 章节特定环境变量（使用前缀，如 `CHAPTER3_*`）

#### 3. 中文化要求

**必须中文化：**
- 所有用户可见的提示词（system prompt）
- 所有用户可见的消息输出
- 所有注释和文档字符串
- README.md 文档

**示例：**
```python
# ❌ 英文提示词
prompt = "Summarize the following content..."

# ✅ 中文提示词
prompt = "请总结以下内容..."
```

#### 4. 文档要求

**必须创建：**
- `README.md` - 包含以下内容：
  - 项目概述
  - 安装说明
  - 使用方法
  - 配置说明
  - 实验结果（如适用）
  - 技术要点

**推荐包含：**
- 策略/方法对比表格
- 故障排除指南
- 扩展开发指南

#### 5. 目录结构

**标准结构：**
```
chapterN/
└── project_name/
    ├── README.md           # 必须
    ├── requirements.txt    # 如有额外依赖
    ├── config.py           # 仅含非 LLM 配置
    ├── agent.py            # 主要代码
    ├── main.py             # 交互入口
    ├── experiment.py       # 实验脚本（如适用）
    ├── results/            # 结果输出目录
    └── logs/               # 日志目录
```

#### 6. 依赖管理

**requirements.txt：**
```txt
# 核心依赖由根目录提供，此处仅列出实验特定依赖
beautifulsoup4>=4.12.0
lxml>=5.0.0
```

**不要重复列出：**
- `openai` - 由根目录统一管理
- `python-dotenv` - 由根目录统一管理

### 完整迁移步骤

当从外部项目迁移代码到 ai-agant 项目时，按照以下步骤进行：

#### 第一步：准备和复制

```bash
# 1. 创建目标目录结构
mkdir -p chapterN/project_name/{results,logs,data}

# 2. 复制所有源文件
cp -r /path/to/source/project/* chapterN/project_name/
```

#### 第二步：添加路径处理（**重要**）

在每个需要导入 `llm.client` 的文件开头，添加以下代码：

```python
import sys
import os

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from llm.client import get_llm_client
except ImportError:
    get_llm_client = None
```

**为什么需要这样做：**
- 项目运行在虚拟环境 `.venv` 中
- 需要将项目根目录添加到 Python 路径
- 确保能找到 `llm` 模块

#### 第三步：修改 LLM 客户端初始化

**必须修改的文件类型：**
- 对话代理类（conversational_agent.py, agent.py 等）
- 后台处理器类（background_memory_processor.py 等）
- 主入口文件（main.py, quickstart.py 等）

**修改方式：**

```python
# ❌ 删除原有方式
from openai import OpenAI
self.client = OpenAI(api_key=api_key, base_url=base_url)

# ✅ 改用统一客户端
self.client = get_llm_client(provider=provider, model=model)
self.model = self.client.model_name
```

**参数调整：**
- 删除所有 `api_key` 参数
- 保留 `provider` 和 `model` 参数（可选，默认使用项目配置）

#### 第四步：清理配置文件

**修改 config.py：**
- 删除 LLM 提供商相关的所有配置
- 删除 `get_api_key()` 方法
- 删除 `validate()` 方法中的 API key 验证
- 删除 `PROVIDER_DEFAULT_MODELS` 等常量
- 仅保留项目特定配置（如记忆模式、超时等）

#### 第五步：中文化内容

**必须中文化的内容：**
1. 所有用户可见的提示词（system prompt）
2. 工具描述（tool descriptions）
3. 例子中的英文内容（人名、公司名、地点等）
4. 用户可见的消息输出

**示例修改：**

```python
# ❌ 英文提示词
prompt = "You are a helpful assistant..."

# ✅ 中文提示词
prompt = "你是一个有用的助手..."

# ❌ 英文例子
"User works at TechCorp as John Smith..."

# ✅ 中文例子
"用户在腾讯公司担任张三..."
```

#### 第六步：更新入口文件

**修改 main.py 等入口文件：**
- 删除 `Config.get_api_key()` 调用
- 删除 `Config.validate()` 调用
- 删除 API key 相关的错误提示

#### 第七步：更新依赖文件

**修改 requirements.txt：**
```txt
# 核心依赖由根目录提供，此处仅列出实验特定依赖
# 删除：openai, python-dotenv
```

#### 第八步：更新文档

**README.md 必须包含：**
- 项目概述
- 安装说明（强调项目根目录 .env 配置）
- 使用方法
- API 使用示例（删除 api_key 参数）
- 迁移说明

#### 第九步：语法验证

```bash
# 验证 Python 语法
python3 -m py_compile chapterN/project_name/*.py
```

#### 第十步：运行验证

**虚拟环境位置：** `.venv/`（项目根目录）

**正确运行方式：**

```bash
# 方式一：从项目根目录运行（推荐）
cd ai-agant
source .venv/bin/activate
python3 chapter3/user-memory/quickstart.py

# 方式二：使用完整路径
cd ai-agant
source .venv/bin/activate
python3 chapter3/project_name/main.py --mode interactive

# 方式三：添加根目录到 PYTHONPATH
cd ai-agant
export PYTHONPATH=$PYTHONPATH:$(pwd)
source .venv/bin/activate
cd chapter3/project_name
python3 quickstart.py
```

**注意：**
- 必须先激活虚拟环境
- 建议从项目根目录运行，使用完整路径
- 或在代码中添加路径处理（见第二步）

### 迁移验证清单

迁移完成后，验证以下内容：

- [ ] 在需要导入 `llm.client` 的文件中添加了路径处理代码
- [ ] 使用 `from llm.client import get_llm_client` 获取 LLM 客户端
- [ ] 删除了所有硬编码的 API 密钥和端点
- [ ] 所有提示词已中文化
- [ ] 所有注释已中文化
- [ ] README.md 包含完整文档
- [ ] 代码遵循命名规范
- [ ] 创建了必要的输出目录（results/, logs/）
- [ ] 在虚拟环境中能正常运行

### 快速迁移命令

```bash
# 1. 创建目录
mkdir -p chapterN/project_name
mkdir -p chapterN/project_name/{results,logs}

# 2. 迁移代码后，在每个导入 llm.client 的文件中添加路径处理
# 见第二步的代码模板

# 3. 验证语法
python3 -m py_compile chapterN/project_name/*.py

# 4. 激活虚拟环境并测试
cd ai-agant
source .venv/bin/activate
python3 chapterN/project_name/main.py --help
```

---

## 总结

遵循本规范可以：

1. ✅ 保持代码一致性
2. ✅ 减少重复工作
3. ✅ 便于协作维护
4. ✅ 提高代码质量
5. ✅ 简化代码迁移

**核心原则：** 复用优先，DRY（Don't Repeat Yourself），KISS（Keep It Simple, Stupid）。
