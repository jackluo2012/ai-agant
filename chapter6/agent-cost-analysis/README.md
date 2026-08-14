# Agent 任务端到端成本分析

配套《深入理解 AI Agent》第 6 章「实验 6-7 ★：Agent 任务的端到端成本分析」。

## 功能概述

本项目对一个典型的多轮 Agent 任务（客服退款）做**全链路成本拆解**，用**自建的轻量 tracing / 可观测系统**记录每次 LLM 调用的输入/输出/缓存 token、时延与成本。

主要功能：
- 按步骤聚合出「哪一步最贵」
- 按**成本构成**拆解「未缓存输入 / 缓存输入 / 输出各占多少」
- 分析「工具返回注入」占用了多少 token
- 给出**单步成本分布**（p50/p95/p99）
- 完整 **2×2 A/B 对比**，量化 **KV-cache 复用** 与 **上下文压缩** 两个优化杠杆的真实成本差异

## 快速开始

### 1. 环境准备

确保项目根目录的 `.venv` 虚拟环境已创建并激活：

```bash
# 在项目根目录（ai-agant/）
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate     # Windows
```

### 2. 安装依赖

```bash
cd chapter6/agent-cost-analysis
pip install -r requirements.txt
```

### 3. 配置 LLM

在**项目根目录**的 `.env` 文件中配置 LLM 提供商：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3   # 可选，默认使用提供商推荐模型
```

支持的 LLM 提供商：
- **Kimi** (`kimi`): kimi-k3
- **SiliconFlow** (`siliconflow`): Qwen/Qwen2.5-7B-Instruct
- **DeepSeek** (`deepseek`): deepseek-chat
- **阿里云** (`aliyun`): qwen-plus（需要额外配置 BASE_URL）
- **OpenAI** (`openai`): gpt-4o-mini

### 4. 运行

**在线模式**（真实调用模型，需要 LLM 配置）：

```bash
# 默认跑 A(朴素)+B(优化) 两组
python demo.py

# 跑完整 2×2 四组
python demo.py --scenario all
```

**离线模式**（无需 LLM 配置）：

```bash
# 用内置 sample_trace.json 复算全部表格
python demo.py --offline --scenario all

# 换模型单价重算
python demo.py --offline --model gpt-4o
```

## 使用方法

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--live` / `--offline` | 在线真实调用（默认）/ 离线从 trace 文件复算 |
| `--scenario NAME` | `ab`(默认=naive+both) / `all`(2×2 四组) / 逗号分隔子集 |
| `--trace FILE` | 离线读取的 trace 文件，默认 `sample_trace.json` |
| `--save-trace FILE` | 在线跑时保存真实 token 用量到 trace 文件 |
| `--model NAME` | 模型名（决定默认单价预设） |
| `--price-input/-cached/-output` | 覆盖三档单价（每百万 token 美元） |
| `--no-warmup` | 关闭 KV-cache 组的前缀预热 |
| `--output FILE` | 导出完整结果 JSON |

### A/B 四种策略（完整 2×2）

同一个 8 轮客服退款任务，四组做的是**同样的逻辑工作**，只在上下文构造上不同：

| 场景 | KV-cache | 压缩 | 上下文构造 |
|------|:--:|:--:|------|
| `naive` A 朴素 | ✗ | ✗ | 随机 session 头 + 历史工具返回原样带全 |
| `kv` 仅缓存 | ✓ | ✗ | 稳定长前缀 + 历史不压缩 |
| `compress` 仅压缩 | ✗ | ✓ | 前缀不稳定 + 仅最近 2 轮完整，更早压成摘要 |
| `both` B 优化 | ✓ | ✓ | 稳定前缀 + 上下文压缩（两个杠杆叠加） |

### 项目结构

```
chapter6/agent-cost-analysis/
├── README.md              # 本文档
├── requirements.txt       # 项目依赖（tiktoken）
├── env.example           # LLM 配置示例
├── config.py             # 模型与价格配置
├── tracer.py             # 自建轻量 tracing 系统
├── agent.py              # 多轮客服退款 Agent
├── demo.py               # 命令行入口
├── sample_trace.json     # 内置离线 trace 文件
├── results/              # 结果输出目录
├── logs/                 # 日志目录
└── tests/                # 离线回归测试
```

## 运行示例

### 在线模式

```bash
# 激活虚拟环境后
cd chapter6/agent-cost-analysis

# 运行 A/B 对比
python demo.py

# 运行完整 2×2 对比
python demo.py --scenario all

# 保存 trace 供离线复用
python demo.py --save-trace my_trace.json
```

### 离线模式

```bash
# 使用内置 trace
python demo.py --offline

# 换单价重算
python demo.py --offline --model gpt-4o

# 自定义单价
python demo.py --offline --price-input 0.20 --price-cached 0.10 --price-output 0.80
```

### 测试

```bash
# 运行离线测试（无需 API key）
python -m pytest tests/
```

## 输出示例

### 成本拆解

```
===== 成本拆解: A 朴素(无缓存/无压缩)（单次任务全链路拆解） =====
步骤       工具/动作                   输入tok    缓存tok    工具tok    输出tok    时延(s)        成本($)
---------------------------------------------------------------------------------------
turn-1   query_order              1113        0      276      104     3.15     0.000229
turn-2   query_logistics          1807        0      829       99     2.09     0.000330
...
```

### A/B 对比

```
===== A/B 成本对比（同一个 8 轮客服退款任务）=====
方案                             总输入tok      缓存tok      缓存率    输出tok       总成本($)       vs基线
------------------------------------------------------------------------------------------
A 朴素(无缓存/无压缩)                   20700          0     0.0%     1118     0.003776         基线
B 优化(KV缓存+压缩)                   16035       6144    38.3%     1164     0.002643     -30.0%
```

## 技术要点

### KV-cache 节省原理

- 利用 OpenAI 的**自动 prompt caching**：当请求前缀 ≥ 1024 token 且与近期请求命中相同前缀时，`usage.prompt_tokens_details.cached_tokens > 0`
- 这部分输入 token 按**缓存价**（通常为输入价的 50%）计费

### 上下文压缩策略

- 仅最近 `KEEP_VERBOSE`（默认 2）轮保留完整工具返回
- 更早轮次压成一句话摘要，显著降低输入 token 增长

### 工具返回注入成本

- 每次工具调用返回结果注入上下文
- 同一份工具返回在后续每轮被**反复计费**
- 本项目用 tiktoken 估算这部分 token 数量

## 故障排除

### LLM 客户端初始化失败

**错误信息**：`LLM 客户端初始化失败`

**解决方法**：
1. 检查项目根目录 `.env` 文件是否存在
2. 确认 `API_KEY`、`LLM_PROVIDER` 已正确配置
3. 某些提供商（如阿里云）需要额外配置 `BASE_URL`

### 离线模式找不到 trace 文件

**错误信息**：`找不到 trace 文件`

**解决方法**：
- 确认 `sample_trace.json` 文件存在
- 或使用 `--trace` 参数指定正确的 trace 文件路径

### 导入错误

**错误信息**：`No module named 'llm.client'`

**解决方法**：
- 确保从项目根目录运行（或已设置 PYTHONPATH）
- 确认虚拟环境已激活

## 成本分析结论

基于真实运行数据（gpt-4o-mini）：

- **仅 KV-cache**：缓存率冲到 66.6%，端到端成本降 **28.3%**
- **仅压缩**：总输入 token 降约 22%，端到端成本降 **17.5%**
- **两者叠加（B 优化）**：端到端总成本降 **30.0%**（A 是 B 的 1.43 倍）

**注意**：KV 与压缩并非简单相加。压缩缩短了历史，可被缓存的「历史轮次」也随之变少，需要实测协同效应。

## 注意事项

1. **具体数字每次在线运行会有小幅波动**：prompt cache 是尽力而为的（按约 128 token 的块缓存、约 5–10 分钟过期）
2. **预热机制**：正式计量前会先对 KV-cache 组跑一次「预热」把稳定前缀写入缓存，让命中更稳定
3. **凭据配置**：所有 LLM 凭据统一在项目根目录 `.env` 配置，本项目不再单独管理 API Key
