# 实验 8-2：从 GAIA 轨迹提炼经验知识文档

本项目对应第八章"将经验沉淀为知识"。新版实验不再把一条成功轨迹压缩成 JSON 后直接做 RAG，而是先依据环境结果把轨迹标为成功、部分成功或失败，再比较同一任务族的多条路径，最后生成可检索的 Markdown 经验文档。

## 功能概述

- **跨轨迹经验归纳**：比较多条评估轨迹，提取可复用的经验知识
- **分级经验验证**：成功、部分成功、失败轨迹分别提炼不同类型的知识
- **Markdown 文档生成**：生成包含适用场景、推荐策略、常见误区、例外条件的结构化文档
- **三基线评估**：对比无经验、单轨迹摘要、知识文档三种模式的效果
- **真实 LLM 提取**：支持使用真实 LLM 从已评价运行中提取结构化经验

## 快速开始

### 1. 环境准备

确保项目根目录的 `.env` 文件中已配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3   # 可选
```

### 2. 安装依赖

```bash
# 激活虚拟环境
cd ai-agant
source .venv/bin/activate

# 进入项目目录
cd chapter8/gaia-experience

# 核心实验（离线，无需 API Key）
pip install -r requirements-lite.txt

# 完整实验（需要 AWorld 框架）
pip install -r requirements.txt
```

### 2.1 获取 AWorld 框架（完整实验需要）

AWorld 是 GAIA 基准测试的模拟环境框架，已加入 `.gitignore` 不包含在本仓库中。请按以下方式获取：

**方式一：直接克隆 GAIA 官方仓库**
```bash
# 在项目根目录执行
cd ai-agant/chapter8/gaia-experience
git clone https://github.com/facebookresearch/gaia.git temp_gaia
mv temp_gaia/AWorld AWorld
rm -rf temp_gaia
```

**方式二：符号链接（如果已有 GAIA 仓库）**
```bash
# 假设已有 GAIA 仓库在其他位置
ln -s /path/to/your/gaia/AWorld AWorld
```

**验证安装：**
```bash
python -c "import AWorld; print('AWorld 安装成功')"
```

### 2.2 获取 GAIA 验证数据集（可选）

`gaia-validation.jsonl` 是 GAIA 基准测试的验证数据，已加入 `.gitignore`。

**下载方式：**
```bash
# 从 GAIA 官方仓库下载
wget https://github.com/facebookresearch/gaia/raw/main/gaia-validation.jsonl

# 或使用 curl
curl -o gaia-validation.jsonl https://github.com/facebookresearch/gaia/raw/main/gaia-validation.jsonl
```

**或从官方发布页面获取：**
- 访问：https://github.com/facebookresearch/gaia/releases
- 下载 `gaia-validation.jsonl` 文件

### 3. 运行离线演示

```bash
# 使用固定数据运行完整演示
python demo_documents.py

# 使用真实 LLM 提取经验
export OPENAI_API_KEY=your_api_key_here
python demo_documents.py --extractor llm --model gpt-5.6
```

### 4. 运行完整 GAIA 实验

```bash
# 学习模式：从成功轨迹中沉淀经验
python run_with_experience.py --learning-mode --start 0 --end 10

# 应用模式：用已学到的经验解新题
python run_with_experience.py --apply-experience --start 10 --end 20

# A/B 对照：比较"无经验/有经验"的效果
python run_with_experience.py --compare --start 10 --end 20 --experience-db ./learned_experiences.json
```

## 使用方法

### 离线实验（推荐入门）

```bash
# 1. 运行离线演示
python demo_documents.py

# 2. 运行单元测试
python -m unittest -v test_experience_documents.py
```

### 在线实验（需要 API Key）

```bash
# 1. 设置环境变量
export OPENAI_API_KEY=your_api_key_here

# 2. 运行真实 LLM 提取
python demo_documents.py --extractor llm --model gpt-5.6

# 3. 查看生成的文档
ls output/experience_documents/
```

### 完整 GAIA 评估

```bash
# 1. 下载 GAIA 数据集
export GAIA_DATASET_PATH=./AWorld/examples/gaia/GAIA

# 2. 预加载知识库
python run_with_experience.py --preload-kb --start 0 --end 100

# 3. 学习模式（在部分题目上学习）
python run_with_experience.py --learning-mode --start 0 --end 50

# 4. 应用模式（在未见题目上测试）
python run_with_experience.py --apply-experience --start 50 --end 100
```

## 项目结构

```
chapter8/gaia-experience/
├── experience_documents.py      # 核心模块：跨轨迹归纳与 Markdown 生成
├── llm_extractor.py             # 真实 LLM 提取器
├── demo_documents.py            # 离线演示入口
├── test_experience_documents.py # 单元测试
├── run_with_experience.py       # AWorld 集成运行器
├── experience_agent.py          # AWorld 代理适配器
├── trajectory_summarizer.py    # 轨迹总结器
├── knowledge_base.py            # 知识库索引
├── llm_env.py                   # LLM 环境配置
├── real_gaia_campaign.py       # 真实 GAIA 活动脚本
├── config.yaml                  # 项目配置
├── requirements.txt             # 完整依赖
├── requirements-lite.txt        # 轻量依赖
├── env.template                 # 环境变量模板
├── README.md                    # 项目文档
├── QUICKSTART.md                # 快速入门指南
├── run.sh                       # 运行脚本
├── .gitignore                   # Git 忽略规则
│
├── results/                     # ❌ 已忽略：结果输出目录
├── logs/                        # ❌ 已忽略：日志目录
├── output/                      # ❌ 已忽略：输出目录
│
├── AWorld/                      # ❌ 已忽略：AWorld 框架（需单独获取）
├── validation/                  # ❌ 已忽略：实验验证结果
├── gaia-validation.jsonl        # ❌ 已忽略：GAIA 验证数据集（需单独下载）
└── sample_trajectories.json    # ❌ 已忽略：样例数据
```

**说明：** 标记 ❌ 的目录/文件已加入 `.gitignore`，不包含在版本控制中，需按上述说明单独获取。

## 配置说明

### 项目根目录 .env（LLM 配置）

```bash
# LLM 提供商配置
API_KEY=your-api-key
LLM_PROVIDER=kimi
LLM_MODEL=kimi-k3
```

### 项目配置 config.yaml

```yaml
# 学习模式配置
learning:
  enabled: true
  summarizer:
    model: "gpt-5.6-luna"
    temperature: 0.3

# 知识库配置
knowledge_base:
  enabled: true
  index:
    path: "./kb_index"
    embedding_model: "all-MiniLM-L6-v2"

# 经验应用配置
application:
  enabled: true
  strategy: "prompt_enhancement"
```

## API 说明

### ExperienceDocument

核心数据类，表示一个跨轨迹经验文档：

```python
from experience_documents import ExperienceDocument

doc = ExperienceDocument(
    task_family="web_research",
    capabilities=("search", "source_verification"),
    applies_when=("GAIA web-research tasks",),
    recommended_strategies=("验证答案使用主要来源",),
    common_pitfalls=("依赖单一来源",),
    exceptions=("事实为常识知识时",),
    sources=("task_001 (success, score=1.00)",),
    last_validated="2026-08-17"
)

# 生成 Markdown
markdown = doc.to_markdown()
```

### build_documents

从多条轨迹构建经验文档：

```python
from experience_documents import build_documents

trajectories = [
    {
        "id": "task_001",
        "task_family": "web_research",
        "environment_score": 1.0,
        "observed_strategies": ["使用主要来源验证"],
        "mistakes": [],
        "applies_when": ["需要外部验证的任务"],
        "exceptions": []
    }
]

documents = build_documents(trajectories)
```

## 故障排除

### 导入错误

```bash
# 确保从项目根目录运行
cd ai-agant
source .venv/bin/activate
python chapter8/gaia-experience/demo_documents.py
```

### FAISS 索引错误

```bash
# 重新构建索引
rm -rf ./kb_index
python run_with_experience.py --preload-kb
```

### LLM 调用失败

```bash
# 检查 API Key 配置
echo $OPENAI_API_KEY

# 使用离线模式测试
python demo_documents.py  # 默认使用固定数据
```

## 技术要点

### 经验提炼原则

1. **双轨迹支持**：推荐策略必须至少得到两条非失败轨迹的支持
2. **分级学习**：
   - 成功轨迹 → 正面策略
   - 失败轨迹 → 误区警示
   - 部分成功 → 细粒度分析
3. **来源可追溯**：每条经验都保留原始轨迹 ID，便于回查验证

### 三基线对比

| 模式 | 描述 | 迁移成功率 | 负迁移率 | 检索开销 |
|------|------|------------|----------|----------|
| 无经验 | 不使用任何历史经验 | 基线 | 0% | 0 字符 |
| 单轨迹摘要 | 直接检索单条轨迹摘要 | 中等 | 较高 | 中等 |
| 知识文档 | 检索跨轨迹归纳的文档 | 较高 | 较低 | 较大 |

### 文档结构

生成的 Markdown 文档包含：

- **适用场景**（applies_when）：经验适用的任务类型
- **推荐策略**（recommended_strategies）：经过验证的有效方法
- **常见误区**（common_pitfalls）：失败轨迹中提取的警示
- **例外条件**（exceptions）：不应应用该经验的情况
- **来源轨迹**（sources）：支持该经验的所有原始轨迹

## 相关文件

- `QUICKSTART.md` - 快速入门指南
- `env.template` - 环境变量模板
- `sample_trajectories.json` - 教学样例数据
