# 上下文压缩策略对比实验

> 《AI Agent 深度解析》第 2 章 - 实验 2-9 ★★★：上下文压缩策略对比

本实验演示并对比多种 LLM Agent 上下文压缩策略，通过查找 OpenAI 联合创始人当前归属的研究任务来测试不同策略的效果。

---

## 📋 目录

- [概述](#概述)
- [为什么需要上下文压缩](#为什么需要上下文压缩)
- [压缩策略](#压缩策略)
- [安装](#安装)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [实验结果](#实验结果)
- [配置说明](#配置说明)
- [扩展开发](#扩展开发)

---

## 概述

随着上下文窗口越来越大（128K+），高效的上下文管理对于以下方面至关重要：

- **成本** - 减少 token 使用量
- **性能** - 降低延迟
- **可靠性** - 减少溢出错误
- **相关性** - 保留重要信息

本实验实现并对比 **6 种**压缩策略及其权衡。

---

## 为什么需要上下文压缩

### 问题场景

在多轮对话和复杂任务中，Agent 会：

1. 调用多个工具（如网络搜索）
2. 累积大量上下文（网页内容、工具结果）
3. 快速消耗 token 预算
4. 可能超出模型上下文窗口限制

### 解决方案

通过智能压缩，可以：
- 保留关键信息，删除冗余
- 聚焦于当前任务的相关内容
- 平衡细节与效率

---

## 压缩策略

### 策略对比

| # | 策略 | 描述 | 优点 | 缺点 |
|---|------|------|------|------|
| 1 | 无压缩 | 返回原始内容 | 无信息丢失 | 快速溢出 |
| 2 | 逐页摘要 | 每页单独摘要 | 保留页内细节 | 可能丢失跨页关联 |
| 3 | 合并摘要 | 全部合并后摘要 | 全局视角好 | 可能丢失页级归属 |
| 4 | 上下文感知 | 基于查询聚焦摘要 | 相关性最高 | 额外 LLM 调用 |
| 5 | 带引用 | 包含来源链接 | 便于追问验证 | 上下文略大 |
| 6 | 窗口化 | 保留最新，压缩历史 | 细节与效率平衡 | 需要阈值管理 |

### 详细说明

#### 1. 无压缩 (NO_COMPRESSION)

直接将网页原文放入上下文。

- **预期**：几次工具调用后溢出失败
- **用途**：展示基线问题

#### 2. 非上下文感知 - 逐页摘要 (NON_CONTEXT_AWARE_INDIVIDUAL)

每页单独用 LLM 摘要，然后拼接。

- **优点**：保留页内细节
- **缺点**：多次 LLM 调用，可能丢失跨页关联
- **适用**：来源彼此独立时

#### 3. 非上下文感知 - 合并摘要 (NON_CONTEXT_AWARE_COMBINED)

先拼接全部网页，再做一次总摘要。

- **优点**：全局视角更好
- **缺点**：可能丢失页级归属
- **适用**：页数不多时

#### 4. 上下文感知摘要 (CONTEXT_AWARE)

结合原始查询对全部搜索结果做聚焦摘要。

- **优点**：相关性更高
- **缺点**：额外的 LLM 调用

#### 5. 带引用的上下文感知 (CONTEXT_AWARE_CITATIONS)

在策略 4 基础上增加引用和来源链接。

- **优点**：便于追问和验证
- **缺点**：上下文略大

#### 6. 窗口化上下文 (WINDOWED_CONTEXT)

最新一次工具调用保留全文，更早历史压缩。

- **优点**：细节与效率平衡
- **实现**：只在上下文超过 80% 阈值时压缩未标记的消息

---

## 安装

### 环境要求

- Python 3.8+
- 已配置 LLM（见项目根目录 `.env`）

### 安装步骤

```bash
cd chapter2/context_compression

# 安装依赖（如需要）
pip install -r requirements.txt

# 确保根目录 .env 已配置
# LLM 配置在 /ai-agant/.env 中统一管理
```

### LLM 配置

本实验使用项目统一的 LLM 配置（`/ai-agant/.env`）：

```bash
# 根目录 .env 配置示例
API_KEY=your-api-key
LLM_PROVIDER=kimi
LLM_MODEL=kimi-k3
BASE_URL=
```

### 可选配置

```bash
# 搜索 API（可选，无 Key 时使用模拟数据）
SERPER_API_KEY=your-serper-key
```

获取免费 Serper API Key: https://serper.dev

---

## 快速开始

### 方式一：运行完整实验

```bash
# 运行所有 6 种策略并生成对比表
python experiment.py

# 仅运行特定策略
python experiment.py -s context_aware

# 运行多个策略
python experiment.py -s individual combined

# 指定输出文件
python experiment.py -o results/my_experiment.json
```

### 方式二：交互式演示

```bash
# 交互选择策略
python main.py

# 直接指定策略
python main.py -s citations

# 禁用流式输出
python main.py -s windowed --no-streaming
```

### 方式三：列出可用策略

```bash
python experiment.py --list-strategies
python main.py --list-strategies
```

---

## 项目结构

```
context_compression/
├── README.md                   # 本文档
├── requirements.txt            # 依赖列表
├── config.py                   # 配置管理
├── compression_strategies.py   # 压缩策略实现
├── agent.py                    # 研究 Agent
├── web_tools.py                # 网页工具
├── experiment.py               # 自动对比实验
├── main.py                     # 交互式演示
├── results/                    # 实验结果目录
│   └── experiment_*.json
└── logs/                       # 日志目录
```

---

## 实验结果

### 典型结果对比

以下是基于 `kimi-k3` 模型（128K 预算）的实测结果：

| # | 策略 | 成功 | 迭代次数 | Tokens | 压缩率 | 溢出次数 | 耗时 |
|---|------|------|----------|--------|--------|----------|------|
| 1 | no_compression | ❌ | 5 | 166,043 | 102.1% | 1 | 107s |
| 2 | individual_summary | ✅ | 12 | 276,608 | 10.9% | 4 | 2980s |
| 3 | combined_summary | ✅ | 10 | 93,449 | 4.3% | 0 | 1189s |
| 4 | context_aware | ✅ | 7 | **40,157** | **3.0%** | 0 | 967s |
| 5 | citations | ✅ | 10 | 222,992 | 4.1% | 3 | 1235s |
| 6 | windowed | ✅ | 7 | 174,601 | 102.4% | 4 | **867s** |

### 结论

- **无压缩**按设计在超过 128K 时失败（约第 5 轮）
- **上下文感知摘要（#4）**在 token 效率上最优
- **窗口化（#6）**在总耗时上最短，适合长对话
- 单次运行的绝对值会波动，**相对排序是关键**

---

## 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MAX_ITERATIONS` | 50 | 最大迭代次数 |
| `MAX_WEBPAGE_LENGTH` | 50000 | 网页内容最大长度 |
| `SUMMARY_MAX_TOKENS` | 500 | 摘要最大 token 数 |
| `CONTEXT_WINDOW_SIZE` | 128000 | 上下文窗口大小（故意收紧） |
| `ENABLE_VERBOSE` | false | 详细日志输出 |

### 命令行参数

#### experiment.py

| 参数 | 说明 |
|------|------|
| `-s, --strategy` | 指定策略（可多个） |
| `-n, --max-iterations` | 最大迭代次数 |
| `--streaming` | 启用流式输出 |
| `-o, --output` | 输出 JSON 文件 |
| `--list-strategies` | 列出所有策略 |

#### main.py

| 参数 | 说明 |
|------|------|
| `-s, --strategy` | 指定策略 |
| `-n, --max-iterations` | 最大迭代次数 |
| `--no-streaming` | 禁用流式输出 |
| `-o, --output` | 保存结果到文件 |
| `--list-strategies` | 列出所有策略 |

---

## 扩展开发

### 添加新策略

1. 在 `CompressionStrategy` 枚举中添加新策略
2. 在 `ContextCompressor` 中实现压缩方法
3. 在 `compress_search_results` 中添加路由

```python
class CompressionStrategy(Enum):
    MY_NEW_STRATEGY = "my_new_strategy"

def _my_new_strategy(self, search_results, query, context):
    # 实现压缩逻辑
    pass
```

### 更改研究任务

修改 `agent.py` 中的系统提示：

```python
def _init_system_prompt(self):
    # 修改任务描述
    self.conversation_history = [{
        "role": "system",
        "content": "你的新任务描述..."
    }]
```

### 添加新工具

在 `_get_tools_description()` 中添加工具定义，并在 `_execute_tool()` 中实现。

---

## 技术要点

### 统一 LLM 客户端

本实验遵循项目规范，使用统一的 LLM 客户端：

```python
from llm.client import get_llm_client

client = get_llm_client()
```

### 推理模型兼容

自动适配推理模型（Kimi K3、GPT-5）的特殊参数：

- `temperature` 固定为 1.0
- `max_tokens` 增加推理预算

### 窗口化压缩

仅在上下文使用超过 80% 阈值时触发，避免频繁压缩。

使用 `[已压缩]` 标记确保每条消息只压缩一次。

---

## 故障排除

### 无 Serper API Key

- 会自动使用模拟数据
- 仍可验证压缩逻辑

### 非基线策略仍溢出

- 降低 `MAX_WEBPAGE_LENGTH`
- 降低 `SUMMARY_MAX_TOKENS`
- 减少搜索结果数量

### 运行缓慢

- 使用 `--no-streaming`
- 减小 `--max-iterations`
- 使用模拟搜索（无 Serper Key）

---

## 参考资料

- [项目规范文档](../../../CONVENTION.md)
- [LLM 客户端文档](../../../llm/client.py)
- [Serper API 文档](https://serper.dev)

---

## 许可

本实验代码遵循项目根目录的 LICENSE。
