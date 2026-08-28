# 实验 10-2：书籍翻译 Agent —— 管理者模式（Orchestration）

演示如何用**管理者模式（Orchestration）**把长文档翻译任务委托给多个专职 Agent 协作完成。核心思想是**上下文隔离**与**控制管理者上下文膨胀**：Manager 只保存任务、计划、各 Agent 调用记录与文件索引，**完整译文全部落盘到文件系统**——因此无论书有多长，Manager 的上下文都基本恒定。

## 功能概述

- **两种翻译方式对照**：
  - 【管理者模式】Glossary / Translation / Proofreading / Manager 四种专职 Agent 协作；
  - 【单 Agent 模式】一条不断增长的对话依次读全书、逐章翻译（对照组）。
- **真实 token 记账**：每次 LLM 调用都按 Agent 记录输入 / 输出 token 与上下文峰值。
- **共享术语表**：Manager 把编辑部指定术语强制写入术语表并下发所有 Translation Agent，
  用确定性字符串匹配度量"术语一致率"与"术语表遵从率"。
- **断点续跑**：单 Agent 模式与官方验收战役均支持检查点恢复，不重放已付费调用。
- **离线预演**：`--dry-run` 不调用任何 API 即可查看四 Agent 协作图与 token 预算。

## 架构：四种专职 Agent

| Agent | 输入（独立上下文） | 输出 | 上下文特征 |
| --- | --- | --- | --- |
| **Glossary Agent** | 全书内容 | 结构化术语表 `glossary.json` | 读整本书，产出后即释放 |
| **Translation Agent** | 当前章节 + 术语表 + 翻译指南 | `chapterN_zh.md` | 每章一个独立实例，只看到自己那一章 |
| **Proofreading Agent** | 全部译文 + 术语表 | 审校报告 `proofreading_report.json` | 做一致性 / 流畅性检查 |
| **Manager Agent** | 任务 + 文件索引 + 报告摘要 | 调度决策（是否发回修订） | **只存元信息，绝不存正文** |

数据流：Manager 先调度 Glossary 抽取术语表，再逐章调度 Translation（全部共享同一份
术语表文件），然后由 Proofreading 审校，最后 Manager 根据报告决定个别章节是否发回修订。
译文与术语表都经**文件系统**流转，Manager 的上下文里只有文件路径。

关键设计：Manager 把编辑部指定术语（token→词元、prompt→提示词、latency→时延等）
强制写入共享术语表，从而把指定译法贯彻到全书；单 Agent 看不到术语表，只能使用自己的默认译法。

## 项目结构

```text
chapter10/book-translation/
├── agents.py                  # 四种 Agent + 两种运行方式 + TokenTracker 记账
├── consistency.py             # 术语一致性 / 术语表遵从率（确定性字符串匹配）
├── consistency_auditor.py     # 双语一致性审计器（术语/代码块/LaTeX 公式/链接四类检查）
├── demo.py                    # 一键演示入口（含 --dry-run 离线预演）
├── run_official_experiment.py # 官方全量验收战役（盲评 + 验收门禁 + provenance）
├── test_official_experiment.py# 验收脚本的离线回归测试
├── tests/                     # Glossary / Proofreading 边界情况的离线回归测试
├── sample_book/               # 内置英文短章节样书（4 章，含术语与代码块）
│   ├── chapter1.md ... chapter4.md
├── validation/                # 历史实验存档（源仓库原始运行产物，仅供参考）
├── results/                   # 结果输出目录
├── logs/                      # 日志目录
└── requirements.txt           # 本实验无额外依赖（openai/dotenv/tiktoken 由根目录提供）
```

## 快速开始

### 1. 环境准备

本项目遵循 ai-agant 统一环境约定：

```bash
cd ai-agant
source .venv/bin/activate        # 使用项目根目录统一虚拟环境
```

核心依赖（`openai`、`python-dotenv`、`tiktoken`）已由根目录虚拟环境统一提供。

### 2. 配置说明（项目根目录 .env）

LLM 配置统一读取 **ai-agant/.env**（所有章节共享），本目录没有也不需要独立的 `.env`：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi    # 或 aliyun / deepseek / openai / anthropic / custom 等
LLM_MODEL=kimi-k3    # 未设置时使用该提供商的默认模型
# BASE_URL=https://...   # 仅 aliyun / custom 等提供商需要
```

### 3. 运行

```bash
cd ai-agant
python3 chapter10/book-translation/demo.py --dry-run   # 离线预演，无需密钥
python3 chapter10/book-translation/demo.py             # 完整对比演示
```

> 注意：请在 ai-agant 根目录下运行，或保证根目录在 `PYTHONPATH` 中，
> 这样脚本才能找到统一的 `llm` 模块。

### demo.py 常用参数

| 参数 | 说明 |
| --- | --- |
| `--dry-run` | 离线预演：打印协作图 / 计划 / token 预算，不调 API |
| `--skip-single` | 只跑管理者模式，跳过单 Agent 对照组 |
| `--no-glossary` | 关闭术语抽取（仅保留编辑部指定术语） |
| `--no-proofreading` | 关闭审校 Agent 与修订闭环 |
| `--model NAME` | 临时覆盖模型（等价于根目录 .env 的 `LLM_MODEL`） |
| `--sample-dir DIR` | 换输入书（读取其中按文件名排序的 `*.md`） |
| `--out-dir DIR` | 换产物根目录（默认 `output/`） |
| `--source-lang` / `--target-lang` | 翻译方向措辞（默认 英文 → 中文） |

产物示例：`output/orchestration/glossary.json`、`output/orchestration/chapter1_zh.md`、
`output/orchestration/proofreading_report.json`、`output/single_agent/chapterN_zh.md`。

## 官方全量验收战役

`run_official_experiment.py` 是完整验收流水线：切分翻译单元 → 两种方式全量翻译 →
**盲评打分**（评审模型对两份匿名译文按 准确度 / 流畅度 / 术语 / Markdown 保真 打分）→
一致性分析 → 验收门禁与 provenance 哈希存证。

```bash
# 在 ai-agant 根目录下运行
python3 chapter10/book-translation/run_official_experiment.py
# 指定输入章节（可重复传入 --source）
python3 chapter10/book-translation/run_official_experiment.py \
    --source path/to/chapter1.md --source path/to/chapter2.md
```

- 默认输入为内置 `sample_book/` 前两章（轻量演示即可跑通全流程；
  正式书籍级验收请用 `--source` 传入完整章节 Markdown）。
- 断点续跑：每个阶段落盘检查点到 `validation/<时间戳>/`，中断后重跑会自动跳过已完成单元。
- 最终证据写入 `validation/evidence.json` 与 `validation/latest.json`，
  退出码 0 表示全部验收门禁通过。

## 单元测试

测试完全离线：`tests/conftest.py` 对 `openai` / `tiktoken` 打桩，
`agents.get_client` / `agents.llm_chat` 在用例内被打桩替换，不需要 API 密钥与网络：

```bash
cd ai-agant
python3 -m pytest chapter10/book-translation/tests/ chapter10/book-translation/test_official_experiment.py
```

覆盖点包括：null / 非字典审校结果的容错、不合规术语条目的丢弃、Markdown 保真校验、
翻译单元无损切分、断点续跑不重放已成功调用、评审 schema 失败的重试与修复回执持久化。

## 使用示例

完整演示结束时会输出三张核心对比表：

```text
【管理者模式】各 Agent 上下文 token 消耗
Agent            调用次数      输入tok      输出tok    上下文峰值
Glossary              1         ...          ...         ...
Translation           N         ...          ...         ...

术语一致性对比（确定性字符串匹配，非模型打分）
[管理者模式] 术语一致性：9/9 个术语全书统一（100%）

术语表遵从率对比：编辑部指定术语能否贯彻全书
指定术语        规定译法     默认译法     管理者(遵从/出现)  单Agent(遵从/出现)
token           词元         标记                    x/y                x/y

核心对比表：管理者模式 vs 单 Agent 模式
主/Manager 上下文峰值(tokens)        ...
术语内部一致率                       ...
```

解读要点：Manager 上下文只随"章节数"增加几行记录，与每章正文长度无关；
单 Agent 把全部原文与译文留在同一条对话里，上下文随书长线性膨胀。

## 故障排除

| 现象 | 原因与处理 |
| --- | --- |
| `无法导入统一 LLM 客户端 llm.client` | 未在项目根目录下运行或根目录不在 `PYTHONPATH`。请在 ai-agant 根目录执行，或 `export PYTHONPATH=$PYTHONPATH:$(pwd)` 后再进入子目录运行。 |
| `API 密钥未设置…`（ValueError） | 根目录 `.env` 缺少 `API_KEY`。补齐后重试；只想看结构可先跑 `demo.py --dry-run`。 |
| `提供商 'xxx' 需要指定 BASE_URL` | aliyun / custom 提供商必须在根目录 `.env` 中配置 `BASE_URL`。 |
| `请提供模型名称…` | 该提供商无默认模型时需在根目录 `.env` 设置 `LLM_MODEL`，或运行时加 `--model`。 |
| 评审报错 `未通过 schema 校验` | 模型多次输出不合规格式。换能力更强的模型，或直接重跑（有回执与重试机制）。 |
| 验收脚本退出码非 0 | 某些验收门禁未通过（如书籍规模不足）。查看 `validation/latest.json` 的 `acceptance_gates` 定位未达标项。 |

## 技术要点

- **上下文隔离**：各子 Agent 每次从零构造 messages，天然互不污染；
  Manager 只持有路径索引与摘要，译文正文永不回流其上下文。
- **真实记账**：优先使用 API 返回的真实 usage（`prompt_tokens` / `completion_tokens`）；
  "从未发给模型"的 Manager 状态则用 tiktoken 离线估算。
- **确定性度量**：术语一致性 / 遵从率由纯字符串匹配统计得出，不受评分模型主观性影响；
  `consistency_auditor.py` 进一步提供代码块同步、LaTeX 公式保留、链接保真的规则化审计。
- **鲁棒解析**：`_loads_lenient` 兼容围栏包裹的 JSON；对 null、非字典条目、JSON 数组等
  模型失误逐层容错，避免长任务中途崩溃。
- **瞬时故障自愈**：超时 / 限流 / 空响应自动指数退避重试并计入记账记录。

## 迁移说明

本项目迁移自 `ai-agent-book/chapter10/book-translation`，主要调整：

1. **LLM 配置统一**：移除 OpenAI / OpenRouter / Mistral / ARK 多提供商路由与
   `OPENAI_*` / `ARK_API_KEY` / `MISTRAL_API_KEY` 环境变量依赖，
   改为通过项目根目录 `llm/client.py::get_llm_client()` 统一创建客户端；
   删除了项目内 `env.example`，配置全部集中在 ai-agant/.env。
2. **配套更新**：`--provider` 参数移除；评审客户端同样走统一配置；
   指纹 / 记账中的 provider 特判（thinking 开关）随多路由一并移除。
3. **中文化**：全部注释、文档字符串、用户可见消息、评审与修复提示词均为中文。
4. **验证目录**：`validation/` 下的历史实验产物为源仓库存档，其哈希绑定的
   原始验收回归测试已随迁移移除，存档数据仅供结果比对参考。
