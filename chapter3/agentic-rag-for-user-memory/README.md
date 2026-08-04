# 面向用户记忆的 Agentic RAG 系统

> 配套《深入理解 AI Agent》第 3 章——对话记忆上的 Agentic 多跳检索；含离线演示与可选检索流水线。

[← 返回第 3 章目录](../README.md)

---

## 项目概述

本项目实现了智能体化 RAG（Agentic RAG）系统，用于检索和回答关于用户对话历史的问题。系统采用 ReAct 模式，通过多轮工具调用来实现多跳检索，显著提升了跨会话信息检索的准确性。

### 核心特性

- **对话分块索引**：将长对话分割为可索引的块（约 20 轮 + 重叠 + 上下文增强）
- **混合检索**：支持稠密向量 + 稀疏（BM25）混合检索；可扩展外部流水线
- **Agentic RAG**：采用 ReAct 模式，智能体自主决策检索策略
- **LLM 自动评估**：集成自动评分框架（≥0.6 分通过）
- **完全离线支持**：内置 BM25 后端，无需外部服务即可运行

### 系统架构

```
用户记忆测试用例（60 个，3 个层次）
    → 对话分块器（约 20 轮分段 + 重叠 + 增强）
    → 外部检索流水线（端口 4242）或本地 BM25
         稠密 + 稀疏混合
    → Agentic RAG 智能体（ReAct；search_memory / get_conversation_context / get_full_conversation）
    → LLM 评估（奖励 0-1，通过/失败，推理说明）
```

### 关键概念

1. **对话分块**：约 20 轮，可搜索，有上下文，高效
2. **混合检索**（可选流水线）：稠密 + BM25 + 融合；可扩展
3. **Agentic RAG**：推理 → 行动 → 观察 → 迭代
4. **LLM 评估**：集成 user-memory-evaluation 风格评分（≥0.6 通过）
5. **上下文增强**：元数据、邻近块、标签

---

## 前置条件

- Python 3.8+
- **端口 4242 检索流水线是可选的。** 默认 `retrieval_backend="auto"`：如果流水线可达则使用，否则使用**内置本地 BM25**（离线工作）。
- 仅 LLM 模式（`batch` / `interactive` / `demo`）需要 API 密钥。
- **`--mode offline-demo` 不需要 API 密钥和端口 4242。**

---

## 安装

```bash
cd chapter3/agentic-rag-for-user-memory
pip install -r requirements.txt
```

### 环境配置

LLM 配置由项目根目录（`ai-agant/`）的 `.env` 文件统一提供：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your_api_key
LLM_PROVIDER=kimi          # 或 openai, deepseek 等
LLM_MODEL=kimi-k3
BASE_URL=https://api.moonshot.cn/v1
```

---

## 检索后端配置

| 值 | 行为 |
|----|------|
| `auto` | 默认——流水线可用则使用，否则本地 BM25 |
| `local` | 始终使用离线 BM25 |
| `pipeline` | 始终使用端口 4242 流水线 |

### 可选检索流水线

```bash
cd ../retrieval-pipeline
python api_server.py   # http://localhost:4242
```

---

## 使用方法

### 离线演示（无需 API）

离线多跳检索 vs 朴素单次检索对比演示：

```bash
# 从项目根目录运行
cd ai-agant
source .venv/bin/activate
python chapter3/agentic-rag-for-user-memory/main.py --mode offline-demo

# 或直接运行
python chapter3/agentic-rag-for-user-memory/offline_demo.py
python chapter3/agentic-rag-for-user-memory/offline_demo.py --output results/offline_demo.json
```

### 交互模式

```bash
python chapter3/agentic-rag-for-user-memory/main.py
```

交互式菜单提供以下选项：
1. 加载测试用例
2. 查看已加载的测试用例
3. 配置设置
4. 评估单个测试用例
5. 按类别评估
6. 评估所有测试用例
7. 查看结果
8. 生成报告
9. 演示模式（快速测试）

### 批量评估

```bash
# 评估特定类别
python chapter3/agentic-rag-for-user-memory/main.py --mode batch --category layer1 --backend local

# 评估单个测试用例
python chapter3/agentic-rag-for-user-memory/main.py --mode batch --test-id layer2_01_multiple_vehicles
```

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--mode {interactive,batch,demo,offline-demo}` | 运行模式 |
| `--category {layer1,layer2,layer3}` | 批量模式下评估的难度层次 |
| `--test-id` | 指定要评估的单个用例 ID |
| `--index-mode {dense,sparse,hybrid}` | 检索策略 |
| `--backend {auto,local,pipeline}` | 检索后端选择 |
| `--top-k` | 每次记忆检索返回的块数量 |
| `--rounds-per-chunk` | 对话分块时每块的轮数（默认 20） |
| `--output` | 结果输出文件路径 |

---

## 离线演示结果（可重现）

在 `layer2_01_multiple_vehicles`（本田 + 特斯拉跨会话）测试用例上，真实 BM25 检索结果：

| 指标 | 朴素单次查询 | Agentic 多跳 |
|------|-------------|-------------|
| 发出的检索查询数 | 1 | 5 |
| 检索的记忆块数 | 3 | 5 |
| 决定性证据召回率 | **50%** | **100%** |
| 能否完全消歧并回答 | 否 | 是 |

朴素方法被"预约服务"关键词主导，错过了本田确认信息（`FS-447291`）。Agentic 方法发现了第二辆车，发出有针对性的后续查询，恢复了证据。数据来自实际检索，非硬编码。

---

## 测试用例层次

- **L1 简单检索**："我的支票账户号码是多少？"
- **L2 多会话**："哪辆车需要先保养？"
- **L3 复杂推理**："旅行前我有哪些紧急事项？"

---

## 核心组件

- **chunker.py**：对话分块器
- **indexer.py**：记忆索引器（支持本地 BM25 和外部流水线）
- **tools.py**：记忆工具（search_memory, get_conversation_context, get_full_conversation）
- **agent.py**：ReAct 智能体
- **evaluator.py**：评估框架集成

---

## 配置示例

```python
config.chunking.rounds_per_chunk = 20
config.chunking.overlap_rounds = 2
config.index.mode = "hybrid"
config.index.enable_contextual = True
config.agent.max_search_results = 5
config.evaluation.max_iterations = 10
```

---

## 指标与故障排查

**指标**：成功率、LLM 奖励、迭代次数、工具调用、延迟、索引时间

**Top-k 配置**：流水线使用 `top_k`（候选）和 `rerank_top_k`（最终）

**LLM 评估缺失**：需要评估器 API 和标准

**流水线不可用**：使用 `--backend auto` 非致命；强制离线使用 `--backend local`

---

## 相关项目

- `user-memory`：用户记忆管理
- `user-memory-evaluation`：用户记忆评估框架
- `agentic-rag`：Agentic RAG 基础实现
- `contextual-retrieval`：上下文检索（同 chapter3 路径）

---

## 技术要点

### ReAct 循环

智能体采用 ReAct（推理-行动-观察）模式：

1. **推理**：分析当前信息，决定下一步行动
2. **行动**：调用检索工具获取更多信息
3. **观察**：分析工具返回的结果
4. **迭代**：重复直到有足够信息回答

### 多跳检索策略

与传统单次检索不同，Agentic RAG：
- 根据初步结果动态调整检索策略
- 发出多个相关查询以覆盖不同角度
- 利用上下文工具获取完整对话历史
- 通过迭代逐步缩小搜索范围

---

## 许可证

教育教学用途。
