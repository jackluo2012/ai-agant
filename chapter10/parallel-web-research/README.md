# 实验 10-4：真实浏览器会话的并行研究（Parallel Web Research）

本实现不使用任何模拟数据源、预置内容或人为延迟。管理者（Manager）针对每个真实大学 URL 动态启动一个同构 Worker；每个 Worker 拥有独立的 Playwright Chromium 浏览器上下文，访问真实网页、读取渲染后的文本，再由真实配置的 LLM 端点做证据约束的教师信息抽取。LLM 配置统一来自项目根目录的 `.env` 文件，本目录内不存放任何密钥。

## 功能概述

- 动态 N 路并发：为目标 URL、教师姓名与路由任务 ID 动态启动同构 Worker。
- 基于带时间戳的异步消息总线推送状态更新（进程内发布/订阅，无需部署 Redis）。
- 单站超时/错误隔离：某个站点不可访问或结构异常不会影响同伴 Worker。
- 首个 `target_found` 在 `asyncio.Lock` 保护下结算：只允许一次终止广播，迟到命中被记录为重复。
- 导航与 LLM 抽取均与终止事件赛跑：落败的 Worker 在安全点取消、回执确认并关闭浏览器上下文。
- 浏览器上下文创建/关闭计数器：让"泄漏的浏览器会话"成为明确的验收失败项。
- 串行与并行路径访问同一批真实站点、使用同一抽取函数：实测（而非估算）墙钟时间与加速比。

## 快速开始

### 1. 环境准备

- Python 3.10+
- 项目根目录虚拟环境 `.venv/` 已就绪
- 安装 Chromium 浏览器内核：

```bash
playwright install chromium
```

### 2. 安装依赖

核心依赖（openai、python-dotenv）由项目根目录统一提供；本实验的额外依赖：

```bash
pip install -r chapter10/parallel-web-research/requirements.txt
```

### 3. 配置说明（项目根目录 .env）

LLM 配置统一读取项目根目录 ai-agant/.env，请确认其中已配置：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi        # 或 openai / deepseek / anthropic / aliyun / custom 等
LLM_MODEL=kimi-k3        # 可选，未填则使用提供商默认模型
BASE_URL=                # 仅 aliyun / custom 提供商需要
```

注意：真实网页抽取需要可用的文本模型端点；本实验不会创建本目录内的 `.env` 文件。

### 4. 运行方法

```bash
# 在项目根目录 ai-agant 下运行
source .venv/bin/activate

# 默认演示：10 个斯坦福真实页面 + 真实串行基线对比
python3 chapter10/parallel-web-research/demo.py

# 指定目标教师、站点列表与并发数
python3 chapter10/parallel-web-research/demo.py --target "吴恩达" --sites-json chapter10/parallel-web-research/sites.example.json --agents 3

# 跳过串行基线 / 显示浏览器窗口 / 静默总线日志
python3 chapter10/parallel-web-research/demo.py --no-compare
python3 chapter10/parallel-web-research/demo.py --headed
python3 chapter10/parallel-web-research/demo.py --quiet
```

溯源完备的官方验收战役（默认对比 + 四 Worker 实时级联压测，一次运行完成）：

```bash
python3 chapter10/parallel-web-research/run_official_experiment.py --run-id exp10-4-real-receipts-YYYYMMDD-vN
```

该运行器会留存：完整渲染后的浏览器观测、无密钥的原始 SDK 请求/响应（含提供商响应 ID 与用量）、消息总线事件流、运行时源码哈希、产物哈希与验收门禁结果。

`sites.example.json` 是一个三站点的用户自备列表示例；`cascade-stress.example.json` 用四个不同的查询 URL 重复访问同一个真实目标档案页，专门用于让"近乎同时的真实命中与级联取消"可被观察——它是真实浏览器的压测补充，不是多学校研究数据集。

## 使用方法

### 代码阅读路径

- **先运行**：`demo.py --target "教师姓名" --sites-json sites.example.json --agents 3`
- **从这里入手**：`agents.py` 的 `search_one`，以及 `run_official_experiment.py` 中管理者的运行路径
- **核心行为**：Worker 导航/抽取、异步消息总线、首目标结算与取消
- **状态/协议**：任务 ID、status/result/terminate 事件、Worker 注册表与清单
- **验证器**：证据约束抽取、验收门禁、加锁的唯一胜者、确认计数与浏览器上下文关闭
- **实验变量**：站点数量、串行/并行调度与级联时序
- **第一遍可跳过**：提供商请求凭证留存、HTML 夹具与报告格式化

### 消息协议

| 消息类型 | 方向 | 含义 |
|---------|------|------|
| `task_assigned` | 协调器 → Worker | 派发任务（目标、URL、任务 ID） |
| `status_update` | Worker → 协调器 | 状态表更新（执行中/已完成/失败/已终止） |
| `target_found` | Worker → 协调器 | 命中目标（首个生效，触发终止广播） |
| `not_found` | Worker → 协调器 | 页面中未找到目标及原因 |
| `terminate` | 协调器 → 广播 | 级联终止（整个实验只广播一次） |
| `ack` | Worker → 协调器 | Worker 对终止广播的确认 |
| `worker_error` | Worker → 协调器 | 错误隔离上报 |
| `resource_closed` | Worker → 协调器 | 浏览器上下文已关闭（资源审计） |

## 项目结构

```
chapter10/parallel-web-research/
├── demo.py                        # 演示入口：并行 + 串行对比
├── run_official_experiment.py     # 官方验收运行器（完整凭证留存）
├── agents.py                      # Worker、浏览器池、中心协调器
├── message_bus.py                 # 进程内异步消息总线
├── profile_llm.py                 # 证据约束抽取（统一 LLM 封装的异步调用）
├── sources.py                     # 真实大学网站数据集
├── sites.example.json             # 用户自备站点列表示例
├── cascade-stress.example.json    # 级联压测站点（同一档案页 × 4 查询 URL）
├── requirements.txt               # 实验特定依赖
├── test_*.py                      # 单元/回归/证据回放测试
├── validation/                    # 历史实测证据（2026-07 运行记录）
├── results/                       # demo.py 结果输出目录
└── logs/                          # 日志目录
```

## 配置说明

### LLM 配置（项目根目录 .env）

见"快速开始"第 3 步。本实验通过统一封装 `llm.client.get_llm_client()` 读取配置，再构造异步客户端完成抽取调用；不在本目录重复实现任何提供商配置。

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--target` | `Andrew Ng` | 要查找的教师姓名 |
| `--sites-json` | 内置 10 站 | 网站数组 JSON（每项含 name/college/url） |
| `--agents` | 10 | 使用前 N 个网站/Agent |
| `--timeout` | 120 | 每站超时秒数 |
| `--headed` | 关闭 | 显示每个真实浏览器页面 |
| `--quiet` | 关闭 | 不打印逐条总线消息 |
| `--no-compare` | 关闭 | 跳过串行基线 |
| `--output` | `results/latest.json` | 实测结果 JSON 保存路径 |

## 故障排除

| 现象 | 原因与处理 |
|------|-----------|
| 报错"需要在项目根目录 .env 中配置 API_KEY" | 根目录 `.env` 缺少 `API_KEY`/`LLM_PROVIDER`，按上文补齐 |
| 报错"playwright 未安装"或浏览器启动失败 | 运行 `playwright install chromium` 安装内核 |
| 部分站点超时/抽取失败 | 属于正常的错误隔离；结果 JSON 的 `failure_summary` 会按类型汇总 |
| `ModuleNotFoundError: llm` | 请从项目根目录运行，或保持文件内的路径处理代码完整 |
| 退出码非 0 | 验收门禁未全过（资源清理/单次级联/败者确认），查看输出的门禁详情 |
| 迁移后 `test_official_experiment.py` 哈希断言失败 | 该测试锚定历史运行快照；重新运行 `run_official_experiment.py` 生成新证据即可 |

## 技术要点

- **证据约束抽取**：先做确定性的人名出现门槛（`target` 未出现在渲染文本中直接判 `found=False`），防止模型凭参数化记忆编造档案；`evidence` 字段要求页面原文摘录。
- **级联终止语义**：`asyncio.Lock` 保证唯一胜者；只有结算时刻仍在运行的 Worker 欠一次确认（`expected_loser_acks` 快照），已自行完成者不计入。
- **可中断等待**：Worker 的每个耗时操作都与终止事件赛跑（`_await_interruptibly`），落败方在安全点取消并回执。
- **资源审计**：上下文创建/关闭计数器 + `resource_closed` 消息，双重保证"泄漏的浏览器会话"必然导致验收失败。
- **溯源完备凭证**：官方运行器留存原始请求/响应（含响应 ID 与用量）、总线事件流、源码与产物 SHA-256，并做凭证泄漏扫描（实际密钥命中 + 通用凭证模式双保险）。

## 历史实测证据

2026-07-29 的默认十页斯坦福运行通过 ARK 抽取在真实的 Stanford HAI 页面找到了 Andrew Ng：并行墙钟 18.542 秒、串行 58.264 秒，实测 3.142× 加速；并行与串行的全部 20 个浏览器上下文均关闭。级联压测产生 1 个胜者、1 次终止广播、3 份败者确认、4/4 上下文关闭。

当前溯源完备的验收战役记录见
[`validation/runs/exp10-4-real-receipts-20260730-v2/manifest.json`](validation/runs/exp10-4-real-receipts-20260730-v2/manifest.json)：
12 条验收门禁全部通过——十站并行与串行双模式均找到目标并关闭全部 20 个上下文，实测加速 1.872×；级联产生 1 次广播、3 份败者确认、4/4 上下文关闭。运行保留了 24 份完整浏览器观测、3 份带唯一响应 ID 与用量的原始 ARK 响应、114 条总线事件；7 个运行时源码/输入哈希与 4 个产物哈希全部可精确复算，凭证扫描零命中。

更早的"仅汇总"历史记录保留在
[`validation/real_parallel_serial_2026-07-29.json`](validation/real_parallel_serial_2026-07-29.json)
与 [`validation/real_cascade_2026-07-29.json`](validation/real_cascade_2026-07-29.json)，仅供历史对照，不再是当前的溯源锚点。

> 注：迁移后源码已经过统一 LLM 封装改造与中文化，历史快照中的源码哈希不再与当前文件匹配；如需复现完整的溯源锚点，请重新运行 `run_official_experiment.py` 生成新证据。
