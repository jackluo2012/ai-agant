# 论文转 PPT（提议者-审核者机制）

基于论文自动生成演示文稿的实验项目，演示"提议者-审核者"（Proposer-Reviewer）双 Agent 分工机制，与单 Agent 自审方案进行对比。

## 功能概述

本项目实现了一个完整的 PPT 自动生成流程：

- **双 Agent 方案**：Proposer 负责生成 Slidev 代码，Reviewer 负责渲染 PNG 并使用 Vision LLM 审查，输出结构化改进建议
- **单 Agent 方案**：同一个 Agent 负责生成、渲染、自审和修订
- **独立评委**：使用统一的 Vision rubric 对两种方案的最终结果进行质量评分
- **Token 对比**：统计并对比两种方案的上下文 token 消耗

## 核心设计

### 提议者-审核者分工

| 角色 | 职责 | 上下文内容 |
|------|------|------------|
| **Proposer**（文本模型） | 读论文 → 规划页面 → 生成/修订 `slides.md` | 论文正文 + 累积的结构化文字反馈（不含图片） |
| **Reviewer**（视觉模型） | 看最新渲染截图 → 输出结构化建议 JSON | 每轮全新调用，只看最新截图 |

### 关键优势

- Proposer 全程不看图片，上下文仅累积文本
- Reviewer 每轮独立调用，不存在上下文膨胀问题
- 相比单 Agent 自审（图片在同一上下文累积），上下文峰值显著更小

## 快速开始

### 1. 环境准备

确保已安装：
- Python 3.8+
- Node.js 16+（用于 Slidev 渲染）
- 项目虚拟环境（`.venv`）

### 2. 安装依赖

```bash
# 进入项目根目录
cd ai-agant

# 激活虚拟环境
source .venv/bin/activate

# 安装实验特定依赖
pip install -r chapter5/paper-to-ppt/requirements.txt

# 安装 Node.js 依赖（Slidev + 渲染工具）
cd chapter5/paper-to-ppt
npm install
```

### 3. 配置 LLM

在**项目根目录**（`ai-agant/.env`）中配置 LLM：

```bash
API_KEY=your-api-key
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
```

> 注意：视觉模型必须支持图像输入（如 `gpt-4o`、`claude-sonnet-4-20250514`）

### 4. 运行

```bash
# 从项目根目录运行
cd ai-agant
source .venv/bin/activate
python3 chapter5/paper-to-ppt/demo.py
```

## 使用方法

### 完整运行

```bash
# 同时运行两种方案并对比
python3 chapter5/paper-to-ppt/demo.py
```

### 快速测试

```bash
# 仅验证 Slidev 渲染链路（不调用 LLM）
python3 chapter5/paper-to-ppt/demo.py --smoke

# 离线走通完整闭环（脚本化内容，不调用 LLM）
python3 chapter5/paper-to-ppt/demo.py --dry-run

# 单轮真实 LLM 测试
python3 chapter5/paper-to-ppt/demo.py --mode dual --max-rounds 1
```

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--paper PATH` | 输入论文路径（默认 `paper/sample_paper.md`） |
| `--out-dir DIR` | 输出目录（默认 `output/`） |
| `--text-model NAME` | 覆盖文本模型 |
| `--vision-model NAME` | 覆盖视觉模型 |
| `--mode {both,dual,single}` | 运行模式（默认 `both`） |
| `--max-rounds N` | 最大迭代轮数（默认 3） |
| `--smoke` | 仅验证渲染链路 |
| `--dry-run` | 离线演示闭环 |

## 项目结构

```
chapter5/paper-to-ppt/
├── agents.py              # Proposer / Reviewer Agent 实现
├── demo.py                # 主入口
├── renderer.py            # Slidev 渲染器
├── make_figures.py        # 图表生成
├── package.json           # Node.js 依赖
├── requirements.txt       # Python 特定依赖
├── paper/                 # 论文文件目录
│   └── sample_paper.md
├── output/                # 运行产物（slides.md、review.json）
├── slidev_workspace/      # Slidev 工作区
│   ├── public/            # 图片资源
│   └── exports/           # 渲染 PNG 输出
├── results/               # 结果输出目录
└── logs/                  # 日志目录
```

## 配置说明

### LLM 配置（项目根目录 .env）

在 `ai-agant/.env` 中配置：

```bash
# 必需配置
API_KEY=your-api-key
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o

# 可选配置
BASE_URL=https://api.openai.com/v1
```

### 环境变量覆盖

可通过环境变量覆盖模型选择：

```bash
export TEXT_MODEL=gpt-4o
export VISION_MODEL=claude-sonnet-4-20250514
```

## 输出说明

### output/ 目录

- `dual_roundN_slides.md` - 双 Agent 第 N 版 slides.md
- `dual_roundN_review.json` - Reviewer 审查结果
- `single_roundN_slides.md` - 单 Agent 第 N 版 slides.md
- `comparison_summary.json` - 完整对比结果

### slidev_workspace/exports/ 目录

- `dual_roundN/` - 双 Agent 渲染 PNG
- `single_roundN/` - 单 Agent 渲染 PNG

## 审查标准

Reviewer 按以下标准审查：

- `text_overflow`：文字溢出/被裁切
- `overcrowded`：内容过多/过于拥挤
- `image_size`：图片尺寸不合适
- `readability`：字号过小、对比度差
- `layout`：对齐混乱、比例失衡

每条问题包含：页码、类型、严重程度（high/medium/low）、具体建议。

## 故障排除

### Slidev 渲染失败

```bash
# 重新安装 Node.js 依赖
cd chapter5/paper-to-ppt
rm -rf node_modules package-lock.json
npm install

# 安装 Chromium 浏览器
npx playwright install chromium
```

### LLM 调用失败

检查项目根目录 `.env` 配置：

```bash
# 验证配置
cat ai-agant/.env | grep API_KEY
cat ai-agant/.env | grep LLM_PROVIDER
```

### 模块导入错误

确保从项目根目录运行，或设置 PYTHONPATH：

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 chapter5/paper-to-ppt/demo.py
```

## 技术要点

### 为什么要"渲染出来再看"

Agent 写完 Slidev 代码时并不知道实际渲染效果——内容会不会太挤、文字会不会溢出、图片尺寸是否合适。只有真正渲染成像素才能看出问题。Reviewer 接触到的是 Proposer 看不到的新信息。

### 第一版为什么故意写得很挤

为了稳定复现"渲染→发现问题→修订"的闭环，Proposer 的首版会把整篇论文塞进约 4 页，会产生真实的溢出和裁切。Reviewer 的问题都是视觉模型看真实像素得出的。

## 局限性

- **审美主观**：Reviewer 的偏好未必等于用户偏好
- **图表来源**：本实验不解析真实 PDF，图表由程序复现
- **成本/时长**：每轮 Reviewer 需要发送约 10 张截图给视觉模型
- **确定性**：LLM 与 Vision 判定有随机性
