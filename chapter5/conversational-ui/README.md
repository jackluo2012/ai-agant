# 对话式界面定制系统

> 实验 5-11：用户用自然语言提出 UI 定制需求，Agent 自主修改前端源码，Vite HMR 让改动即时生效。

← [返回第 5 章目录](../)

---

## 功能概述

本实验展示了一个**对话式 UI 定制系统**，用户可以用自然语言描述界面定制需求，Agent 自动定位并修改前端源码：

- **定制范围**：颜色、字体、文案、布局、组件位置
- **工作流程**：自然语言需求 → Agent 改写 React 源码 → 热加载即时生效
- **支持多轮迭代**：可持续对话，逐步完善界面

## 系统架构

系统由四部分组成：

```
chapter5/conversational-ui/
├── frontend/                 # React + Vite 前端（被定制的对象）
│   ├── src/App.jsx           # 界面与文案（Agent 改"文案/组件"）
│   ├── src/theme.css         # 颜色/字体/布局（Agent 改"样式"）
│   ├── src/main.jsx
│   ├── index.html
│   ├── vite.config.js        # HMR + /api 代理到后端
│   └── package.json
├── backend/
│   ├── main.py               # FastAPI 后端（/api/chat）
│   └── requirements.txt
├── baseline/src/             # 前端源码初始快照
├── agent.py                  # 定制 Agent：NL → 改写源码
├── demo.py                   # 端到端演示 + 自动验证
├── requirements.txt          # 实验特定依赖
├── results/                  # 结果输出目录
└── logs/                     # 日志目录
```

### 核心组件

1. **`agent.py`** - 定制 Agent
   - 接收自然语言需求
   - 使用 LLM 定位并改写源码
   - 只修改白名单文件（`src/App.jsx`、`src/theme.css`）

2. **`frontend/`** - React + Vite 前端
   - 基础 chatbot 界面
   - 开发模式下 Vite HMR 让改动即时可见

3. **`backend/`** - FastAPI 后端
   - 提供 `/api/chat` 对话接口
   - 默认回声模式，可选真实 LLM 对话

4. **`demo.py`** - 自动验证脚本
   - 运行多轮定制
   - 验证改动正确应用
   - 确认构建不破坏

## 快速开始

### 1. 环境准备

确保已安装：
- Python 3.8+
- Node.js 16+
- npm

### 2. 配置 LLM

在**项目根目录**的 `.env` 文件中配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3   # 可选
BASE_URL=...        # 如需要
```

支持的 LLM 提供商：Kimi、OpenAI、DeepSeek、Anthropic、阿里云等。

### 3. 安装依赖

```bash
# 安装 Python 依赖
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
pip install -r chapter5/conversational-ui/requirements.txt

# 安装前端依赖
cd chapter5/conversational-ui/frontend
npm install
```

### 4. 运行演示

#### 自动验证（无需浏览器）

```bash
cd chapter5/conversational-ui

# 跑全部 3 轮定制并做完整验证
python demo.py

# 只跑第 1 轮（快速冒烟）
python demo.py --quick

# 只跑前 2 轮
python demo.py --rounds 2

# 跳过 vite build（仅验证改动应用）
python demo.py --no-build
```

#### 手动体验 HMR（需要浏览器）

```bash
# 终端 A：启动后端
cd chapter5/conversational-ui/backend
python main.py --reload --port 8000

# 终端 B：启动前端（HMR）
cd chapter5/conversational-ui/frontend
npm run dev
# 打开 http://localhost:5173

# 终端 C：执行定制
cd chapter5/conversational-ui
python -c "import agent,pathlib; c,m=agent.build_client_and_model(); r=agent.customize(c,m,pathlib.Path('frontend'),'把发送按钮改成橙色'); [pathlib.Path('frontend',f['path']).write_text(f['content']) for f in r['files']]"
```

## 使用方法

### Agent 定制

```python
import agent
from pathlib import Path

# 获取客户端
client, model = agent.build_client_and_model()

# 执行定制
result = agent.customize(
    client, model,
    Path("frontend"),
    "把发送按钮改成蓝色"
)

# 应用改动
for f in result["files"]:
    (Path("frontend") / f["path"]).write_text(f["content"])
```

### 后端 API

启动后端后：

```bash
# 默认回声模式
curl http://localhost:8000/api/chat -X POST -H "Content-Type: application/json" -d '{"message":"你好"}'

# LLM 模式（需要配置 LLM）
CHAT_MODEL=kimi-k3 python backend/main.py
```

### 后端命令行参数

| 参数 | 说明 | 默认 |
| --- | --- | --- |
| `--host` | 监听地址 | `127.0.0.1` |
| `--port` | 监听端口 | `8000` |
| `--reload` / `--no-reload` | 后端热加载 | 开启 |
| `--model NAME` | LLM 模型名 | 无（echo 模式） |
| `--log-level` | 日志级别 | `info` |
| `--print-config` | 打印配置后退出 | 关 |

## 验证示例

```
第 1 轮 NL 定制需求：把发送按钮和用户消息气泡的主题色从绿色改成蓝色，用 #2563eb 这个蓝。
[改动文件] src/theme.css
  - --color-primary: #16a34a;   /* 初始为绿色 */
  + --color-primary: #2563eb;   /* 改为蓝色 */
断言：源码中出现蓝色值 #2563eb -> 通过 ✅
构建结果：通过 ✅

第 2 轮 NL 定制需求：把整个界面的字体换成等宽字体（monospace）。
[改动文件] src/theme.css
  - --font-family: system-ui, "PingFang SC", ... sans-serif;
  + --font-family: monospace;
断言：源码中出现 monospace 等宽字体 -> 通过 ✅
构建结果：通过 ✅

第 3 轮 NL 定制需求：把顶部的标题文案改成"我的专属客服"。
[改动文件] src/App.jsx
  - const HEADER_TITLE = "智能助手";
  + const HEADER_TITLE = "我的专属客服";
断言：源码中出现新标题文案"我的专属客服" -> 通过 ✅
构建结果：通过 ✅

多轮定制总结：全部通过 ✅
```

## 扩展指南

### 修改可定制文件

编辑 `agent.py` 中的 `EDITABLE_FILES`：

```python
EDITABLE_FILES = [
    "src/App.jsx",
    "src/theme.css",
    "src/YourCustomFile.jsx",  # 添加新文件
]
```

### 添加验证轮次

编辑 `demo.py` 中的 `ROUNDS`：

```python
ROUNDS = [
    {
        "requirement": "你的定制需求",
        "verify": lambda s: (
            "期望的内容" in _all_text(s),
            "断言描述",
        ),
    },
]
```

### 替换前端界面

1. 替换 `frontend/src/*` 文件
2. 更新 `baseline/src/` 快照
3. 更新 `agent.py` 中的白名单

## 故障排除

### LLM 调用失败

- 检查项目根目录 `.env` 中的 LLM 配置
- 确认 API_KEY 有效
- 检查网络连接

### 前端构建失败

```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### 后端启动失败

```bash
# 检查端口占用
lsof -i :8000

# 使用其他端口
python backend/main.py --port 8001
```

## 技术要点

1. **白名单机制**：只允许修改特定文件，降低改错风险
2. **整文件重写**：对小文件比零散替换更稳定
3. **自动验证**：每轮改动后断言 + 构建验证
4. **热加载**：前端 Vite HMR + 后端 uvicorn --reload
5. **统一 LLM 配置**：使用项目根目录 `.env`，避免重复配置
