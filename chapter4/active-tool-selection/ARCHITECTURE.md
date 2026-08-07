# 架构深入解析

本文档详细解释主动工具选择系统的架构，受 MCP-Zero 启发。

## 目录

1. [系统概述](#系统概述)
2. [核心组件](#核心组件)
3. [主动发现流程](#主动发现流程)
4. [语义路由算法](#语义路由算法)
5. [主动 vs 被动对比](#主动-vs-被动对比)
6. [性能优化](#性能优化)
7. [设计决策](#设计决策)

## 系统概述

主动工具选择系统由四个协作的主要组件组成：

```
┌─────────────────────────────────────────────────────────┐
│                    用户任务                              │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│              主动工具代理                                │
│  • 任务分析                                             │
│  • 能力缺口识别                                         │
│  • 结构化工具请求生成                                   │
│  • 工具使用和任务执行                                   │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│          分层语义路由器                                  │
│  阶段 1: 服务器级路由（平台匹配）                       │
│  阶段 2: 工具级路由（操作匹配）                         │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│            工具知识库                                    │
│  8 个服务器 × 40+ 工具                                  │
│  按域/平台组织                                          │
└─────────────────────────────────────────────────────────┘
```

## 核心组件

### 1. 主动工具代理 (`agent.py`)

代理负责：

#### 任务分析
```python
def execute_task(self, task: str):
    # 1. 初始化空工具集
    self.available_tools = []

    # 2. 分析任务以识别能力需求
    # 3. 生成结构化工具请求
    # 4. 迭代发现和加载工具
    # 5. 使用发现的工具执行任务
```

#### 工具请求生成

代理生成以下格式的结构化请求：

```xml
<tool_request>
server: [平台/域描述]
tool: [操作描述]
</tool_request>
```

**示例：**
```xml
<tool_request>
server: GitHub 用于代码仓库操作
tool: 按关键字和过滤器搜索仓库
</tool_request>
```

#### 迭代发现

代理可以随着理解深化进行多次工具请求：

```python
# 迭代 1: 识别基本需求
请求: "GitHub 仓库访问"
→ 加载: github_search_repos, github_list_issues

# 迭代 2: 识别额外需求
请求: "用于本地存储的文件系统操作"
→ 加载: fs_read_file, fs_write_file

# 迭代 3: 识别分析需求
请求: "数据可视化和统计"
→ 加载: analytics_summarize, analytics_visualize
```

### 2. 语义路由器 (`semantic_router.py`)

实现两阶段分层路由：

#### 阶段 1: 服务器级路由

将工具请求匹配到相关服务器（平台）：

```python
def _route_to_servers(self, request: str, top_k: int):
    # 1. 使用 TF-IDF 向量化请求
    request_vector = self.server_vectorizer.transform([request])

    # 2. 计算与所有服务器的余弦相似度
    similarities = cosine_similarity(request_vector, self.server_embeddings)

    # 3. 按相似度返回前 K 个服务器
    top_indices = np.argsort(similarities)[::-1][:top_k]
    return [(self.servers[idx], similarities[idx]) for idx in top_indices]
```

**为什么有效：**
- 将搜索空间从所有工具减少到相关服务器的工具
- 平台/域匹配是粗粒度且可靠的
- 示例："GitHub" 请求 → GitHub 服务器（而非文件系统服务器）

#### 阶段 2: 工具级路由

在选定服务器内将请求匹配到特定工具：

```python
def _route_to_tools(self, server: ServerDefinition, request: str, top_k: int):
    # 1. 获取服务器专用向量器和嵌入
    vectorizer = self.tool_vectorizers[server.name]
    tool_embeddings = server._tool_embeddings

    # 2. 向量化请求
    request_vector = vectorizer.transform([request])

    # 3. 计算与此服务器中工具的相似度
    similarities = cosine_similarity(request_vector, tool_embeddings)

    # 4. 返回前 K 个工具
    top_indices = np.argsort(similarities)[::-1][:top_k]
    return [(server.tools[idx], similarities[idx]) for idx in top_indices]
```

**为什么有效：**
- 在相关域内的细粒度匹配
- 工具描述比服务器描述更具体
- 示例："搜索仓库" → github_search_repos（而非 github_create_issue）

#### 分数组合

最终工具分数组合两个阶段：

```python
combined_score = 0.3 * server_score + 0.7 * tool_score
```

**原理：**
- 服务器分数（30%）：确保工具来自相关域
- 工具分数（70%）：优先考虑操作级匹配
- 加权组合防止跨域误报

### 3. 工具知识库 (`tool_knowledge_base.py`)

分层组织：

```
知识库
├── GitHub 服务器
│   ├── github_search_repos
│   ├── github_create_pr
│   ├── github_list_issues
│   ├── github_get_file
│   └── github_create_issue
├── 文件系统服务器
│   ├── fs_read_file
│   ├── fs_write_file
│   ├── fs_list_directory
│   ├── fs_delete_file
│   └── fs_search_files
├── 数据库服务器
│   ├── db_query
│   ├── db_insert
│   ├── db_update
│   ├── db_delete
│   └── db_schema
└── ...（另外 5 个服务器）
```

**设计原则：**

1. **分层组织**：工具按平台/域分组
2. **丰富描述**：服务器和工具都有语义描述
3. **标准模式**：OpenAI 函数调用格式
4. **可扩展**：易于添加新服务器/工具

### 4. 配置 (`config.py`)

所有组件的集中配置：

```python
# LLM 设置（现在在项目根目录 .env 中）
# API_KEY 由统一 LLM 客户端管理

# 路由阈值
SIMILARITY_THRESHOLD = 0.15  # 匹配的最小相似度
TOP_K_SERVERS = 3            # 要搜索的服务器
TOP_K_TOOLS = 5              # 每个服务器的工具

# 代理限制
MAX_TOOL_REQUESTS = 5        # 最大发现迭代次数
AGENT_TEMPERATURE = 0.7      # LLM 温度
```

## 主动发现流程

主动工具发现的详细流程：

```
┌─────────────────────────────────────────────────────────┐
│ 步骤 1: 任务提交                                        │
│ 用户: "在 GitHub 上搜索 Python ML 仓库"                │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 步骤 2: 任务分析（代理）                                │
│ • 识别仓库搜索能力需求                                  │
│ • 当前工具: 无                                          │
│ • 决策: 请求 GitHub 工具                                │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 步骤 3: 工具请求生成                                    │
│ <tool_request>                                          │
│   server: GitHub 用于仓库操作                           │
│   tool: 按关键字搜索仓库                                │
│ </tool_request>                                        │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 步骤 4: 语义路由                                        │
│ 阶段 1: 服务器路由                                      │
│   • github: 0.89 ✓                                     │
│   • filesystem: 0.12                                    │
│   • web: 0.24                                          │
│                                                         │
│ 阶段 2: 工具路由（GitHub 服务器）                       │
│   • github_search_repos: 0.94 ✓                       │
│   • github_list_issues: 0.45                           │
│   • github_get_file: 0.31                              │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 步骤 5: 工具加载                                        │
│ 已加载: [github_search_repos]                           │
│ 可用工具数: 1                                           │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 步骤 6: 任务执行                                        │
│ 代理使用 github_search_repos 完成任务                   │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 步骤 7: 响应                                            │
│ 结果返回给用户                                          │
│ 指标: 1 个工具加载，约 2000 tokens 使用                  │
└─────────────────────────────────────────────────────────┘
```

### 多迭代示例

需要多次工具发现迭代的复杂任务：

```
任务: "克隆仓库、分析代码、可视化指标、邮件报告"

迭代 1:
  分析: 需要 GitHub 访问
  请求: GitHub 仓库操作
  已加载: github 工具（2 个工具）

迭代 2:
  分析: 需要文件系统用于代码存储
  请求: 文件系统操作
  已加载: 文件系统工具（共 3 个工具）

迭代 3:
  分析: 需要分析工具进行代码分析
  请求: 数据分析和可视化
  已加载: 分析工具（共 5 个工具）

迭代 4:
  分析: 需要通信工具发送邮件
  请求: 邮件通信
  已加载: 通信工具（共 6 个工具）

执行: 使用所有 6 个工具完成任务
```

## 语义路由算法

### TF-IDF 向量化

使用 TF-IDF 将工具和请求转换为向量：

```python
# 从所有工具描述构建词汇表
vectorizer = TfidfVectorizer(stop_words='english')

# 服务器描述
server_docs = [f"{s.name} {s.description}" for s in servers]
server_matrix = vectorizer.fit_transform(server_docs)

# 工具描述（每个服务器）
tool_docs = [f"{t.name} {t.description}" for t in tools]
tool_matrix = vectorizer.fit_transform(tool_docs)
```

**什么是 TF-IDF？**

- **TF（词频）**: 词在文档中出现的频率
- **IDF（逆文档频率）**: 词在整个文档集中的稀有程度
- **TF-IDF**: 在文档中频繁但整体稀有的词获得高分

**示例：**
```
服务器: "GitHub 仓库管理和版本控制"
工具: "按关键字搜索仓库"
请求: "查找 GitHub 仓库"

TF-IDF 向量捕获语义重叠:
- "repository" 出现在三者中 → 中等权重
- "GitHub" 出现在服务器和请求中 → 强匹配
- "search" 出现在工具和请求中 → 强匹配
```

### 余弦相似度

测量向量之间的相似度：

```python
similarity = cosine_similarity(request_vector, tool_vector)
# 返回 0（正交）到 1（相同）之间的值
```

**几何解释：**
```
如果向量指向相同方向 → 相似（分数接近 1）
如果向量垂直 → 不相似（分数接近 0）
```

**示例分数：**
```
请求: "搜索仓库"
  • github_search_repos: 0.92（强匹配）
  • github_create_pr: 0.31（弱匹配）
  • fs_read_file: 0.08（无匹配）
```

### 阈值过滤

低于相似度阈值的工具被过滤掉：

```python
SIMILARITY_THRESHOLD = 0.15

relevant_tools = [
    tool for tool, score in tool_scores
    if score >= SIMILARITY_THRESHOLD
]
```

**为什么是 0.15？**
- 精确度和召回率之间的平衡
- 捕获语义重叠而没有误报
- 通过测试经验确定

## 主动 vs 被动对比

### 被动工具注入（传统）

```python
class PassiveToolAgent:
    def __init__(self):
        # 初始化时加载所有工具
        self.all_tools = load_all_40_plus_tools()

    def execute_task(self, task):
        # 将所有工具模式注入提示词
        response = llm.complete(
            messages=[{"role": "user", "content": task}],
            tools=self.all_tools  # 40+ 工具模式
        )
```

**问题：**
1. **巨大上下文**：仅工具模式就需要 30k-50k tokens
2. **扩展性差**：添加 10 个工具使每个请求增加 5k tokens
3. **失去自主性**：代理从预定义集中选择
4. **认知过载**：LLM 必须处理无关工具

### 主动工具发现（MCP-Zero 方法）

```python
class ActiveToolAgent:
    def __init__(self):
        # 从空工具集开始
        self.available_tools = []

    def execute_task(self, task):
        # 按需迭代发现工具
        while not task_complete:
            # 代理识别能力缺口
            if need_more_tools:
                request = agent.generate_tool_request()
                new_tools = router.discover_tools(request)
                self.available_tools.extend(new_tools)
            else:
                # 使用可用工具
                execute_with_tools(self.available_tools)
```

**优势：**
1. **最小上下文**：2k-5k tokens（仅需要的工具）
2. **高效扩展**：添加 100 个工具不影响简单任务
3. **保持自主性**：代理控制能力获取
4. **专注处理**：LLM 只看到相关工具

### 性能对比表

| 指标 | 被动 | 主动 | 提升 |
|------|----------|--------|-------------|
| **初始工具** | 40 | 0 | 不适用 |
| **简单任务工具** | 40 | 2-3 | 减少 92-95% |
| **Tokens（简单任务）** | 45,000 | 2,500 | 减少 94% |
| **Tokens（复杂任务）** | 50,000 | 8,000 | 减少 84% |
| **扩展性** | O(n) | O(k) | k << n |
| **代理自主性** | 低 | 高 | 质量提升 |

其中：
- n = 生态系统中的工具总数
- k = 特定任务所需的工具

## 性能优化

### 1. 嵌入预计算

工具嵌入在初始化时计算一次：

```python
def __init__(self, servers):
    # 预计算所有嵌入
    self._build_server_index()
    self._build_tool_indices()

    # 查询时间：仅余弦相似度
    # 无需重新向量化
```

**优势**：O(1) 查询时间而非 O(n) 向量化

### 2. 分层搜索

两阶段路由降低复杂度：

```python
# 无层次：搜索所有 40 个工具
# 复杂度：O(40) 相似度比较

# 有层次：搜索 8 个服务器，然后前 3 个服务器
# 阶段 1: O(8) 服务器比较
# 阶段 2: 每个服务器 O(5) 工具比较 = O(15)
# 总计: O(8 + 15) = O(23)

# 节省: 40 - 23 = 17 次比较（减少 42%）
```

**扩展性更好**：
- 100 个工具，10 个服务器：100 vs 35 次比较（减少 65%）
- 1000 个工具，20 个服务器：1000 vs 120 次比较（减少 88%）

### 3. 缓存潜力

未来优化：缓存路由结果：

```python
# 缓存结构
routing_cache = {
    "搜索 GitHub 仓库": ["github_search_repos", ...],
    "读取本地文件": ["fs_read_file", ...]
}

# 缓存命中: O(1) 查找
# 缓存未命中: 回退到语义路由
```

## 设计决策

### 为什么用 TF-IDF 而非神经嵌入？

**选择**：TF-IDF 与余弦相似度

**考虑的替代方案**：
- Sentence-BERT 嵌入
- OpenAI 嵌入（text-embedding-ada-002）

**原理**：
1. **教育清晰性**：TF-IDF 更易理解和调试
2. **无 API 调用**：离线工作无需额外成本
3. **足够性能**：工具描述是技术性和关键字丰富的
4. **快速**：无需模型推断

**神经嵌入更好时**：
- 自然语言查询（较少技术性）
- 语义细微差别重要
- 有同义词的大型语料库

### 为什么用两阶段路由？

**考虑的替代方案**：
- 所有工具的平面搜索
- 基于聚类的搜索
- 检索增强生成（RAG）

**原理**：
1. **匹配心智模型**：用户思考 "GitHub" → "搜索仓库"
2. **减少误报**：单独 "search" 可能匹配错误的域
3. **提高精确度**：服务器上下文缩小工具搜索
4. **可扩展**：对数复杂度 vs 线性

### 为什么用结构化请求？

**格式**：
```xml
<tool_request>
server: [域]
tool: [操作]
</tool_request>
```

**考虑的替代方案**：
- 自由格式自然语言
- JSON 格式
- 函数调用

**原理**：
1. **显式结构**：服务器 + 工具分解匹配路由阶段
2. **易于解析**：简单字符串匹配
3. **LLM 友好**：清晰格式减少歧义
4. **语义对齐**：请求格式匹配知识库组织

### 为什么模拟工具执行？

**决策**：工具返回模拟结果而非真实执行

**原理**：
1. **教育重点**：演示发现而非执行
2. **安全性**：无真实 API 调用或文件操作
3. **可移植性**：无外部依赖即可工作
4. **简单性**：专注于架构而非集成

**未来增强**：连接真实 API 用于生产

### 为什么 3 个服务器和 5 个工具？

**配置**：
```python
TOP_K_SERVERS = 3
TOP_K_TOOLS = 5
```

**原理**：
1. **平衡**：捕获相关工具而不淹没上下文
2. **经验**：在各种任务上测试，3×5=15 工具通常足够
3. **上下文窗口**：15 个工具模式 ≈ 3k-5k tokens（可管理）
4. **回退**：如果初始集不足可请求更多工具

**调优指南**：
- 简单任务：减少到 2×3 = 6 工具
- 复杂任务：增加到 5×7 = 35 工具
- 大型生态系统：保持比例，而非绝对数字

## 结论

主动工具选择架构表明：

1. **分层路由**在保持精确度的同时降低搜索复杂度
2. **主动发现**保持代理自主性并高效扩展
3. **迭代扩展**允许工具链随任务理解演进
4. **语义匹配**（即使使用简单的 TF-IDF）对工具发现效果良好

此架构代表了从被动工具注入到主动能力获取的根本转变，使代理能够在拥有数百或数千可用工具的生态系统中有效运行。
