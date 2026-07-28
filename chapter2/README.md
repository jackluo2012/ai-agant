# Chapter 2: 本地 LLM 工具调用演示

本目录包含本地大语言模型（LLM）工具调用的完整实现和示例。

## 📋 目录

- [功能概述](#功能概述)
- [系统架构](#系统架构)
- [环境准备](#环境准备)
- [快速开始](#快速开始)
- [详细使用说明](#详细使用说明)
- [可用工具](#可用工具)
- [配置说明](#配置说明)
- [示例任务](#示例任务)
- [故障排查](#故障排查)

## 🎯 功能概述

本项目演示如何在本地 LLM 上实现类似 OpenAI 的工具调用（Tool Calling）功能，支持：

- **🔧 工具调用**：让 LLM 能够调用外部工具获取实时信息
- **💬 流式响应**：实时流式输出 AI 的思考过程和响应
- **🌐 多后端支持**：支持 llama.cpp（Ollama）和 vLLM 两种后端
- **🚀 跨平台**：自动检测并选择最佳后端（Linux GPU → vLLM，其他 → Ollama）
- **📦 多种工具**：天气查询、时间查询、货币转换、代码解释器等

## 🏗️ 系统架构

```
chapter2/local_llm_serving/
├── main.py              # 主入口，跨平台智能代理
├── agent.py             # vLLM 工具调用代理实现
├── ollama_native.py    # Ollama 原生接口实现
├── tools.py             # 工具注册表和工具函数
├── config.py            # 配置文件
├── server.py            # vLLM 服务器管理
└── test_*.py            # 各种测试脚本
```

### 核心组件说明

| 文件 | 说明 |
|------|------|
| `main.py` | **主入口文件**，提供跨平台的智能工具调用代理 |
| `agent.py` | vLLM 后端的代理实现，使用 OpenAI 兼容 API |
| `ollama_native.py` | Ollama/llama.cpp 后端的代理实现 |
| `tools.py` | 工具注册表，定义所有可用的工具函数 |
| `config.py` | 配置管理，支持环境变量配置 |
| `server.py` | vLLM 服务器启动和管理 |

## 🛠️ 环境准备

### 1. Python 虚拟环境

项目使用 `uv` 创建的虚拟环境（`.venv`）：

```bash
# 激活虚拟环境
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate     # Windows
```

### 2. 安装依赖

```bash
# 使用 uv 安装依赖
uv pip install PyPDF2 requests python-dotenv ollama openai

# 或使用 requirements.txt（如果有）
pip install -r requirements.txt
```

### 3. 后端选择

本项目支持两种后端，系统会自动选择：

#### A. llama.cpp / Ollama（推荐用于 CPU/Mac）

**安装 Ollama：**
- **Mac**: `brew install ollama`
- **Linux**: `curl -fsSL https://ollama.com/install.sh | sh`
- **Windows**: 从 [ollama.com](https://ollama.com) 下载安装

**启动 Ollama 服务：**
```bash
ollama serve
```

**下载模型（推荐）：**
```bash
# Qwen3 小模型（推荐用于工具调用）
ollama pull qwen3:0.6b

# 或其他模型
ollama pull llama3.2:3b
```

#### B. vLLM（推荐用于 Linux + NVIDIA GPU）

**安装 vLLM：**
```bash
pip install vllm
```

**vLLM 会自动启动和管理**，无需手动配置。

## 🚀 快速开始

### 方式一：使用主程序（推荐）

```bash
cd /home/jackluo/my/ai-agent/ai-agant

# 激活虚拟环境
source .venv/bin/activate

# 运行主程序（自动检测最佳后端）
python chapter2/local_llm_serving/main.py
```

### 方式二：使用 Ollama 原生接口

```bash
# 确保 Ollama 正在运行
ollama serve

# 运行 Ollama 原生实现
python chapter2/local_llm_serving/ollama_native.py
```

### 方式三：查看系统信息

```bash
# 检查系统配置和支持的后端
python chapter2/local_llm_serving/main.py --info
```

## 📖 详细使用说明

### 交互模式（默认）

```bash
python chapter2/local_llm_serving/main.py
# 或
python chapter2/local_llm_serving/main.py --mode interactive
```

**交互命令：**

| 命令 | 说明 |
|------|------|
| `/reset` | 重置对话历史 |
| `/tools` | 显示可用工具列表 |
| `/samples` | 显示示例任务 |
| `/sample <n>` | 运行第 n 个示例任务 |
| `/stream` | 切换流式输出模式 |
| `/help` | 显示帮助信息 |
| `/exit` 或 `quit` | 退出程序 |

### 单任务模式

```bash
# 运行指定任务
python chapter2/local_llm_serving/main.py --mode single --task "你的问题"

# 运行示例任务（交互式选择）
python chapter2/local_llm_serving/main.py --mode single
```

### 指定后端

```bash
# 强制使用 vLLM
python chapter2/local_llm_serving/main.py --backend vllm

# 强制使用 Ollama
python chapter2/local_llm_serving/main.py --backend ollama

# 自动检测（默认）
python chapter2/local_llm_serving/main.py --backend auto
```

## 🔧 可用工具

| 工具名称 | 功能描述 | 参数 |
|----------|----------|------|
| `get_current_temperature` | 获取指定位置的当前温度 | location, unit |
| `get_current_time` | 获取指定时区的当前时间 | timezone |
| `convert_currency` | 货币转换（使用实时汇率） | amount, from_currency, to_currency |
| `code_interpreter` | 执行 Python 代码进行复杂计算 | code |

### 工具使用示例

```
👤 你: 北京现在的天气怎么样？
🤖 AI: [调用 get_current_temperature 工具]
   根据查询结果，北京目前的温度是...

👤 你: 100美元等于多少人民币？
🤖 AI: [调用 convert_currency 工具]
   根据当前汇率，100美元约等于...

👤 你: 计算 2^10 的结果
🤖 AI: [调用 code_interpreter 工具]
   2^10 = 1024
```

## ⚙️ 配置说明

### 环境变量配置（可选）

创建 `.env` 文件：

```bash
# llama.cpp / Ollama 配置
LLAMA_HOST=192.168.1.158      # Ollama 服务器地址
LLAMA_PORT=11434               # Ollama 端口
MODEL_NAME=MiniCPM5-1B-Q4_K_M.gguf  # 模型名称

# vLLM 配置（可选）
VLLM_HOST=localhost
VLLM_PORT=8000
VLLM_MODEL_NAME=Qwen/Qwen3-0.6B

# 日志级别
LOG_LEVEL=INFO
```

### 修改默认配置

编辑 `config.py` 文件修改默认配置：

```python
# 修改默认服务器地址
LLAMA_HOST = "192.168.1.158"

# 修改默认模型
LLAMA_MODEL = "your-model-name"

# 启用/禁用特定工具
ENABLE_WEATHER_TOOL = True
ENABLE_CALCULATOR_TOOL = True
```

## 📝 示例任务

运行以下示例查看工具调用能力：

```bash
python chapter2/local_llm_serving/main.py --mode single
```

**可用示例：**

1. **🕐 当前时间检查** - 查询特定城市的当前时间
2. **☀️ 简单天气查询** - 获取单个城市的当前天气
3. **☀️ 时间和天气检查** - 同时查询时间和天气
4. **💵 复利计算** - 使用代码解释器计算复利
5. **🌡️ 多城市天气分析** - 比较多个城市的天气数据
6. **💰 复杂财务分析** - 多步财务计算和货币转换
7. **⏰ 全球时区协调** - 跨时区会议时间安排

## 🔍 故障排查

### 问题：PyPDF2 模块未找到

```bash
uv pip install PyPDF2
```

### 问题：Ollama 连接失败

**检查 Ollama 是否运行：**
```bash
ollama list
```

**启动 Ollama 服务：**
```bash
ollama serve
```

**检查模型是否已下载：**
```bash
ollama list
ollama pull qwen3:0.6b
```

### 问题：vLLM 初始化失败

**检查 CUDA 是否可用：**
```bash
python -c "import torch; print(torch.cuda.is_available())"
```

**安装 vLLM：**
```bash
pip install vllm
```

### 问题：端口被占用

修改 `.env` 文件中的端口配置：
```bash
LLAMA_PORT=11434
VLLM_PORT=8000
```

### 调试模式

启用详细日志：
```bash
LOG_LEVEL=DEBUG python chapter2/local_llm_serving/main.py
```

## 🧪 测试脚本

项目包含多个测试脚本用于验证功能：

```bash
# 测试流式输出
python chapter2/local_llm_serving/test_streaming.py

# 测试天气工具
python chapter2/local_llm_serving/test_weather.py

# 测试代码解释器
python chapter2/local_llm_serving/test_code_interpreter_full.py

# 测试并行工具调用
python chapter2/local_llm_serving/test_parallel_tools.py

# 兼容性检查
python chapter2/local_llm_serving/check_compatibility.py
```

## 📚 进阶使用

### 自定义工具

编辑 `tools.py` 添加自定义工具：

```python
def my_custom_tool(self, param1: str) -> str:
    """自定义工具描述"""
    # 实现你的逻辑
    return "结果"

# 注册工具
self.register_tool(
    name="my_custom_tool",
    function=self.my_custom_tool,
    description="工具描述",
    parameters={
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "参数说明"}
        },
        "required": ["param1"]
    }
)
```

### 集成到你的项目

```python
from chapter2.local_llm_serving.main import ToolCallingAgent

# 初始化代理
agent = ToolCallingAgent()

# 进行对话
response = agent.chat("你的问题")
print(response)
```

## 📞 支持

如有问题，请检查：
1. 虚拟环境是否激活
2. 所有依赖是否安装
3. 后端服务（Ollama/vLLM）是否运行
4. 模型是否已下载

---

**提示**：首次运行时，系统会自动检测并选择最适合你系统的后端。推荐使用交互模式探索各种功能！
