# AI Agent 状态栏增强系统

> 来自《AI Agent 开发实战》第2章 - 上下文工程

## 📖 项目简介

本项目实现了 **Agent 状态栏（Agent Status Bar）** 技术，这是上下文工程中的一个重要概念。通过在上下文末尾注入动态状态摘要，帮助 Agent 更好地理解自身状态、避免无限循环、提升任务管理效率。

### 🎯 核心思想

将手机屏幕顶部状态栏的概念引入 AI Agent：
- **手机状态栏**：显示时间、电量、信号强度——让用户随时掌握设备状态
- **Agent 状态栏**：显示工具调用次数、任务进度、系统状态——让模型随时掌握执行状态

### ⚡ 五种状态栏技术

| 技术 | 功能 | 效果 |
|------|------|------|
| **时间戳跟踪** | `[2025-09-14 10:30:45]` 格式前缀 | 帮助理解时序关系，支持时间模拟 |
| **工具调用计数** | `Tool call #3 for 'read_file'` | 防止无限循环，实现成本感知 |
| **TODO 列表管理** | 四种状态任务跟踪 | 迭代次数从21次降至15次 |
| **详细错误信息** | 四层错误详情+修复建议 | 成功率从60%提升到95% |
| **系统状态感知** | 工作目录、系统、Python版本 | 环境自适应决策 |

## 🚀 快速开始

### 1. 安装依赖

```bash
cd agent-status-bar
pip install -r requirements.txt
```

### 2. 配置 API 密钥

**方式一：使用环境变量**

```bash
# 通用 API 密钥（推荐）
export API_KEY='your-api-key-here'

# 或者使用特定提供商的密钥
export KIMI_API_KEY='your-kimi-key'
export OPENAI_API_KEY='your-openai-key'
```

**方式二：使用 .env 文件**

```bash
cp env.example .env
# 编辑 .env 文件，填入你的配置
```

**方式三：命令行参数**

```bash
python main.py --api-key "your-key" --provider openai --model "gpt-4o"
```

### 3. 运行示例

```bash
# 离线预览状态栏效果（无需 API 密钥）
python main.py --mode preview

# 执行单个任务
python main.py --mode single --task "分析当前项目结构"

# 交互模式
python main.py --mode interactive

# 功能演示
python main.py --mode demo

# 效果对比
python main.py --mode comparison
```

## 📖 详细使用指南

### 运行模式

| 模式 | 说明 | 命令 |
|------|------|------|
| `preview` | 离线预览状态栏效果 | `python main.py --mode preview` |
| `single` | 执行单个任务 | `python main.py --mode single --task "任务描述"` |
| `interactive` | 交互模式（默认） | `python main.py --mode interactive` |
| `demo` | 运行功能演示 | `python main.py --mode demo` |
| `comparison` | 对比有/无状态栏的效果 | `python main.py --mode comparison` |

### 功能开关

```bash
# 禁用特定功能
python main.py --mode single --task "任务" --no-timestamps
python main.py --mode single --task "任务" --no-counter
python main.py --mode single --task "任务" --no-todo
python main.py --mode single --task "任务" --no-errors
python main.py --mode single --task "任务" --no-state
```

### 配置预设

```bash
# 使用完整功能配置
python main.py --preset full --mode single --task "任务"

# 使用最小配置（禁用所有状态栏）
python main.py --preset minimal --mode single --task "任务"

# 使用调试配置（详细日志）
python main.py --preset debug --mode single --task "任务"

# 使用演示配置（时间模拟）
python main.py --preset demo --mode demo
```

### 🌐 自定义 LLM 配置

本项目支持任意兼容 OpenAI API 格式的 LLM 提供商。

#### 预设提供商

```bash
# Kimi / Moonshot（默认）
python main.py --provider kimi --api-key "your-key"

# OpenAI
python main.py --provider openai --api-key "sk-..." --model "gpt-4o"

# DeepSeek
python main.py --provider deepseek --api-key "sk-..." --model "deepseek-chat"

# Anthropic Claude
python main.py --provider anthropic --api-key "sk-..." --model "claude-sonnet-4-20250514"
```

#### 自定义提供商

```bash
# 使用自定义 API 端点
python main.py \
  --provider custom \
  --base-url "https://your-api-endpoint.com/v1" \
  --model "your-model-name" \
  --api-key "your-api-key"

# 示例：使用本地 Ollama
python main.py \
  --provider custom \
  --base-url "http://localhost:11434/v1" \
  --model "qwen3:0.6b" \
  --api-key "ollama"

# 示例：使用 Azure OpenAI
python main.py \
  --provider azure \
  --base-url "https://your-resource.openai.azure.com/openai/deployments/your-deployment" \
  --model "gpt-4" \
  --api-key "your-azure-key"
```

#### 环境变量配置

在 `.env` 文件中配置：

```bash
# 通用配置（所有提供商都支持）
API_KEY=your-api-key
LLM_PROVIDER=kimi
LLM_MODEL=kimi-k3
BASE_URL=

# 或者针对特定提供商
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=sk-...
```

## 🛠️ 编程方式使用

```python
from agent import StatusBarAgent, SystemHintConfig

# 创建配置
config = SystemHintConfig(
    enable_timestamps=True,
    enable_tool_counter=True,
    enable_todo_list=True,
    enable_detailed_errors=True,
    enable_system_state=True
)

# ===== 使用预设提供商 =====

# Kimi（默认）
agent = StatusBarAgent(
    api_key="your-kimi-key",
    provider="kimi",
    model="kimi-k3",
    config=config
)

# OpenAI
agent = StatusBarAgent(
    api_key="sk-...",
    provider="openai",
    model="gpt-4o",
    config=config
)

# DeepSeek
agent = StatusBarAgent(
    api_key="sk-...",
    provider="deepseek",
    model="deepseek-chat",
    config=config
)

# ===== 使用自定义提供商 =====

# 本地 Ollama
agent = StatusBarAgent(
    api_key="ollama",
    provider="custom",
    base_url="http://localhost:11434/v1",
    model="qwen3:0.6b",
    config=config
)

# 自定义 API 端点
agent = StatusBarAgent(
    api_key="your-api-key",
    provider="custom",
    base_url="https://your-api.com/v1",
    model="your-model",
    config=config
)

# ===== 执行任务 =====
result = agent.execute_task("创建一个 Python 脚本", max_iterations=20)

# 查看结果
print(result['final_answer'])
print(f"工具调用次数: {len(result['tool_calls'])}")
print(f"迭代次数: {result['iterations']}")
```

## 📂 可用工具

| 工具 | 说明 | 参数 |
|------|------|------|
| `read_file` | 读取文本文件内容 | `file_path`, `begin_line`, `number_lines` |
| `write_file` | 写入文件（创建/覆盖） | `file_path`, `content` |
| `code_interpreter` | 执行 Python 代码 | `code` |
| `execute_command` | 执行 Shell 命令 | `command`, `working_dir` |
| `rewrite_todo_list` | 重写 TODO 列表 | `items` (字符串列表) |
| `update_todo_status` | 更新 TODO 项目状态 | `updates` (ID 和状态列表) |

## 🔍 状态栏工作原理

### 注入位置

状态栏作为临时 `user` 消息注入到上下文**末尾**，而不是修改 `system` 消息：

```python
# 永久对话历史
conversation_history = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "[时间戳] 用户任务"},
    {"role": "assistant", "content": "...", "tool_calls": [...]},
    {"role": "tool", "content": "[时间戳] [工具调用 #N] 工具结果"}
]

# 临时消息（每次 LLM 调用时添加）
messages_to_send = conversation_history + [
    {"role": "user", "content": "=== 系统状态 ===\n...\n=== 当前任务 ===\n..."}
]
```

### 为什么这样设计？

1. **避免 KV Cache 污染**：修改 `system` 消息会破坏缓存，追加消息不会
2. **获得最高注意力**：末尾位置离即将生成的 token 最近，注意力权重最高
3. **保持对话简洁**：状态栏不存储在对话历史中

### 关键发现

> **重要**：光给模型读数不够，还需要配套的「操作手册」说明如何使用这些读数。

示例：
- ❌ 仅给读数：`elapsed_ms=5000` → 模型"看见"了但不会据此改变行为
- ✅ 读数+策略：`elapsed_ms=5000 expected_ms=500` + "超时需要诊断" → 模型知道该怎么做

## 📊 效果对比

### TODO 列表管理

- **禁用**：平均 21 次迭代，经常遗漏子任务
- **启用**：平均 15 次迭代，任务完整性显著提升

### 错误处理

- **禁用**：60% 成功率，盲目重试
- **启用**：95% 成功率，分析性问题解决

### 工具调用计数

防止无限循环：
- 第1次失败 → 检查路径
- 第2次失败 → 列出目录
- 第3次失败 → 改变策略

## 🔧 配置选项

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `KIMI_API_KEY` | Kimi API 密钥 | 必填 |
| `LLM_PROVIDER` | LLM 提供商 | `kimi` |
| `LLM_MODEL` | 模型名称 | `kimi-k3` |
| `ENABLE_TIMESTAMPS` | 启用时间戳 | `true` |
| `ENABLE_TOOL_COUNTER` | 启用工具计数 | `true` |
| `ENABLE_TODO_LIST` | 启用 TODO 列表 | `true` |
| `ENABLE_DETAILED_ERRORS` | 启用详细错误 | `true` |
| `ENABLE_SYSTEM_STATE` | 启用系统状态 | `true` |
| `MAX_ITERATIONS` | 最大迭代次数 | `20` |
| `VERBOSE` | 详细日志 | `false` |

### 代码配置

```python
from agent import SystemHintConfig

config = SystemHintConfig(
    enable_timestamps=True,          # 时间戳跟踪
    enable_tool_counter=True,         # 工具调用计数
    enable_todo_list=True,            # TODO 列表管理
    enable_detailed_errors=True,      # 详细错误信息
    enable_system_state=True,         # 系统状态感知
    timestamp_format="%Y-%m-%d %H:%M:%S",  # 时间戳格式
    simulate_time_delay=False,        # 时间模拟
    save_trajectory=True,              # 保存轨迹
    trajectory_file="trajectory.json"   # 轨迹文件路径
)
```

## 📁 轨迹文件

每次执行后，Agent 会保存轨迹到 JSON 文件，包含：
- 完整对话历史
- 工具调用记录（含耗时）
- TODO 列表变化
- 当前工作目录
- 配置信息

查看轨迹：
```bash
# 直接查看
cat trajectory.json | jq

# 或使用 jq 美化输出
cat trajectory.json | jq '.tool_calls[] | {tool_name, call_number, duration_ms}'
```

## 🎓 学习资源

- **原始概念**：《AI Agent 开发实战》第2章 - 上下文工程
- **理论基础**：注意力机制、上下文学习更像检索而非推理
- **设计原则**：显式状态优于隐式状态

## 📝 代码结构

```
agent-status-bar/
├── agent.py          # 核心 Agent 实现（带中文注释）
├── config.py         # 配置管理
├── main.py           # CLI 入口
├── requirements.txt  # 依赖列表
├── env.example       # 环境变量模板
└── README.md         # 本文档
```

## 🔮 高级话题

### 时间感（Time Sense）

状态栏技术揭示了 Agent 缺失的「时间感」能力，可拆分为三个轴：

- **紧迫度**（urgency）：预算轴——时间紧就果断交付，时间宽裕就多打磨
- **坚持度**（persistence）：终点轴——分清真墙和假墙
- **警觉度**（vigilance）：监控轴——异常耗时值得追查

### 上下文蒸馏

状态栏是「上下文蒸馏」最常见的形式：
- 提取分散在上下文各处的隐式状态
- 凝练为可直接使用的显式知识
- 以最小 token 成本提供关键信息

## 🤝 贡献

本项目是教学示例，欢迎提出问题和改进建议！

## 📄 许可

本项目内容来自《AI Agent 开发实战》，仅供学习使用。
