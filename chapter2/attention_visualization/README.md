# 注意力机制可视化

> 《深入理解 AI Agent》第 2 章配套实验 —— 基于 llama.cpp 的 Token 置信度可视化

← [返回第 2 章目录](../README.md)

---

## 项目概述

本项目实现了基于 llama.cpp 的文本生成可视化工具，通过记录每个 token 的对数概率（logprob）来展示模型的置信度和推理过程。

### 功能特点

- **Token 置信度分析**：记录每个生成 token 的对数概率
- **Top-K 候选展示**：显示每个位置的前 N 个候选 token
- **概率分布曲线**：直观展示生成过程的概率变化
- **中文提示词**：所有示例和文档均为中文
- **独立 CLI 工具**：无需前端，直接生成可视化图表

---

## 快速开始

### 1. 环境准备

确保 llama.cpp 服务器正在运行：

```bash
# 检查服务器状态
curl http://192.168.1.158:11434/v1/models

# 服务器应返回可用模型列表
```

### 2. 安装依赖

```bash
cd chapter2/attention_visualization
pip install -r requirements.txt
```

### 3. 运行示例

#### 方式一：独立 CLI（推荐）

```bash
# 使用默认提示词
python attention_cli.py

# 自定义提示词
python attention_cli.py -p "北京今天的天气怎么样？"

# 指定输出文件
python attention_cli.py -p "解释什么是 AI" -o ai_viz.png

# 调整生成参数
python attention_cli.py -p "写一首关于春天的诗" --max-tokens 200 --temperature 0.9
```

#### 方式二：运行 Agent 演示

```bash
python agent.py
```

---

## CLI 使用说明

### 基本参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-p, --prompt` | 输入提示文本 | "北京今天的天气怎么样？" |
| `-o, --output` | 输出文件路径 | 自动生成 |
| `--max-tokens` | 最大生成 token 数 | 100 |
| `--temperature` | 采样温度 | 0.7 |
| `--top-logprobs` | 记录前 N 个候选 | 5 |

### 可视化选项

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--type` | 可视化类型：confidence/distribution/topk/all | all |
| `--cmap` | 颜色映射（如 viridis, plasma） | viridis |
| `--figsize` | 图表大小：宽,高 | 14,10 |
| `--no-display` | 仅保存，不显示图表 | - |

### 使用示例

```bash
# 生成所有类型的可视化
python attention_cli.py -p "什么是机器学习？" --type all

# 只生成置信度热力图
python attention_cli.py -p "25 乘以 37" --type confidence

# 使用不同配色方案
python attention_cli.py -p "你好" --cmap plasma
```

---

## 项目结构

```
attention_visualization/
├── agent.py              # 核心 Agent 实现
├── attention_cli.py      # 独立 CLI 工具
├── visualization.py      # 可视化工具
├── config.py             # 配置文件
├── requirements.txt      # Python 依赖
├── env.example           # 环境变量模板
├── results/              # 生成结果 JSON
├── visualizations/       # 可视化图表 PNG
└── README.md             # 本文档
```

---

## 输出说明

### JSON 结果文件

保存在 `results/` 目录，包含：

```json
{
  "timestamp": "2026-07-29T09:23:00",
  "category": "知识查询",
  "result": {
    "input_text": "北京今天的天气怎么样？",
    "output_text": "好的，用户问的是...",
    "token_info": [
      {
        "token": "好的",
        "logprob": -0.8634,
        "top_logprobs": [{"好的": -0.86}, {"嗯": -1.23}],
        "position": 0
      }
    ],
    "model": "MiniCPM5-1B-Q4_K_M.gguf",
    "temperature": 0.7
  }
}
```

### 可视化图表

1. **置信度热力图** (`*_confidence.png`)
   - 每个位置的 token 及其对数概率
   - 颜色越亮，置信度越高

2. **概率分布图** (`*_distribution.png`)
   - 上图：token 概率折线
   - 下图：对数概率折线

3. **Top-K 候选图** (`*_topk.png`)
   - 每个位置的前 N 个候选 token
   - 展示模型的其他可能选择

---

## 配置说明

复制 `env.example` 为 `.env` 并修改：

```bash
# llama.cpp 服务器配置
LLAMA_HOST=192.168.1.158
LLAMA_PORT=11434
MODEL_NAME=MiniCPM5-1B-Q4_K_M.gguf

# 生成参数
MAX_NEW_TOKENS=100
TEMPERATURE=0.7
TOP_P=0.9

# 可视化配置
VIZ_OUTPUT_DIR=visualizations
VIZ_COLORMAP=viridis
```

---

## 中文字体问题

**注意：** 由于 matplotlib 在 WSL/Linux 环境下对中文字体的支持不稳定，当前版本的可视化图表使用**英文标签**（如 "Token Confidence"、"Probability" 等），以确保图表可读性。

- 图表中的 token 内容（如 "你好"、"世界"）会正常显示中文
- 坐标轴、标题、图例等标签使用英文

如需完全使用中文标签，可以：
1. 安装中文字体：`sudo apt-get install fonts-noto-cjk`
2. 清除 matplotlib 缓存：`rm -rf ~/.cache/matplotlib`
3. 修改 `visualization.py` 中的标签文字

---

## 在代码中使用

```python
from agent import AttentionVisualizationAgent

# 初始化
agent = AttentionVisualizationAgent()

# 生成并记录
result = agent.generate_with_logprobs(
    prompt="什么是人工智能？",
    max_tokens=150,
    temperature=0.7,
    save_result=True,
    category="概念解释"
)

print(f"生成内容: {result.output_text}")
print(f"Token 数量: {len(result.output_tokens)}")

# 查看置信度
for info in result.token_info[:5]:
    print(f"{info.token}: logprob={info.logprob:.4f}")
```

---

## 批量可视化

```bash
# 使用可视化模块批量处理已有结果
python -c "
from visualization import batch_visualize_results
batch_visualize_results()
"
```

---

## 与原版区别

原 `ai-agent-book` 版本使用 Transformer 直接获取注意力权重。本项目基于 llama.cpp，采用以下替代方案：

| 原版 | 本项目 |
|------|--------|
| 完整注意力权重矩阵 | Token 级别的 logprobs |
| 多层/多头注意力 | Top-K 候选 token |
| 前端交互式展示 | 静态图表输出 |
| Qwen3-0.6B 本地模型 | MiniCPM5-1B 通过 llama.cpp |

---

## 故障排除

### 服务器连接失败

```bash
# 检查服务器是否运行
curl http://192.168.1.158:11434/v1/models

# 检查网络
ping 192.168.1.158
```

### 没有生成图表

检查 `visualizations/` 目录是否存在且有写入权限。

### 中文显示为方块

按照"中文字体问题"章节安装字体。

---

## 技术说明

### Logprob 含义

- **Logprob（对数概率）**：模型对该 token 的置信度
- **值越大**：模型越确定（通常在 -5 到 0 之间）
- **值越小**：模型越不确定

### 可视化解读

1. **高 logprob 值**：模型有把握
2. **低 logprob 值**：模型在探索
3. **均匀分布**：模型发散，可调低温度
4. **峰值集中**：模型收敛，可调高温度

---

## 下一步

- 尝试不同的中文提示词
- 调整温度观察概率分布变化
- 对比不同类别的置信度模式

---

## 许可

本项目与《深入理解 AI Agent》课程配套，供学习使用。
