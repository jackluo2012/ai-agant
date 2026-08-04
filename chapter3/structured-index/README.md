# 结构化索引：RAPTOR 与 GraphRAG

> 配套《深入理解 AI Agent》第 3 章 **实验 3-8**：RAPTOR 层次树 vs GraphRAG 知识图谱，含离线「结构化 vs 扁平」演示。

← [返回第 3 章目录](../README.md)

---

## 概述

面向大型技术文档（如 Intel® SDM 风格手册）的两种结构化索引方法：

1. **RAPTOR** — 递归摘要的层次树
2. **GraphRAG** — 实体/关系/社区与多跳遍历

### 功能特性

**RAPTOR：**
- 多层抽象结构
- 递归摘要生成
- 自叶到根检索
- GMM 聚类
- UMAP 降维

**GraphRAG：**
- LLM 实体/关系抽取
- 社区检测
- 社区摘要
- 多策略检索
- **多跳关系遍历**（回答「A 与 B 如何相连」）

**HTTP API：**
- 构建/查询接口
- 文件上传
- 异步大文档处理
- 混合检索
- 状态统计

---

## 安装

### 前置条件

本项目已迁移到 `ai-agant` 统一项目结构，使用项目根目录的 LLM 配置。

```bash
# 确保在项目根目录
cd /path/to/ai-agant

# 安装依赖
pip install -r chapter3/structured-index/requirements.txt
```

### 环境配置

在项目根目录的 `.env` 文件中配置 LLM：

```bash
# 项目根目录的 .env
API_KEY=your_api_key
LLM_PROVIDER=aliyun          # 或 kimi, openai, deepseek 等
LLM_MODEL=qwen3.7-max-2026-05-20
BASE_URL=https://your-endpoint.com/v1
```

---

## 使用方法

### 命令行接口

所有子命令支持中文 `--help`：

```bash
# 从项目根目录运行（推荐）
python chapter3/structured-index/main.py --help
```

```
用法: main.py [-h] {build,query,demo,serve} ...
  build   从文档构建结构化索引（需要 LLM 配置）
  query   查询已构建的索引
  demo    离线对比：结构化 vs 扁平（无需 API Key）
  serve   启动 HTTP API
```

### 0. 离线演示（推荐先运行）

无需 API Key，使用预构建的小型 Intel x86 SIMD 知识库：

```bash
python chapter3/structured-index/main.py demo

# 自定义查询
python chapter3/structured-index/main.py demo --query "VADDPS 用到哪个寄存器"

# 输出到文件
python chapter3/structured-index/main.py demo --output demo_result.json
```

示例输出（多跳关系推理）：

```
【查询 1｜多跳关系推理】运行 ADDPS 指令前，操作系统必须把哪个控制寄存器位置 1？
-- 扁平检索（按词面相似度返回独立片段）--
  1. [control-bit] CR4.OSFXSR  (score=0.459)
  ...
  × 只能召回词面相近的孤立片段，无法把 ADDPS 与某个控制位「连」起来。

-- 结构化图检索（沿关系边多跳遍历）--
  ADDPS --属于--> SSE --需要启用--> CR4.OSFXSR
  √ 答案：CR4.OSFXSR（从 ADDPS 经 2 跳可达）
```

### 1. 构建索引

```bash
# 构建两种索引
python chapter3/structured-index/main.py build path/to/document.pdf

# 只构建 RAPTOR
python chapter3/structured-index/main.py build path/to/document.pdf --type raptor

# 只构建 GraphRAG
python chapter3/structured-index/main.py build path/to/document.pdf --type graphrag

# 输出统计信息
python chapter3/structured-index/main.py build path/to/document.pdf --output stats.json
```

### 2. 查询索引

```bash
# 查询两种索引
python chapter3/structured-index/main.py query "MOV 指令有哪些变体？"

# 只查询 RAPTOR
python chapter3/structured-index/main.py query "解释 SSE 指令" --type raptor --top-k 10

# 查询 GraphRAG + 多跳遍历
python chapter3/structured-index/main.py query "SSE 寄存器" --type graphrag --multi-hop 2

# 输出结果
python chapter3/structured-index/main.py query "控制寄存器" --output result.json
```

### 3. HTTP API 服务

```bash
# 启动服务
python chapter3/structured-index/main.py serve

# 访问 http://localhost:4242
```

### HTTP API 示例

```bash
# 上传并构建索引
curl -X POST "http://localhost:4242/upload" \
  -F "file=@path/to/intel_manual.pdf" \
  -F "index_type=both"

# 构建索引
curl -X POST "http://localhost:4242/build" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/document.pdf", "index_type": "both", "force_rebuild": false}'

# 查询
curl -X POST "http://localhost:4242/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "什么是向量指令？", "index_type": "hybrid", "top_k": 5}'

# 获取状态
curl http://localhost:4242/status
curl http://localhost:4242/statistics
```

| 端点 | 方法 | 描述 |
|------|------|------|
| `/` | GET | API 信息 |
| `/build` | POST | 从文本/文件构建索引 |
| `/upload` | POST | 上传 + 构建 |
| `/query` | POST | 查询索引 |
| `/status` | GET | 服务状态 |
| `/statistics` | GET | 索引统计 |
| `/indexes` | DELETE | 清除索引 |

---

## 项目结构

```
structured-index/
├── config.py                 # 项目特定配置（非 LLM）
├── raptor_indexer.py         # RAPTOR 实现
├── graphrag_indexer.py       # GraphRAG 实现
├── document_processor.py     # 文档处理
├── api_service.py           # HTTP API
├── structured_vs_flat_demo.py # 离线演示
├── main.py                  # 命令行入口
├── requirements.txt         # 实验特定依赖
├── env.example              # 环境变量示例（仅供参考）
├── indexes/                 # 索引存储
│   ├── raptor/
│   └── graphrag/
└── cache/                   # 缓存目录
```

---

## 工作原理

### RAPTOR

1. 分块 → 嵌入 → 叶节点
2. GMM 聚类
3. 为每个聚类创建父节点摘要
4. 递归构建多层树
5. 多层检索

### GraphRAG

1. 分块（按句子 + 重叠）
2. LLM 抽取实体和关系
3. 构建 NetworkX 图
4. 社区检测（Leiden/Louvain）
5. 社区摘要和层次聚合
6. 实体/社区检索 + 多跳遍历

---

## 高级参数

通过环境变量或修改 `config.py` 调整：

### RAPTOR 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `RAPTOR_CHUNK_SIZE` | 1000 | 每个分块的词数 |
| `RAPTOR_CHUNK_OVERLAP` | 200 | 分块重叠词数 |
| `RAPTOR_TREE_DEPTH` | 3 | 树的最大深度 |
| `RAPTOR_SUMMARY_LENGTH` | 200 | 摘要词数 |
| `RAPTOR_TEMPERATURE` | 0.1 | LLM 温度 |

### GraphRAG 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `GRAPHRAG_CHUNK_SIZE` | 1200 | 每个分块的词数 |
| `GRAPHRAG_CHUNK_OVERLAP` | 100 | 分块重叠词数 |
| `GRAPHRAG_MAX_TRIPLES` | 10 | 每块最大三元组数 |
| `GRAPHRAG_COMMUNITY_ALG` | leiden | 社区检测算法 |

---

## 性能与排错

### 常见问题

1. **内存不足**
   - 减小 `chunk_size`
   - 分段处理文档
   - 使用较小的嵌入模型

2. **索引构建慢**
   - 使用更快/更小的 LLM
   - 减少 `tree_depth` 或 `max_triples`
   - 启用缓存

3. **检索效果差**
   - 调整 `chunk_size` 和 `overlap`
   - 优化聚类参数
   - 改进实体抽取提示词

4. **API 错误**
   - 检查根目录 `.env` 中的 API 密钥
   - 监控限流
   - 验证索引是否存在

---

## 集成使用

作为后端与 Agentic RAG 系统集成：

```python
from llm.client import get_llm_client
from chapter3.structured_index.config import get_raptor_config
from chapter3.structured_index.raptor_indexer import RaptorIndexer

# 获取配置（自动使用 .env 中的 LLM 设置）
config = get_raptor_config()
raptor = RaptorIndexer(config)

# 构建和查询
raptor.build_index(document_text)
results = raptor.search("SSE 指令", top_k=5)
```

---

## 扩展开发

### 添加新文档类型

扩展 `DocumentProcessor` 类：

```python
def process_new_format(self, file_path: Path) -> str:
    # 实现新格式处理
    pass
```

### 自定义实体抽取

修改 `GraphRAGIndexer.extract_entities_relationships()` 中的提示词。

### 替换聚类算法

在 `RaptorIndexer.cluster_nodes()` 中替换 GMM。

---

## 参考资料

- [RAPTOR 论文](https://arxiv.org/abs/2401.18059)
- [GraphRAG (Microsoft)](https://github.com/microsoft/graphrag)
- [Intel SDM](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html)
- [项目规范文档](../../../CONVENTION.md)

---

## 迁移说明

本项目已从 `ai-agent-book` 迁移到 `ai-agant`，主要变更：

1. **LLM 配置统一**：使用项目根目录的 `.env` 和 `llm.client` 模块
2. **提示词中文化**：所有用户可见内容已翻译为中文
3. **依赖精简**：核心依赖由根目录统一管理
4. **路径适配**：添加了自动路径处理，确保正确导入模块

从原项目迁移的代码已按照 [CONVENTION.md](../../../CONVENTION.md) 规范进行适配。
