# 协作工具 MCP 服务器

> 配套《深入理解 AI Agent》第 4 章 **实验 4-3 ★★**
>
> 为 AI Agent 提供协作能力的综合 Model Context Protocol（MCP）服务器，涵盖浏览器自动化、人机协同、通知与定时器管理。

## 功能概述

### 浏览器自动化（browser-use）
- 导航 URL、管理标签页
- 抽取网页内容
- 用 AI Agent 执行高层浏览器任务
- 截图、完整虚拟浏览器能力

### 子 Agent 管理
- 以 **sync**（等待结果）或 **async**（返回 `task_id`）模式创建子 Agent
- 向子 Agent 发送后续消息、取消运行中的子 Agent
- **两种上下文传递策略**（可检查上下文文本与 token 数）：
  - `minimal` — 只传任务 + 可选手选片段（最省、隐私好）
  - `llm_generated` — 额外一次 LLM 调用，从父轨迹合成紧凑、隐私过滤的交接上下文

### 人机协同（HITL）
- 敏感操作请求管理员审批
- 向人类管理员请求输入
- 管理待处理审批
- 可配置超时与通知渠道

### 邮件通知
- 经 SMTP 或 SendGrid 发信
- 支持 HTML、抄送与附件

### 即时通讯
- Telegram bot、Slack webhook、Discord webhook

### 定时器与调度
- 一次性/循环定时器
- 持久化存储、到期回调通知

## 快速开始

### 1. 环境准备

确保已安装 Python 3.11+，并在项目根目录配置 `.env` 文件。

### 2. 安装依赖

```bash
cd chapter4/collaboration-tools
pip install -r requirements.txt
```

### 3. 安装 Playwright 浏览器

```bash
playwright install chromium
```

### 4. 配置

在项目根目录 `.env` 文件中配置 LLM 提供商：

```bash
# LLM 配置（在项目根目录 .env 中配置）
API_KEY=your-api-key
LLM_PROVIDER=kimi
LLM_MODEL=kimi-k3
```

可选配置（在 `chapter4/collaboration-tools/.env` 中）：

```bash
# 浏览器
BROWSER_HEADLESS=false

# 邮件
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# 即时通讯
TELEGRAM_BOT_TOKEN=your-telegram-bot-token
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK

# HITL
HITL_ADMIN_EMAIL=admin@example.com
HITL_TIMEOUT_SECONDS=3600
```

## 使用方法

### 命令行入口

```bash
# 列出所有协作工具
python main.py list

# 运行端到端演示
python main.py demo

# 对比两种上下文传递策略
python main.py subagent compare

# 创建子 Agent
python main.py subagent spawn --task "查询订单 A12345 状态" --strategy minimal

# HITL 审批演示
python main.py hitl approve --message "删除 1000 条记录？" --timeout 5 --auto-approve

# 多渠道通知
python main.py notify slack --message "部署完成"
```

### 运行 MCP 服务器

```bash
python src/main.py
```

### 与 Claude Desktop 联用

在 Claude Desktop 配置中添加：

```json
{
  "mcpServers": {
    "collaboration-tools": {
      "command": "python",
      "args": ["/path/to/ai-agant/chapter4/collaboration-tools/src/main.py"],
      "env": {
        "API_KEY": "your-key-here"
      }
    }
  }
}
```

## 可用工具

### 浏览器工具
- `mcp_browser_navigate` — 导航到 URL
- `mcp_browser_get_content` — 获取页面内容
- `mcp_browser_execute_task` — 执行 AI 驱动的浏览器任务
- `mcp_browser_screenshot` — 截图
- `mcp_browser_list_tabs` — 列出标签页

### 通知工具
- `mcp_send_email` — 发送邮件
- `mcp_send_telegram_message` — Telegram 消息
- `mcp_send_slack_message` — Slack 消息
- `mcp_send_discord_message` — Discord 消息

### 子 Agent 工具
- `mcp_spawn_subagent` — 创建子 Agent（sync/async）
- `mcp_send_message_to_subagent` — 向子 Agent 发后续消息
- `mcp_cancel_subagent` — 取消子 Agent
- `mcp_get_subagent_status` — 查询状态/结果

### HITL 工具
- `mcp_request_admin_approval` — 请求管理员审批
- `mcp_request_admin_input` — 请求管理员输入
- `mcp_respond_to_request` — 响应审批请求
- `mcp_list_pending_requests` — 列出待处理请求

### 定时器工具
- `mcp_set_timer` — 一次性定时器
- `mcp_set_recurring_timer` — 循环定时器
- `mcp_cancel_timer` — 取消定时器
- `mcp_list_timers` — 列出定时器

## 使用示例

### 浏览器自动化
```python
await mcp_browser_navigate(url="https://example.com")
await mcp_browser_execute_task(task="搜索 AI Agent 教程并提取前 5 条结果")
await mcp_browser_screenshot(full_page=True)
```

### 通知
```python
await mcp_send_email(to_email="user@example.com", subject="任务完成", body="您的任务已成功完成！")
await mcp_send_slack_message(message="🎉 部署成功！")
```

### 人机协同
```python
result = await mcp_request_admin_approval(
    request_message="删除数据库中的 1000 条记录？",
    urgent=True,
    timeout_seconds=300
)
```

### 定时器
```python
await mcp_set_timer(duration_seconds=300, timer_name="检查网站", callback_message="该检查网站状态了")
await mcp_set_recurring_timer(interval_seconds=3600, max_occurrences=24, timer_name="每小时健康检查")
```

## 架构

```
collaboration-tools/
├── src/
│   ├── main.py              # MCP 服务器入口
│   ├── config.py            # 配置管理
│   ├── llm_fallback.py      # LLM 回退机制
│   ├── browser_tools.py     # 浏览器自动化
│   ├── notification_tools.py # 邮件 & IM 通知
│   ├── hitl_tools.py        # 人机协同
│   ├── timer_tools.py       # 定时器管理
│   ├── chess_tools.py       # 国际象棋
│   ├── excel_tools.py       # Excel 操作
│   ├── intelligence_tools.py # 智能处理
│   └── subagent_tools.py    # 子 Agent 管理
├── main.py                  # CLI 入口
├── requirements.txt         # 依赖清单
├── results/                 # 结果输出目录
└── logs/                    # 日志目录
```

## 故障排除

### 浏览器问题
```bash
playwright install chromium --force
```

### 邮件问题
- Gmail 请使用 [应用专用密码](https://support.google.com/accounts/answer/185833)

### Telegram 问题
- 通过 [@BotFather](https://t.me/botfather) 创建 bot
- 用 [@userinfobot](https://t.me/userinfobot) 获取 chat ID

### LangChain/Pydantic 问题
- ChatOpenAI 仅在需要时按需初始化
- 简单导航不需要 LLM 密钥
- 仅自主浏览器任务需要 LLM 密钥

## 依赖要求

- Python 3.11+
- LLM API 密钥（在项目根目录 `.env` 中配置）
- 可选：邮件/IM 凭据
- Playwright 浏览器（浏览器自动化）

## 许可证

MIT License
