# Agentic RAG 系统

> 第 3 章 **实验 3-9**：ReAct 式 Agentic RAG 与非 Agentic RAG 对比，使用中文法律问答数据集；离线多跳证据召回对比。

← [返回第 3 章](../)

---

## 项目概述

本项目实现了两种 RAG（检索增强生成）范式的对比：

- **Agentic RAG（ReAct 模式）**：多轮迭代检索 + 推理 + 工具调用
- **非 Agentic RAG**：单次检索 + 一次性回答

核心发现：对于复杂问题，Agentic 风格的多跳/分解检索的证据召回率显著优于单次查询。

---

## 功能特性

- **双模式对比**：Agentic RAG（ReAct）与非 Agentic RAG
- **多种知识库后端**：
  - 离线 BM25（内置，零依赖）- 使用 `laws/` 目录
  - 本地检索流水线
  - Dify 知识库 API
- 智能分块（保持段落边界）
- 中文法律数据集评测
- 多轮对话支持
- 详细推理轨迹日志

---

## 安装与配置

### 安装依赖

```bash
# 核心依赖由项目根目录统一管理
# 以下为实验特定依赖
pip install -r requirements.txt
```

### 配置 LLM

项目自动读取项目根目录的 `.env` 文件，无需额外配置 LLM 参数。

```bash
# 在项目根目录的 .env 中配置（已完成）
API_KEY=your_api_key
LLM_PROVIDER=kimi
LLM_MODEL=kimi-k3
BASE_URL=...
```

### 配置知识库

```bash
# 可选：设置知识库类型（默认：local）
KB_TYPE=offline  # "offline" | "local" | "dify"

# Dify 配置（如使用 Dify）
DIFY_API_KEY=...
DIFY_DATASET_ID=...
```

---

## 使用方法

### 1. 零依赖离线对比（推荐先运行）

完全离线运行，无需 API 密钥或外部服务。`compare_offline.py` 使用内置的离线 BM25 检索器。

```bash
cd chapter3/agentic-rag
python compare_offline.py
```

实测结果（21372 条法条分块 / 288 个文档）：

```
问题                          难度    单次检索    分解检索    检索次数
------------------------------------------------------------------------------
故意伤害致人重伤的，如何处…  easy    100%        100%        1 → 1
正当防卫是怎么规定的？        easy    100%        100%        1 → 1
醉酒驾驶机动车如何处罚？      easy    100%        100%        1 → 1
故意杀人罪判几年？            hard    0%          100%        1 → 1
盗窃罪的立案标准是什么？      hard    0%          100%        1 → 1
诈骗罪的量刑标准是什么？      hard    0%          100%        1 → 1
醉酒过失致人重伤且有盗窃前…  hard    33%         100%        1 → 3
------------------------------------------------------------------------------
聚合指标（平均证据召回率）:
  全部                                48%         100%        1.0 → 1.3
  简单题                              100%        100%        1.0 → 1.0
  复杂题                              8%          100%        1.0 → 1.5
```

**解读**：简单题两种范式均约 100%；复杂/表述不当的问题：**8% → 100%**。

### 2. 完整 Agent（需 API）

使用离线知识库（检索离线，回答生成需要 API）：

```bash
# 单条查询
python main.py --kb-type offline --query "醉酒过失致人重伤且有盗窃前科如何量刑"

# 对比模式
python main.py --kb-type offline --query "故意杀人罪判几年" --mode compare
```

### 3. 本地检索流水线模式

首先启动检索流水线：

```bash
cd chapter3/retrieval-pipeline
python main.py
# http://localhost:4242
```

然后运行 Agentic RAG：

```bash
cd chapter3/agentic-rag

# 交互模式（默认）
python main.py

# 单条查询
python main.py --query "宪法第一条是什么？" --mode agentic
python main.py --query "盗窃罪的立案标准是什么？" --mode non-agentic

# 对比模式
python main.py --query "故意杀人罪判几年？" --mode compare
```

### 4. 批量查询

```bash
python main.py --batch queries.txt --output results.json
python main.py --batch queries.txt --mode non-agentic --output results_non_agentic.json
```

### 5. 文档索引

```bash
# 索引本地法律文档
python index_local_laws.py
python index_local_laws.py --categories 宪法 民法典
python index_local_laws.py --max-docs 10

# 索引自定义文档
python main.py --index path/to/document.txt
python main.py --index path/to/documents/ --chunk-size 2048
```

### 6. 交互命令

在交互模式中：

- `quit` / `exit`：退出
- `clear`：清除对话历史
- `mode`：切换 agentic/non-agentic 模式

---

## 项目结构

```
agentic-rag/
├── README.md           # 本文档
├── requirements.txt    # 实验特定依赖
├── config.py           # 配置（不含 LLM 配置）
├── agent.py            # Agentic RAG Agent
├── tools.py            # 知识库工具
├── main.py             # 主入口
├── chunking.py         # 文档分块
├── offline_retriever.py # 离线 BM25 检索器
├── compare_offline.py  # 离线对比脚本
├── index_local_laws.py # 法律文档索引
├── quickstart.py       # 快速入门
├── laws/               # 中文法律语料
│   ├── 1-宪法/
│   ├── 2-宪法相关法/
│   ├── 3-民法典/
│   ├── 4-行政法/
│   ├── 5-经济法/
│   ├── 6-社会法/
│   ├── 7-刑法/
│   └── 8-诉讼与非诉讼程序法/
├── results/            # 结果输出目录
├── logs/               # 日志目录
└── evaluation/          # 评测脚本
    ├── dataset_builder.py
    ├── evaluate.py
    └── offline_qa.json
```

---

## 工作原理

### Agentic 模式

1. 理解用户问题
2. 调用 `knowledge_base_search` 工具搜索相关信息
3. 如需更多上下文，调用 `get_document` 获取完整文档
4. 综合信息生成答案（含引用）
5. 保留对话历史用于后续问题

### 非 Agentic 模式

1. 使用原始查询进行单次检索
2. 将 Top-K 结果注入 Prompt
3. LLM 一次性生成答案

---

## 配置参数

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--mode` | 查询模式：`agentic`（默认）、`non-agentic`、`compare` |
| `--query` | 单条查询问题 |
| `--batch` | 批量查询文件路径 |
| `--output` | 批量结果输出文件（默认：results.json） |
| `--kb-type` | 知识库类型：`offline`、`local`、`dify` |
| `--corpus` | 离线后端语料目录（仅 offline 模式，默认：laws） |
| `--top-k` | 每次检索返回的分块数量 |
| `--verbose` / `--no-verbose` | 开启/关闭详细推理轨迹 |
| `--index` | 待索引的文件或目录路径 |
| `--chunk-size` | 索引时的分块大小（默认：2048） |

---

## 评测结果

### 检索层（离线，可复现）

见上文表格：复杂题证据召回率 **8% → 100%**。

### 生成层（需 API）

运行 `evaluation/evaluate.py` 评估：
- 成功率
- 关键概念召回率
- 延迟
- 引用覆盖率

Agentic 模式：多面覆盖更好、引用更全；较慢。
非 Agentic 模式：更快；对复杂/歧义问题较弱。

---

## 故障排查

### 检查检索流水线

```bash
curl http://localhost:4242/health
```

### 启动检索流水线

```bash
cd chapter3/retrieval-pipeline
python main.py
```

### 检查文档索引

```bash
python index_local_laws.py
ls -la document_store.json
curl http://localhost:4242/stats
```

### 检查 LLM 配置

确保项目根目录的 `.env` 文件包含有效的 API 配置。

---

## 技术要点

1. **ReAct 模式**：推理（Reasoning）+ 行动（Acting）循环
2. **工具调用**：使用 OpenAI Function Calling 格式
3. **多跳检索**：通过多轮工具调用实现信息聚合
4. **引用机制**：每个答案都包含文档/分块引用
5. **离线优先**：内置 BM25 检索器，零依赖运行

---

## 扩展开发

### 添加新的知识库后端

1. 在 `config.py` 中添加 `KnowledgeBaseType` 枚举值
2. 在 `KnowledgeBaseConfig` 中添加配置字段
3. 在 `tools.py` 中实现 `_search_xxx()` 和 `_get_document_xxx()` 方法

### 自定义系统提示词

修改 `agent.py` 中的 `_get_system_prompt()` 方法。

---

## 许可

教学项目。
