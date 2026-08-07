# 主动工具选择 (Active Tool Selection)

受 MCP-Zero 启发的 LLM 代理实验，演示按需主动发现工具相比传统被动注入的效率优势。

## 功能概述

- **主动工具发现**：代理按需请求工具，而非预先注入所有工具模式
- **语义路由**：分层语义匹配，精确定位相关工具
- **工具检索**：单次 RAG 风格检索，选择 top-k 相关工具
- **效率对比**：与传统被动注入方法进行全面对比

## 核心概念

### 三种工具选择策略

1. **被动注入 (Passive Injection)**
   - 预先将所有工具模式注入提示词
   - 巨大的上下文开销
   - 随工具数量增长而线性扩展

2. **工具检索 (Retrieval/RAG)**
   - 在第一次 LLM 调用前检索 top-k 相关工具
   - 无额外往返开销
   - 将"工具选择"转化为"知识检索"问题

3. **主动发现 (Active Discovery/MCP-Zero)**
   - 代理迭代地请求所需工具
   - 随任务理解深化而演进
   - 维持最小上下文占用

## 快速开始

### 1. 环境准备

确保项目根目录（`ai-agant/`）的虚拟环境已激活：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r chapter4/active-tool-selection/requirements.txt
```

### 3. 配置 LLM

在项目根目录的 `.env` 文件中配置 LLM 提供商：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3   # 可选，使用提供商默认模型
```

### 4. 运行演示

```bash
# 快速入门演示
python chapter4/active-tool-selection/quickstart.py

# 完整对比演示（需要 API）
python chapter4/active-tool-selection/demo_comparison.py

# 仅离线对比（无需 API）
python chapter4/active-tool-selection/demo_comparison.py --offline
```

## 使用方法

### 基本用法

```python
from agent import ActiveToolAgent

# 创建主动工具发现代理
agent = ActiveToolAgent()

# 执行任务
result = agent.execute_task("在 GitHub 上搜索星标超过 5000 的 Python Web 框架")

# 查看结果
print(f"使用的 tokens: {result['metrics']['tokens_used']}")
print(f"加载的工具: {result['tools_loaded']}")
print(f"响应: {result['response']}")
```

### 工具检索代理

```python
from agent import RetrievalToolAgent

# 创建检索代理，自动检索 top-5 相关工具
agent = RetrievalToolAgent(top_k=5)

result = agent.execute_task("分析销售数据并生成可视化")
```

### 被动注入代理（对比基线）

```python
from agent import PassiveToolAgent

# 创建被动代理，预先加载所有工具
agent = PassiveToolAgent()

result = agent.execute_task("发送邮件通知团队")
```

## 项目结构

```
chapter4/active-tool-selection/
├── agent.py              # 三种代理实现
├── config.py             # 项目配置
├── semantic_router.py    # 语义路由器
├── tool_knowledge_base.py # 工具知识库
├── quickstart.py         # 快速入门演示
├── demo_comparison.py    # 完整对比演示
├── benchmark.py          # 离线基准测试
├── examples.py           # 更多示例
├── requirements.txt      # 依赖列表
├── results/              # 结果输出目录
└── logs/                 # 日志目录
```

## 配置说明

### LLM 配置（项目根目录 .env）

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi
LLM_MODEL=kimi-k3
```

支持的 LLM 提供商：
- Kimi (`kimi`)
- SiliconFlow (`siliconflow`)
- 豆包 (`doubao`)
- DeepSeek (`deepseek`)
- OpenAI (`openai`)
- 自定义 (`custom`，需配置 `BASE_URL`)

### 项目配置

在 `config.py` 中可调整：

```python
AGENT_TEMPERATURE = 0.7      # LLM 温度
MAX_TOOL_REQUESTS = 5        # 最大工具请求次数
SIMILARITY_THRESHOLD = 0.15  # 相似度阈值
TOP_K_SERVERS = 3            # 搜索的服务器数量
TOP_K_TOOLS = 5              # 每个服务器返回的工具数量
```

## 效率对比

典型场景下的效率提升：

| 指标 | 被动注入 | 主动发现 | 工具检索 |
|------|----------|----------|----------|
| Token 使用 | 100% | 2-20% | 5-15% |
| 工具加载 | 全部 | 按需 | Top-K |
| API 调用 | 1 次 | 2-5 次 | 1 次 |
| 召回率 | 100% | 95%+ | 90%+ |

## 离线基准测试

运行无需 API 的离线对比：

```bash
python chapter4/active-tool-selection/demo_comparison.py --offline
```

输出示例：
```
╔════════════════════════════════════════════════════════════════════════════╗
║              Active Tool Selection — Strategy Comparison                    ║
╚════════════════════════════════════════════════════════════════════════════╝

+----------+------------------+---------------+-----------------------+
| Strategy | Tools in context | Schema tokens | Recall (gold reachable)|
+----------+------------------+---------------+-----------------------+
| all-tools|               38 |         4,812 |                  100% |
| retrieval|                5 |           633 |                   95% |
+----------+------------------+---------------+-----------------------+
```

## 技术要点

### 语义路由

采用分层两阶段算法：
1. **服务器级路由**：根据域/平台过滤候选服务器
2. **工具级路由**：在选定服务器内按语义相似度排序

使用 TF-IDF 向量化和余弦相似度计算。

### 工具请求格式

代理使用结构化格式请求工具：

```xml
<tool_request>
server: GitHub 用于代码仓库操作
tool: 搜索仓库
</tool_request>
```

### 迭代能力扩展

代理随任务理解深化逐步构建工具链：
- 初始：0 个工具
- 第一次请求：GitHub 工具
- 第二次请求：GitHub + 文件系统工具
- 第三次请求：GitHub + 文件系统 + 分析工具

## 故障排除

### ImportError: 无法导入 llm.client

确保项目根目录的 `.env` 文件配置正确，并且 `llm/` 模块存在。

### Token 计数为 0

某些 LLM 提供商不返回 token 使用信息，这是正常的。

### 工具未找到

检查任务描述是否清晰，语义路由可能需要更具体的描述。

## 参考文献

- MCP-Zero 论文: https://arxiv.org/pdf/2506.01056
- Anthropic 按需工具检索实验

## 许可证

本项目遵循原项目的许可证。
