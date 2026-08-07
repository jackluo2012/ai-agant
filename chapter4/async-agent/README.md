# Flux 异步 Agent 运行时

> 配套《深入理解 AI Agent》第 4 章 **实验 4-5 ★★★**。事件驱动异步 Agent 框架（Flux）：并行工具、打断取消、状态检查点。

← [返回第 4 章目录](../README.md)

---

## 功能概述

本项目实现了事件驱动异步 Agent 框架（Flux）的核心功能，重点覆盖以下四个能力：

1. **异步工具执行**：`run_terminal_command` 立即返回占位符，任务在后台运行，不阻塞对话
2. **事件队列与批量处理**：非紧急事件进入 pending 缓冲，异步结果到达时一次性批量追加
3. **打断机制**：用户"取消/停止"立即取消当前 LLM 轮次和所有异步工具，并留痕
4. **并行工具的取消与状态查询**：`query_task` / `cancel_task` 按 ID 操作，异步完成后以新事件注入真实结果

## 架构设计

基于 `asyncio` 单线程事件循环，三个协程协作：

```
                    ┌──────────────┐
   用户消息/打断  ──▶ │    inbox     │  所有进来的原始事件
   异步任务完成   ──▶ │  (asyncio.Q) │
                    └──────┬───────┘
                           │
               ┌──────────▼───────────┐   classify_urgency()
               │     _dispatcher      │──▶ 打断/立即/排队
               └──────────┬───────────┘
     ┌────────────────┼───────────────────┐
打断 │             立即│              排队│
取消当前+后台任务    直接到 work      pending 缓冲；
                                     等异步结果时批量追加
               ┌──────────▼───────────┐
               │        work          │  待处理的事件批次
               └──────────┬───────────┘
               ┌──────────▼───────────┐
               │       _worker        │  每批次：追加轨迹 -> run_llm_turn()
               │   turn_task 可取消    │  （打断时取消子任务）
               └──────────────────────┘

  TaskManager: 模拟异步终端任务（启动/查询/取消/全部取消）
              自然完成 -> 以新事件注入 inbox
```

### 两种事件处理机制

1. **取消式处理**：紧急事件（用户"取消/停止"）立即取消当前 LLM 轮次和所有异步工具
2. **排队处理**：非紧急事件（补充指令）进入 `pending` 缓冲，异步工具完成时批量追加

### 紧急度判定规则

1. 打断关键词（取消/停止/stop...）→ `INTERRUPT`（取消式处理）
2. 提问（问号或疑问词，如"现在几点"）→ `IMMEDIATE`（立即回应，不打断后台任务）
3. 其他补充指令（如"用日语回复"）→ `DEFERRED`（排队，批量处理）

## 快速开始

### 1. 环境准备

确保已安装 Python 3.10+，并在项目根目录激活虚拟环境：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r chapter4/async-agent/requirements.txt
```

### 3. 配置 LLM（运行 LLM 场景时需要）

在项目根目录的 `.env` 文件中配置：

```bash
# 必需：API 密钥
API_KEY=your-api-key-here

# 必需：LLM 提供商（支持 kimi/openai/deepseek/anthropic/aliyun/custom）
LLM_PROVIDER=kimi

# 可选：模型名称（默认根据提供商自动选择）
LLM_MODEL=kimi-k3

# 可选：API 端点（部分提供商需要）
BASE_URL=https://api.moonshot.cn/v1
```

支持的提供商：
- `kimi` - Moonshot AI（推荐）
- `openai` - OpenAI
- `deepseek` - DeepSeek
- `anthropic` - Anthropic Claude
- `aliyun` - 阿里云（需要 BASE_URL）
- `custom` - 自定义端点（需要 BASE_URL）

### 4. 运行演示

#### 离线演示（无需配置，开箱即用）

```bash
cd chapter4/async-agent

# 默认：依次运行三个离线演示
python demo.py

# 或显式指定
python demo.py offline      # 依次运行三个离线演示
python demo.py parallel     # 能力一：并行 vs 串行墙钟时间对比（打印加速比）
python demo.py interrupt    # 能力二：打断/取消后恢复
python demo.py state        # 能力三：状态检查点持久化与跨会话恢复
```

#### LLM 验证场景（需要配置 .env）

```bash
# 运行全部四个场景
python demo.py scenarios

# 运行单个场景
python demo.py scenarios --scenario 1   # 场景1：异步执行 + 即时提问
python demo.py scenarios --scenario 2   # 场景2：批量处理
python demo.py scenarios --scenario 3   # 场景3：打断机制
python demo.py scenarios --scenario 4   # 场景4：并行取消与状态查询
```

## 使用方法

### 离线演示

离线演示不需要任何 API 配置，直接运行即可测量异步运行时的核心能力：

1. **parallel**：并行 vs 串行工具调用的墙钟时间对比，真实打印加速比
2. **interrupt**：长任务运行中被打断/取消，随后系统恢复
3. **state**：Agent 状态检查点持久化到磁盘，跨会话恢复并校验

### LLM 场景

需要配置 `.env` 中的 LLM，由真实模型做决策：

- **场景 1**：异步工具执行 + 长任务期间即时提问
- **场景 2**：事件队列与批量处理
- **场景 3**：打断机制
- **场景 4**：并行工具的取消与状态查询（竞速 + 按 50% 阈值取消）

## 项目结构

```
chapter4/async-agent/
├── README.md                  # 本文档
├── requirements.txt           # 项目依赖
├── events.py                  # 事件模型（Event、EventType、Urgency）
├── tasks.py                   # 异步任务管理器（模拟终端命令）
├── runtime.py                 # Agent 运行时（事件循环、LLM 调用）
├── async_demos.py             # 离线演示实现
├── demo.py                    # 统一 CLI 入口
├── agent_framework_design.md  # 框架设计文档
├── results/                   # 结果输出目录
└── logs/                      # 日志目录
```

## 配置说明

### LLM 配置（项目根目录 .env）

所有 LLM 相关配置在项目根目录的 `.env` 文件中统一管理：

```bash
# LLM 提供商和密钥（必需）
API_KEY=your-api-key
LLM_PROVIDER=kimi
LLM_MODEL=kimi-k3
BASE_URL=...  # 部分提供商需要

# 时间加速（可选，影响离线演示的节奏）
FLUX_TICK_REAL=0.4  # 1 个"模拟秒"对应的真实秒数
```

### 环境变量

- `FLUX_TICK_REAL`：时间加速因子，默认 0.4（即 2.5 倍速）

## 技术要点

1. **单线程 asyncio**：所有异步操作基于 `asyncio` 单线程事件循环，无线程安全问题
2. **事件驱动**：所有操作抽象为事件，按时间顺序追加到轨迹
3. **异步工具**：`run_terminal_command` 立即返回占位符，后台推进进度
4. **状态检查点**：轨迹 + 任务状态可持久化，支持跨会话恢复
5. **可取消的 LLM 轮次**：每个 LLM 调用作为可取消子任务，打断时直接取消

## 故障排除

### 问题：运行 LLM 场景时报错"未找到可用的 LLM Key"

**解决方法**：检查项目根目录 `.env` 文件中的 `API_KEY` 配置。

### 问题：运行 demo.py 时提示模块找不到

**解决方法**：确保从项目根目录运行，或在虚拟环境中运行：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
python chapter4/async-agent/demo.py
```

### 问题：推理模型输出异常或截断

**解决方法**：某些推理模型（如 kimi-k3）需要 `temperature=1` 且 `max_tokens>=2048`，框架会自动处理。

## 依赖说明

核心依赖由项目根目录提供，本项目特定依赖：

```
openai>=1.30.0          # OpenAI SDK（用于 LLM 调用）
python-dotenv>=1.0.0    # 环境变量加载
```

---

**技术栈**：Python 3.10+, asyncio, OpenAI API

**配套章节**：第 4 章 实验 4-5
