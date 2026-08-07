# 执行工具 MCP 服务器

> 配套《深入理解 AI Agent》第 4 章 **实验 4-2 ★★**
> 带安全机制的执行工具 MCP 服务器

## 项目概述

本项目是一个 MCP（Model Context Protocol）服务器，为 AI Agent 提供具有内置安全机制的综合执行工具。

### 核心功能

1. **LLM 事前审批**：不可逆操作在执行前需经二级 LLM 审批
2. **结果智能摘要**：超过阈值的输出由 LLM 自动摘要
3. **自动语法校验**：支持代码语法验证和反馈
4. **长输出持久化**：截断超长输出并保存到文件

### 工具分类

| 类别 | 工具 | 功能 |
|------|------|------|
| 文件系统 | `file_write` | 写入文件，自动语法校验 |
| 文件系统 | `file_edit` | 编辑已有文件，带 diff 预览 |
| 代码执行 | `code_interpreter` | Python 代码沙箱执行，带结果分析 |
| 终端操作 | `virtual_terminal` | Shell 命令执行，带错误总结 |
| 外部集成 | `google_calendar_add` | 添加 Google Calendar 事件 |
| 外部集成 | `github_create_pr` | 创建 GitHub Pull Request |

## 快速开始

### 1. 环境准备

```bash
# 确保在项目根目录（ai-agant）
cd /home/jackluo/my/ai-agent/ai-agant

# 激活虚拟环境
source .venv/bin/activate
```

### 2. 安装依赖

```bash
# 安装项目特定依赖
pip install -r chapter4/execution-tools/requirements.txt
```

### 3. 配置

在项目根目录的 `.env` 文件中配置 LLM 提供商（已配置则跳过）：

```bash
# LLM 配置（用于安全检查和摘要）
LLM_PROVIDER=kimi
API_KEY=your_kimi_api_key
LLM_MODEL=kimi-k3
BASE_URL=https://api.moonshot.cn/v1
```

**支持的提供商**：
- `kimi`：kimi-k3（默认）
- `openai`：gpt-4o
- `deepseek`：deepseek-chat
- `anthropic`：claude-sonnet-4-20250514
- `aliyun`：qwen3.7-max-2026-05-20（需要 BASE_URL）
- `custom`：自定义端点

### 4. 运行

#### 端到端演示（推荐首先运行）

```bash
python chapter4/execution-tools/cli.py demo
```

此演示无需 API Key 即可运行，展示所有工具的基本功能。

#### 列出所有工具

```bash
python chapter4/execution-tools/cli.py list
```

#### 单独调用工具

```bash
# 执行 Python 代码
python chapter4/execution-tools/cli.py code --language python --code "print(2 ** 10)"

# 执行 Shell 命令
python chapter4/execution-tools/cli.py shell "ls -la"

# 写入文件
python chapter4/execution-tools/cli.py write --path test.txt --content "Hello, World!" --overwrite

# 编辑文件
python chapter4/execution-tools/cli.py edit --path test.txt --search Hello --replace "你好"
```

## 运行 MCP 服务器

```bash
python chapter4/execution-tools/server.py
```

## 配合 MCP 客户端使用

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def use_tools():
    server_params = StdioServerParameters(
        command="python",
        args=["chapter4/execution-tools/server.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 写入文件
            result = await session.call_tool("file_write", {
                "path": "test.py",
                "content": "print('Hello, World!')"
            })

            # 执行 Python 代码
            result = await session.call_tool("code_interpreter", {
                "code": "import math\nprint(math.sqrt(16))"
            })

asyncio.run(use_tools())
```

## 命令行参数

### 全局开关（放在子命令之前）

| 开关 | 作用 |
|------|------|
| `--provider` | 覆盖 LLM 提供商 |
| `--workspace` | 覆盖工作目录 |
| `--no-approval` | 关闭危险操作的 LLM 事前审批 |
| `--no-verify` | 关闭写文件/代码的自动语法校验 |
| `--no-summarize` | 关闭长输出的 LLM 总结 |

> **警告**：`--no-approval` 会绕过安全审批，仅适用于受控的本地演示环境。

## 离线运行

以下功能无需 API Key 即可工作：
- `list`：列出工具
- `demo`：运行演示
- `code`/`shell`/`write`/`edit`（关闭审批/总结/非 Python 校验时）

需要 API Key 的功能：
- LLM 事前审批
- 长输出摘要
- 非 Python 语法校验

## 测试

```bash
# 测试文件操作
python chapter4/execution-tools/test_file_tools.py

# 测试执行工具
python chapter4/execution-tools/test_execution_tools.py

# 测试外部集成
python chapter4/execution-tools/test_external_tools.py
```

## 项目特定配置

以下配置项可在项目根目录 `.env` 中设置：

```bash
# 安全设置
REQUIRE_APPROVAL_FOR_DANGEROUS_OPS=true
AUTO_SUMMARIZE_COMPLEX_OUTPUT=true
AUTO_VERIFY_CODE=true
MAX_OUTPUT_LENGTH=1000

# 模型参数
TEMPERATURE=0.7
MAX_TOKENS=4096

# 外部服务（可选）
GITHUB_TOKEN=your_github_token
GOOGLE_CALENDAR_CREDENTIALS_FILE=credentials.json
```

## 架构说明

服务器采用分层架构：

```
┌─────────────────────────────────────┐
│           安全层 (Safety Layer)        │
│   LLM 审批、输入验证、权限控制          │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│           工具层 (Tool Layer)         │
│   文件操作、代码执行、终端命令          │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│          校验层 (Verify Layer)        │
│   语法检查、结果验证、错误分析          │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│         集成层 (Integration Layer)     │
│   外部 API、MCP 协议适配              │
└─────────────────────────────────────┘
```

## 目录结构

```
chapter4/execution-tools/
├── README.md              # 本文档
├── requirements.txt       # 项目依赖
├── config.py             # 项目配置（不含 LLM 配置）
├── llm_helper.py         # LLM 辅助模块
├── cli.py               # 命令行入口
├── server.py            # MCP 服务器
├── execution_tools.py   # 执行工具实现
├── file_tools.py        # 文件操作工具
├── multilang_executor.py # 多语言代码执行
├── terminal_controller.py # 终端控制器
├── external_tools.py    # 外部集成工具
├── examples.py          # 使用示例
├── results/             # 输出结果目录
└── logs/                # 日志目录
```

## 故障排除

### ImportError: No module named 'llm.client'

确保：
1. 在项目根目录运行
2. 虚拟环境已激活
3. 已运行 `pip install -e .`

### LLM 调用失败

检查 `.env` 文件中的配置：
- `API_KEY` 是否正确
- `BASE_URL` 是否可访问
- `LLM_MODEL` 是否支持

### 文件操作权限问题

检查工作目录配置：
- 确保 `WORKSPACE_DIR` 存在且可写
- 或使用 `--workspace` 参数指定工作目录

## 相关文档

- [实验说明](EXPERIMENT.md)
- [Docker 配置](Dockerfile)
- [环境变量示例](env.example)
