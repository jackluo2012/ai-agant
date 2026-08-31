# 实验 10-5：斯坦福 Generative Agents 复现（Generative Agents）

本项目对官方 `joonspk-research/generative_agents` 源码（固定 commit
`fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4`）运行完整的 Agent 社会实验。
它保留上游的 25 人物 Smallville 环境与十秒世界步长，并通过运行时适配器把
上游遗留的 GPT-3 API 调用面重定向到当前 OpenAI 兼容端点，**上游源码本身
零修改**。LLM 配置统一来自项目根目录的 `.env` 文件，本目录内不存放任何密钥。

实验设计为三个等长实验臂（各 17,280 步，即两个虚拟日），全部从同一个加载
了历史种子的第 0 步分叉，以控制上游 `agent_history_init_n25.csv` 中 248 条
关系记忆及其生成的思考/事件三元组/诗意评分/向量表示：

- `baseline`：原始的 Isabella Rodriguez 情人节派对与 Sam Moore 市长选举种子；
- `custom_goal`：同一历史种子，仅把 Isabella 的初始派对目标替换为同地点同
  时段的社区气候韧性工作坊；
- `no_reflection`：基线目标 + 禁用 `Persona.reflect()` 并防御性调高重要性
  触发阈值，保留感知、检索、规划、执行与对话记忆，但阻止新的反思思考。

> 迁移说明：本项目自 `ai-agent-book/chapter10/generative-agents` 迁移而来，
> LLM 配置改为读取项目根目录 `ai-agant/.env`，适配器改为在共享虚拟环境
> （openai >= 1.0）上注入兼容 shim，评审器改用统一封装客户端。
> 上一轮已验收的保留证据包（含验收报告与分析产物）保留在源仓库的
> `validation/runs/` 目录中，未随本迁移复制。

## 功能概述

- **零修改上游**：固定 commit 的官方源码按原样运行；所有兼容性修正都通过
  导入遮蔽（`compat/utils.py`）与运行时包装完成。
- **统一 LLM 配置**：对话/向量模型、凭据与端点全部来自项目根目录 `.env`，
  经 `llm.client.get_llm_client()` 封装获取。
- **旧接口兼容 shim**：在现代 SDK 上注入 `openai.ChatCompletion` /
  `Completion` / `Embedding` 同名入口，上游的 0.27 风格调用原样工作。
- **无凭据调用回执**：每次逻辑调用保留完整请求/响应、提供商响应 ID、
  token 用量、时延与传输层重试；凭据永不序列化，向量只留维度与内容哈希。
- **断点续跑**：每 360 步（一个虚拟小时）持久化一次；状态文件只有在模拟
  状态与压缩回执都落盘后才原子更新；重启后从最近 checkpoint 恢复。
- **隔离机制**：含提供商错误的 checkpoint 连同其兼容性回执一起被移入
  `.failed-*` 隔离区，从最近干净 checkpoint 重放，绝不混入规范证据。
- **有界兼容修正**：任务分解解析清洗、合法 0 分保留、行动场所归一化，全部
  带修正回执且取值范围有界（场所永远不出可达列表）。
- **臂序盲评**：评审模型只拿无标签的 A/B 轨迹，按人物名哈希决定臂序。

## 快速开始

### 1. 环境准备

- Python 3.10+，项目根目录虚拟环境 `.venv/` 已就绪
- 克隆并固定上游官方源码：

```bash
git clone https://github.com/joonspk-research/generative_agents.git /tmp/generative_agents
git -C /tmp/generative_agents checkout --detach fe05a71d3e4ed7d10bf68aa4eda6dd995ec070f4
```

### 2. 安装依赖

核心依赖（openai、python-dotenv）由项目根目录统一提供；科学计算栈已预装。
如需补齐项目依赖：

```bash
pip install -r chapter10/generative-agents/requirements.txt
```

### 3. 配置说明（项目根目录 .env）

LLM 配置统一读取项目根目录 `ai-agant/.env`，请确认其中已配置：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi        # 或 openai / deepseek / anthropic / aliyun / custom 等
LLM_MODEL=kimi-k3        # 对话模型；未填则使用提供商默认模型
BASE_URL=                # 仅 aliyun / custom 提供商需要
```

实验特定配置（章节前缀环境变量，可选）：

```bash
CHAPTER10_CHAT_MODEL=qwen3.7-flash          # 覆盖对话模型（默认取 LLM_MODEL）
CHAPTER10_EMBEDDING_MODEL=text-embedding-v4 # 覆盖向量模型（aliyun/custom 默认 text-embedding-v4）
CHAPTER10_PROVIDER_TIMEOUT_SECONDS=90       # 单次物理请求超时（默认 90 秒）
```

注意：本实验需要可用的**对话模型**与**文本向量模型**端点；本目录内不会
创建任何 `.env` 文件，也不会序列化任何凭据。

### 4. 运行方法

```bash
# 在项目根目录 ai-agant 下运行
source .venv/bin/activate

# 第一步：准备共享历史种子（只需执行一次）
python3 chapter10/generative-agents/run_campaign.py \
  --upstream /tmp/generative_agents \
  --output outputs/exp10-5 \
  --mode seed
```

启动或恢复全部三个实验臂（分离进程）：

```bash
python3 chapter10/generative-agents/launch_campaigns.py \
  --upstream /tmp/generative_agents \
  --output outputs/exp10-5
```

或使用监督器（自动恢复 + 实时错误提前终止）：

```bash
python3 chapter10/generative-agents/start_supervisor.py \
  --upstream /tmp/generative_agents \
  --output outputs/exp10-5
```

## 使用方法

完整工作流按顺序执行（均在项目根目录下运行）：

```bash
OUT=outputs/exp10-5
SRC=chapter10/generative-agents

# 1) 准备种子 + 2) 启动实验臂（见上文）

# 3) 只读监视进度（不读取凭据）
python3 $SRC/monitor_campaign.py $OUT

# 4) 臂序盲评合理性评审（25 位人物）
python3 $SRC/judge_plausibility.py $OUT

# 5) 确定性分析：记忆、反思、扩散与动作日志
python3 $SRC/analyze_campaign.py $OUT

# 6) 打包保留证据（三个实验臂必须全部完成）
python3 $SRC/package_evidence.py $OUT validation/runs/<run-id> \
  --upstream /tmp/generative_agents

# 7) 独立验收（14 道验收门，全过则输出 passed: true）
python3 $SRC/validate_campaign.py validation/runs/<run-id>
```

运行离线单元测试：

```bash
python3 -m pytest chapter10/generative-agents/tests
```

## 项目结构

```
chapter10/generative-agents/
├── README.md                  # 本文档
├── requirements.txt           # 项目特定依赖（核心依赖由根目录提供）
├── experiment_protocol.json   # 预注册实验协议
├── provider_adapter.py        # LLM 适配器：旧接口 shim + 统一客户端 + 调用回执
├── compat/
│   └── utils.py               # 上游 utils.py 遮蔽层（凭据从统一 .env 读取）
├── run_campaign.py            # 运行器：种子准备 + 实验臂断点续跑
├── launch_campaigns.py        # 分离进程启动器
├── start_supervisor.py        # 监督器启动入口
├── supervise_campaigns.py     # 监督循环：自动恢复 + 实时错误终止
├── monitor_campaign.py        # 只读进度监视
├── judge_plausibility.py      # 臂序盲评合理性评审
├── analyze_campaign.py        # 确定性分析
├── package_evidence.py        # 证据打包（manifest + 哈希）
├── validate_campaign.py       # 独立验收（14 道验收门）
├── action_arena_compat.py     # 行动场所归一化兼容层
├── tests/                     # 离线单元测试
├── results/                   # 结果输出目录
└── logs/                      # 日志目录
```

生成的实验数据属于 `outputs/`（已被 `.gitignore` 忽略）；只有完成并通过
验收的证据包才会被有意选入 `validation/runs/` 保留。

## 配置说明

### 统一 LLM 配置（项目根目录 .env）

| 环境变量 | 说明 | 默认 |
| --- | --- | --- |
| `API_KEY` | 通用 API 密钥（必填） | 无 |
| `LLM_PROVIDER` | 提供商（kimi/openai/deepseek/anthropic/aliyun/custom） | `kimi` |
| `LLM_MODEL` | 对话模型名 | 提供商默认 |
| `BASE_URL` | API 基础 URL（aliyun/custom 必填） | 无 |

### 实验特定配置（章节前缀，可选）

| 环境变量 | 说明 | 默认 |
| --- | --- | --- |
| `CHAPTER10_CHAT_MODEL` | 覆盖对话模型 | `LLM_MODEL` |
| `CHAPTER10_EMBEDDING_MODEL` | 覆盖向量模型 | aliyun/custom: `text-embedding-v4`；其他提供商必须显式指定 |
| `CHAPTER10_PROVIDER_TIMEOUT_SECONDS` | 单次物理请求超时（秒） | `90` |

## 故障排除

- **提示"上游仓库必须固定在 …"**：上游 checkout 的 commit 与预注册值不符，
  重新执行 `git -C /tmp/generative_agents checkout --detach <commit>`。
- **提示"启动实验臂之前请先准备共享历史种子"**：先运行 `--mode seed`。
- **提示"未指定文本向量模型"**：当前提供商无法推断向量模型，设置
  `CHAPTER10_EMBEDDING_MODEL` 后重试。
- **提示"API 密钥未设置"**：在项目根目录 `ai-agant/.env` 中配置 `API_KEY`。
- **checkpoint 被隔离为 `.failed-*`**：该次尝试的回执中存在失败的提供商
  调用；运行器会自动从最近干净 checkpoint 重放。只有修复端点可用性后
  重跑才会推进，隔离文件作为证据保留、不计入规范统计。
- **`import utils` 命中上游文件**：确保通过 `run_campaign.py` 入口运行；
  它会把 `compat/` 插入到导入路径中上游后端之前。

## 技术要点

- **为什么保留英文种子内容**：`CUSTOM_CURRENTLY` 替换目标、分析关键词与
  验收门字符串是绑定英文 Smallville 上游环境的实验数据（人物、地点、时间
  均为上游事实），与分析与验收逻辑三方一致；将其翻译会改变实验本身。
  除此之外的提示词（评审）、注释、CLI 帮助与文档均已中文化。
- **旧接口兼容原理**：上游按 `openai.ChatCompletion.create(...)` 等属性
  访问旧入口；现代 SDK 的模块对象允许注入同名属性，因此 shim 可在运行时
  挂载，上游代码零修改。补全入口映射为对话接口并模拟 0.27 的文本响应形态。
- **重试与隔离的边界**：传输层瞬态错误（连接、超时、限流、服务不可用）在
  同一逻辑调用内有界指数退避重试（最多 5 次），成功回执记录每次失败尝试；
  逻辑错误或重试耗尽保持 `success: false`，含错误的 checkpoint 被隔离重放。
- **验收与配置解耦**：验收门中的模型名从证据包 `environment.json` 读取，
  而非硬编码，因此更换实验模型不需要修改验收逻辑。
- **证据链完整性**：manifest 记录每个文件的字节数与 SHA-256；验收对全部
  文件做凭据字节扫描，任何疑似密钥都会导致 `credential_scan_clean` 门失败。
