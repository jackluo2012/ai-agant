# 混合检索流水线与神经重排序

> 《深入理解 AI Agent》第 3 章 **实验 3-6** 配套项目：稠密 + 稀疏 + 融合 + 重排，含离线评估脚本 `evaluate.py`

← [返回第 3 章](../README.md)

---

## 项目概述

本项目实现了一个完整的混合检索流水线，结合了稠密嵌入（语义检索）、稀疏检索（BM25 关键词匹配）、结果融合和神经重排序技术。

### 核心功能

1. **稠密检索**：使用 BGE-M3 模型进行语义理解和跨语言检索
2. **稀疏检索**：使用 BM25 算法进行精确关键词匹配
3. **结果融合**：支持倒排秩融合（RRF）和加权分数融合
4. **神经重排序**：使用 BGE-Reranker-v2 模型对候选结果进行精细化重排
5. **并行处理**：稠密和稀疏检索并行执行，提高响应速度

---

## 系统架构

```
┌──────────────────────────────────────────────┐
│            客户端应用程序                      │
└────────────────────┬─────────────────────────┘
                     ▼
┌──────────────────────────────────────────────┐
│         检索流水线 (端口 4242)                 │
│  文档存储 (内存)                              │
│  BGE-Reranker-v2 (本地模型)                  │
└────────┬──────────────────┬─────────────────┘
         ▼                  ▼
┌─────────────────┐  ┌─────────────────┐
│  稠密检索服务    │  │  稀疏检索服务    │
│   (端口 4240)   │  │   (端口 4241)   │
│   BGE-M3 模型   │  │   BM25 引擎     │
└─────────────────┘  └─────────────────┘
```

---

## 关键概念

### 稠密检索（BGE-M3）
- **优势**：语义理解、跨语言检索、同义词匹配
- **局限**：可能漏掉精确编码，计算成本较高

### 稀疏检索（BM25）
- **优势**：精确词/ID 匹配，速度快
- **局限**：无语义理解能力

### 融合策略（`fusion.py`）
- **RRF**：倒排秩融合 `score(d)=Σ 1/(k+rank)`，`k=60`（仅用排名，尺度无关）
- **加权融合**：min-max 归一化到 [0,1] 后加权求和

### 重排序
- **服务模式**：使用 BGE-Reranker-v2-M3
- **离线模式**：`evaluate.py` 使用 `BAAI/bge-reranker-base`

---

## 前置要求

- Python 3.8+
- macOS M1/M2（或调整设备设置）
- ≥8GB RAM
- 约 5GB 磁盘空间（用于模型）

---

## 安装步骤

```bash
cd chapter3/retrieval-pipeline
pip install -r requirements.txt
# 首次运行会下载：BGE-M3 (~2.3GB)，BGE-Reranker-v2-M3 (~1.1GB)
```

---

## 使用方法

### 启动服务

```bash
./start_all_services.sh
# 稠密服务 4240，稀疏服务 4241，流水线 4242
```

或分别启动：

```bash
# 终端 1
cd ../dense-embedding && python main.py --port 4240

# 终端 2
cd ../sparse-embedding && python server.py --port 4241

# 终端 3
cd ../retrieval-pipeline && python main.py --port 4242
```

### 测试服务

```bash
python test_client.py   # 教学测试用例
python demo.py          # 交互式演示
# API 文档: http://localhost:4242/docs
```

### 离线评估 CLI（`evaluate.py`）

`test_client.py`/`demo.py` 需要端口 4240-4242。**`evaluate.py` 在单进程中运行完整流水线——无需启动服务，模型缓存后可完全离线运行**。注意：首次运行仍会从 HuggingFace 下载稠密/重排模型，因此首次执行需要网络访问。

```bash
python evaluate.py --help          # 中文帮助
python evaluate.py                 # 完整阶段表格（默认）
python evaluate.py --no-dense      # 仅 BM25，无需模型
python evaluate.py --no-rerank    # 跳过重排序
python evaluate.py --query "XR-7003"
python evaluate.py --embed-model BAAI/bge-m3 --pooling cls
python evaluate.py --output result.json
```

| 阶段 | 默认组件 | 离线？ |
|------|----------|--------|
| 分块 | 字符窗口切分器 | ✅ 纯 Python |
| 稀疏 | BM25 (`rank_bm25`) | ✅ 无需下载模型 |
| 稠密 | `sentence-transformers/all-MiniLM-L6-v2` (~90MB) | ✅ HF 缓存 |
| 融合 | RRF + 加权 (`fusion.py`) | ✅ 纯 Python |
| 重排 | `BAAI/bge-reranker-base`（首次下载 ~1.1GB） | ✅ 缓存后离线 |

> `--no-dense` 完全不需要 ML 模型。稠密/重排模型首次运行时从 HuggingFace 下载（需要网络）；之后从本地缓存运行，`--offline` 强制仅从本地缓存加载。在 Apple Silicon 上，如检测到 MPS 出现 `NaN` 则自动回退到 CPU。

---

## API 接口

### 索引文档

```bash
POST /index
{
  "text": "文档内容",
  "doc_id": "可选的文档ID",
  "metadata": {"category": "示例"}
}
```

### 搜索文档

```bash
POST /search
{
  "query": "搜索词",
  "mode": "hybrid",
  "top_k": 20,
  "rerank_top_k": 10
}
```

### 其他接口

```bash
GET /stats              # 获取统计信息
GET /documents          # 列出文档
DELETE /delete          # 删除文档
```

响应包含稠密/稀疏原始排名、重排结果、排名变化和重叠统计。

---

## 项目结构

```
retrieval-pipeline/
├── config.py              # 配置模块
├── document_store.py      # 文档存储
├── retrieval_client.py    # 检索客户端
├── reranker.py            # 重排序模块
├── fusion.py              # 结果融合
├── retrieval_pipeline.py  # 主流水线
├── main.py                # FastAPI 服务
├── demo.py                # 交互演示
├── test_client.py         # 测试用例
├── evaluate.py            # 离线评估
├── requirements.txt       # 依赖列表
├── start_all_services.sh  # 启动脚本
├── stop_all_services.sh   # 停止脚本
└── README.md              # 本文件
```

---

## 教学测试用例（需服务）

1. **语义查询**（"小猫行为" / feline）— 稠密检索胜出
2. **精确名称**（"张三"）— 稀疏检索胜出
3. **多语言**（"人工智能"）— 稠密检索胜出
4. **技术编码**（"HTTP-403"）— 稀疏检索胜出
5. **概念查询**（"幸福与兴奋"）— 稠密检索胜出

---

## 性能指标

- **时延量级**：稠密 50-100ms，稀疏 10-30ms，重排 100-200ms（20 文档）
- **内存占用**：约 4GB（模型 + 文档）
- **核心结论**：没有单一方法最优；混合检索通常更好；重排序提升相关性

---

## 真实输出示例

```
阶段 / 方法            Recall@3         MRR      nDCG@3
------------------------------------------------------------------------------
BM25 (稀疏)              0.9000      0.8500      0.8631
稠密                     1.0000      0.9000      0.9262
混合-RRF                 1.0000      1.0000      1.0000
混合-加权                1.0000      0.9500      0.9631
混合-RRF+重排            1.0000      0.9500      0.9631
```

**解读**：BM25 擅长编码匹配，但在改写上失败；稠密检索相反；**混合-RRF 达到完美 1.00**（实验 3-6 的核心结论）。加权融合对尺度更敏感。在这个 17 文档的玩具数据集上 RRF 已很强，重排序的价值在更大候选池和自然语言查询中更明显。

---

## 故障排查

- 确保端口 4240-4242 可用
- 确保模型已下载
- 确保 Python 3.8+
- OOM 错误：减小 batch size，使用 CPU，开启 FP16
- 首次运行慢（模型下载）

---

## 延伸阅读

- [BGE-M3 论文](https://arxiv.org/abs/2402.03216)
- [BM25 算法](https://zh.wikipedia.org/wiki/Okapi_BM25)
- [神经信息检索](https://arxiv.org/abs/2301.09191)

---

## 许可证

本项目为教学项目，仅用于学习目的。

---

## 注意事项

- 上游服务：[`../dense-embedding/`](../dense-embedding/)（4240）、[`../sparse-embedding/`](../sparse-embedding/)（4241）
- 本项目已从 `ai-agent-book` 迁移到 `ai-agant`，遵循项目规范
