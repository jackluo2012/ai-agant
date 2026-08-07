# 主动工具发现

配套《深入理解 AI Agent》第 4 章实验：主动工具发现。在 126 个跨领域工具上对比全量注入、检索预筛选与主动发现三种策略。

## 功能概述

当 Agent 拥有数百个工具时，常见做法是将每个工具的 JSON schema 注入到 system prompt 中。这会产生两个问题：

1. **Token 浪费**：126 个工具的完整 schema 约 **11.6k tokens**，每次推理步骤都会重新计费
2. **指令遵循退化**：在略微模糊的任务上，模型会"广撒网"，同时调用通用兜底工具（`web_search`/`google_search`/`universal_search`）和专用工具，甚至用通用搜索替代专用工具（例如通过通用 `web_search` 查询股价）

**主动发现**只在 system prompt 中保留少量基础工具和一个 `discover_tools(need)` 元工具。当模型遇到能力缺口时，用自然语言描述需求；系统通过嵌入相似度检索 3-5 个最相关的专用工具，将其 schema 作为 **user message** 追加到对话中（保护 system 前缀 KV cache），并更新可用工具的状态栏。

### 三种策略对比

- **全量注入（full_injection）**：对照组，126 个工具 schema 一次性注入上下文
- **检索预筛选（retrieval_prefilter）**：按初始查询做一次性语义检索，只注入 top-n 候选工具
- **主动发现（active_discovery）**：少量基础工具 + discover_tools 元工具，执行中按需检索加载

### 为什么用"文本注入 + 文本解析"而非原生 function calling？

OpenAI 原生 function-calling 对工具选择做了很强的约束/优化，即使上百个工具也很少选错，无法体现长上下文下的指令遵循退化。将 schema 当作纯文本塞入 prompt、让模型以 JSON 形式输出工具调用，才是书中控制组的真实机制。

## 快速开始

### 1. 环境准备

确保已安装项目根目录的核心依赖：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r chapter4/active-tool-discovery/requirements.txt
```

### 3. 配置 LLM

在项目根目录的 `.env` 文件中配置 LLM（**注意**：不是在本项目目录内配置）：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=openai  # 或 kimi、siliconflow、doubao 等
LLM_MODEL=gpt-4o     # 或其他模型
```

### 4. 运行实验

#### 离线机制自检（无需 API key）

```bash
cd chapter4/active-tool-discovery
python demo.py --offline
```

离线模式使用本地哈希嵌入 + 脚本化 mock 模型，token/延迟为真实测量，准确率仅反映启发式路由。

#### 真实模型运行

```bash
# 运行全部任务和三种策略
python demo.py

# 仅对比两种策略
python demo.py --strategies full,discovery

# 选择特定任务
python demo.py --tasks finance+news,crypto+news

# 临时单任务
python demo.py --query '查英伟达股价再搜点相关新闻' --offline

# 导出结构化结果
python demo.py --offline --output results/offline.json
```

## 使用方法

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--query TEXT` | 临时单任务：直接给自然语言需求 |
| `--tasks IDS` | 逗号分隔的内置任务 id |
| `--strategies LIST` | 逗号分隔的策略（full/prefilter/discovery） |
| `--tool-set-size N` | 截取工具库为 N 个工具 |
| `--top-k K` | 主动发现每次返回的候选工具数（默认 4） |
| `--prefilter-n N` | 检索预筛选注入的候选工具数（默认 10） |
| `--model NAME` | 对话模型名（从项目根目录 .env 读取） |
| `--embed-model NAME` | 嵌入模型名 |
| `--max-steps N` | 单任务 ReAct 最大步数（默认 10） |
| `--offline` | 离线机制自检模式 |
| `--output PATH` | 输出结构化结果到 JSON 文件 |

### 内置任务

实验包含 8 个跨领域任务，每个任务需要多个专用工具协作：

- `finance+news`：查询股价 + 相关新闻
- `arxiv+download`：检索论文 + 下载文件
- `github+viz`：获取贡献者 + 渲染图表
- `weather+calendar`：天气预报 + 创建日程
- `forex+weather`：汇率查询 + 天气
- `crypto+news`：加密货币价格 + 新闻
- `opinion(诱导)`：通用工具诱导任务
- `academic(诱导)`：学术检索诱导任务

## 项目结构

```
active-tool-discovery/
├── agent.py           # 三种 ReAct 策略实现
├── demo.py            # 主入口：运行对比实验
├── discovery.py       # 工具向量索引 + 相似度检索
├── offline_backend.py # 离线后端：本地嵌入 + mock 模型
├── tools_library.py   # 126 个工具定义 + 评测任务
├── requirements.txt   # 项目特定依赖
├── results/           # 结果输出目录
└── logs/              # 日志目录
```

## 技术要点

### 工具库设计

- **126 个跨领域工具**：覆盖 finance/news/web/arxiv/github/geo/weather/media 等 17 个领域
- **真实 OpenAI function schema**：每个工具都有真实的 name/description/parameters
- **诱导型通用工具**：故意混入 8 个通用/近义工具（web_search、universal_search 等），在全量注入时会与专用工具竞争
- **Mock 执行**：工具执行只做轻量 mock，关注点在"能否选对工具"

### 嵌入检索

- **OpenAIEmbedder**：调用 OpenAI embeddings API（默认 text-embedding-3-small）
- **本地缓存**：工具向量缓存到 `.cache/tool_embeddings_*.json`
- **相似度计算**：余弦相似度返回 top-k 候选工具

### 为什么检索能减少错误选择？

通用工具如 `web_search` 声称"什么都能做"，语义被稀释；专用工具（如 `search_news`）描述专注。对于聚焦的 `need`（"特斯拉最近新闻"），专用工具得分更高排在前面；通用工具往往进不了 top-k，永远不会被加载——检索起到了精度过滤作用。

### 为什么检索预筛选还不够？

预筛选只按**初始查询**做一次匹配，在多步骤跨领域任务中，初始向量往往偏向第一个领域；第二个子任务的专用工具可能没进 top-n。主动发现将发现推迟到每个真实 `need` 出现时分别检索（离线自检显示预筛选在一半多步骤任务中漏掉第二个工具）。

## 离线机制自检结果

一次真实的 `--offline` 运行（8 任务 × 三种策略）：

| 策略 | 精确选对 | 任务完成 | 平均注入 tokens | 总注入 tokens | 平均延迟(s) |
|------|----------|----------|-----------------|---------------|-------------|
| 全量注入 | 8/8 | 8/8 | 11630 | 93040 | 0.008 |
| 检索预筛选 | 4/8 | 4/8 | 1030 | 8236 | 0.006 |
| 主动发现 | 8/8 | 8/8 | 974 | 7796 | 0.010 |

两个真实可复现的结构性结论：

1. **Token 差距随工具集规模扩大**：全量注入固定 11,630 tokens/任务；预筛选和发现约 1,000 tokens（**约 11.9 倍**差距）
2. **预筛选在多步骤任务中结构性漏工具**：一次性 top-10 在 4/8 任务中漏掉第二个专用工具；主动发现按需检索，全部命中

## 故障排除

### ImportError: 无法导入 llm.client

确保项目根目录存在 `.env` 文件并配置了 LLM。

### 离线模式报错

离线模式不需要任何 API key，如果报错请检查依赖是否正确安装。

### 嵌入向量缓存问题

首次运行会生成嵌入向量并缓存，如果更换嵌入模型会自动重建缓存。

## 扩展与定制

- **更换对话模型**：在项目根目录 `.env` 中修改 `LLM_MODEL`
- **更换嵌入模型**：使用 `--embed-model` 参数
- **自定义任务**：编辑 `tools_library.py` 中的 `TASKS`
- **调整工具集**：使用 `--tool-set-size` 参数或编辑 `ALL_TOOLS`
