# 事件驱动 AI Agent

> 配套《深入理解 AI Agent》第 4 章 **实验 4-4 ★★★**。FastAPI 事件驱动 Agent，支持异步 MCP 工具加载。

← [返回第 4 章目录](../README.md)

---

## 功能概述

一个具备**原生异步支持**的现代 AI Agent，可响应来自多种来源的事件。基于 **FastAPI** 构建，集成了 **42 个 MCP 工具**，提供浏览器自动化、网络搜索、文档处理等增强功能。

### 核心能力

- ✅ **原生异步** — FastAPI + 清晰的 async/await 支持
- ✅ **42 个 MCP 工具** — 自动从 3 个 MCP 服务器加载
- ✅ **事件驱动** — 响应 Web 消息、邮件、GitHub 更新、定时器
- ✅ **系统提示** — 时间戳、工具计数、TODO 管理
- ✅ **自动 API 文档** — 交互式 Swagger UI：`/docs`
- ✅ **后台任务** — 进程监控与系统告警

### MCP 工具分类

**协作工具**（18 个）：
- 浏览器自动化（导航、截图、执行任务）
- 通知（邮件、Telegram、Slack、Discord）
- 人机协同（管理员审批、输入请求）
- 定时器管理（一次性、循环）

**执行工具**（6 个）：
- 文件操作（写入、带校验的编辑）
- 代码执行（Python 解释器、shell 命令）
- 外部集成（Google Calendar、GitHub PR）

**感知工具**（18 个）：
- 网络搜索与内容抽取
- 文档阅读（PDF、DOCX、PPTX）
- 多模态解析（图像、视频、网页）
- 公开数据（天气、股票、Wikipedia、ArXiv）
- 私有数据（Google Calendar、Notion）

---

## 快速开始

### 1. 环境准备

确保项目根目录的 `.env` 文件中已配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3   # 可选
```

### 2. 安装依赖

```bash
cd chapter4/agent-with-event-trigger
pip install -r requirements.txt
```

### 3. 事件驱动演示（离线可运行，无需 API Key）

推荐先运行 `event_loop_demo.py`，直观演示本章核心概念——**外部世界主动唤醒 Agent**。

```bash
# 离线演示全部触发器（一次性定时器 + 循环定时器 + 文件监听）
python event_loop_demo.py --mock

# 只演示一次性定时器；2 秒后触发，共运行 6 秒
python event_loop_demo.py --mock --trigger timer --delay 2 --duration 6

# 每 3 秒触发一次循环定时器
python event_loop_demo.py --mock --trigger recurring --interval 3 --duration 12

# 监听目录，向其中写入文件即可触发事件
python event_loop_demo.py --mock --trigger file --watch-dir watched_dir
```

去掉 `--mock` 即接入真实的大模型（默认仅用内置工具，不加载 MCP）。

### 4. 启动 HTTP 服务器

```bash
python server.py
```

服务器支持命令行参数（优先级高于环境变量）：

```bash
python server.py --port 9000           # 自定义端口
python server.py --provider doubao     # 指定大模型提供商
python server.py --no-mcp              # 只用内置工具，不加载 MCP 工具
```

### 5. 发送测试事件

```bash
# 交互模式
python client.py --mode interactive

# 测试场景
python client.py --mode test

# 发送单条事件
python client.py --message "创建一个 Python hello world 脚本"
```

---

## API 端点

### 核心端点

```bash
# 健康检查
curl http://localhost:8000/health

# 检查 MCP 工具状态
curl http://localhost:8000/mcp/status

# 发送事件
curl -X POST http://localhost:8000/event \
  -H 'Content-Type: application/json' \
  -d '{
    "event_type": "web_message",
    "content": "搜索 Python 异步编程最佳实践",
    "metadata": {"user": "demo"}
  }'

# 获取 Agent 状态
curl http://localhost:8000/agent/status

# 重置 Agent 状态
curl -X POST http://localhost:8000/agent/reset

# 重新加载 MCP 工具
curl -X POST http://localhost:8000/mcp/reload
```

### 交互式 API 文档

访问 **http://localhost:8000/docs** 可以：
- 📖 浏览全部端点
- 🧪 交互式测试 API
- 📝 查看请求/响应 schema
- ⚡ 一键发送事件

---

## 项目结构

```
agent-with-event-trigger/
├── agent.py                 # 事件驱动 Agent 实现
├── event_types.py           # 事件类型定义
├── event_loop_demo.py       # 离线事件循环演示
├── server.py                # FastAPI 服务器（主入口）
├── client.py                # 事件客户端（测试用）
├── quickstart.py            # 快速启动脚本
├── example_with_mcp.py      # MCP 集成示例
├── requirements.txt         # 项目依赖
├── env.example              # 配置示例
├── README.md                # 本文件
├── results/                 # 结果输出目录
└── logs/                    # 日志目录
```

---

## 事件类型

```python
class EventType(Enum):
    # 外部输入事件
    WEB_MESSAGE = "web_message"           # Web 界面
    IM_MESSAGE = "im_message"             # 即时通讯
    EMAIL_REPLY = "email_reply"           # 邮件回复
    GITHUB_PR_UPDATE = "github_pr_update" # PR 通知
    TIMER_TRIGGER = "timer_trigger"       # 定时任务（一次性/循环）
    FILE_CHANGE = "file_change"           # 文件变更触发（创建/修改）

    # 系统提醒事件
    USER_TIMEOUT = "user_timeout"         # 用户无活动
    PROCESS_TIMEOUT = "process_timeout"   # 长时间运行的进程
    SYSTEM_ALERT = "system_alert"         # 系统告警
```

---

## 配置说明

### LLM 配置（项目根目录 .env）

```bash
# 必需
API_KEY=your-key

# 可选
LLM_PROVIDER=kimi              # kimi, siliconflow, doubao, deepseek, aliyun 等
LLM_MODEL=kimi-k3               # 模型覆盖
```

### 项目特定配置（可选）

```bash
ENABLE_MCP_TOOLS=true          # 启用 MCP（默认：true）
AGENT_PORT=8000                # 服务器端口（默认：8000）
MAX_ITERATIONS=20              # 单个事件的最大工具调用轮数
```

---

## 故障排除

### 端口占用

```bash
# 查看端口 8000 占用情况
lsof -i :8000

# 使用不同端口
AGENT_PORT=8001 python server.py
```

### MCP 工具未加载

```bash
# 检查状态
curl http://localhost:8000/mcp/status

# 重新加载工具
curl -X POST http://localhost:8000/mcp/reload
```

### 导入错误

```bash
# 重新安装依赖
pip install -r requirements.txt
```

---

## 技术要点

- 使用统一的 LLM 客户端（`llm.client.get_llm_client()`）
- 支持多种 LLM 提供商（Kimi、SiliconFlow、豆包、DeepSeek、阿里云等）
- MCP 工具异步加载，按需执行
- 完整的事件循环演示，离线可运行
- 内置 TODO 列表管理、工具调用计数、系统状态显示
