# 实验 3-13：从结构化数据中提取隐性知识

> 配套《深入理解 AI Agent》第 3 章——以司法判例分析为例：因子发现 → 结构化抽取 → 案件原型聚类 → 对话式建议 Agent。

← [返回第 3 章目录](../README.md)

---

## 概述

本实验演示如何让 Agent 不把知识库当成"只能检索的静态仓库"，而是**先把数据读懂、从数据本身归纳出结构化的决策逻辑，再基于这套逻辑回答问题**。

以三类罪名（盗窃罪 / 故意伤害罪 / 诈骗罪）的判例为例，完整走通四段流水线：

```
判例文本 ──①自下而上因子发现──▶ 模块化 schema（核心+各罪名扩展）
                                        │
                            ②结构化抽取（用发现的 schema 抽因子）
                                        │
                            ③各罪名内聚类 ──▶ 案件原型 + 层次因子重要性
                                        │
        新案情 ──④对话 Agent（匹配最近原型、按重要性追问、给出建议）◀──┘
```

### 核心创新

与"预定义僵化 schema + 回归黑箱"的做法相反，本实验的两个关键创新是：
- **因子不预设、由 LLM 从数据里自由归纳**
- **判决经验不靠回归拟合刑期、而靠聚类出可解释的案件原型**

---

## 安装

### 前置条件

本项目已迁移到 `ai-agant` 统一项目结构，使用项目根目录的 LLM 配置。

```bash
# 确保在项目根目录
cd /path/to/ai-agant

# 安装依赖
pip install -r chapter3/structured-knowledge-extraction/requirements.txt
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

```bash
# 从项目根目录运行（推荐）
python chapter3/structured-knowledge-extraction/demo.py
```

### 运行流程

`demo.py` 会依次执行四个阶段：

1. **阶段 1：自下而上因子发现**
   - 让 LLM 自由归纳因子
   - 归并成模块化 schema（核心+各罪名扩展）

2. **阶段 2：结构化抽取**
   - 用发现的 schema 从每条判例抽取因子
   - 带缓存，一次性抽取后重跑几乎免费

3. **阶段 3：聚类成案件原型 + 层次因子重要性**
   - 把因子向量聚成「案件原型」
   - 计算全局与原型内因子重要性

4. **阶段 4：对话式量刑建议 Agent**
   - 把新案情匹配到最近原型
   - 按重要性追问缺失因子
   - 给出基于数据的建议

### 可选：重新生成数据

```bash
python chapter3/structured-knowledge-extraction/generate_data.py
```

---

## 运行输出示例

```
阶段 1 自下而上发现的 schema：
  核心通用因子: prior_record 前科 / self_surrender 自首 / compensation 赔偿 /
               guilty_plea 认罪认罚 / victim_reconciliation 谅解 ...
  扩展·盗窃罪:  amount_stolen 盗窃金额 / gang_involvement 团伙 / use_of_weapon 持械
  扩展·故意伤害罪: injury_level 伤害等级[轻微伤/轻伤二级/重伤二级] / premeditation 预谋 ...
  扩展·诈骗罪:  amount_defrauded 诈骗金额 / victim_count 受害人数 / group_crime 团伙

阶段 3 各罪名内聚类（k 由轮廓系数自动选）→ 共 12 个案件原型；全局因子重要性排序：
  1. 罪名  2. 伤害等级=重伤  3. 诈骗金额  4. 盗窃金额  5. 团伙作案  6. 是否预谋 ...
  ▸ 原型#0 [故意伤害罪] 中位 2 月：伤害等级=轻微伤(z=+2.5)
  ▸ 原型#1 [故意伤害罪] 中位 42 月：伤害等级=重伤二级(z=+3.9)、预谋(z=+1.8) —— "持械预谋重伤"型
  ▸ 原型#5 [盗窃罪]     中位 51 月：盗窃金额高、前科/累犯 100% ...

阶段 4 对话：识别到盗窃案缺金额 → 按重要性追问金额/认罪/谅解 → 补全后匹配到 原型#6
         （典型刑期中位 40 月、区间 24~50 月），并引用该原型的关键因子给出建议。
```

---

## 项目结构

```
structured-knowledge-extraction/
├── README.md           # 本文档
├── requirements.txt    # 项目特定依赖
├── config.py           # 项目特定配置（非 LLM）
├── generate_data.py    # 合成数据生成
├── discovery.py        # 阶段 ①：因子发现
├── extractor.py        # 阶段 ②：结构化抽取
├── archetypes.py       # 阶段 ③：聚类分析
├── advisor_agent.py    # 阶段 ④：对话 Agent
├── demo.py            # 全流程演示
├── test_*.py          # 测试文件
├── data/              # 数据目录
│   ├── cases.jsonl    # 案例数据
│   ├── schema.json    # 发现的 schema（缓存）
│   ├── extracted.jsonl # 抽取结果（缓存）
│   └── archetypes.json # 聚类模型（缓存）
├── results/           # 结果输出目录
└── logs/              # 日志目录
```

---

## 数据说明

`data/cases.jsonl` 是**自带的小样本合成数据**（66 条，覆盖 3 类罪名），由 `generate_data.py` 用已知量刑公式加噪声生成。

关键点是**因子在生成时被"写进"案情文本，发现阶段再从文本里把它们"读"回来**——因子发现完全不依赖生成时的字段列表，因此学到的模式来自数据本身。

**真实目标数据集是 CAIL2018**（中文刑事判决，数百万条）。因体量太大不便随仓库分发才用合成小样本；换成真实数据只需把 `generate_data.py` 换成读取 CAIL 的 `data_*.json`（每行含 `fact`、`meta.accusation`、`meta.term_of_imprisonment`），产出同结构的 `cases.jsonl` 即可。

---

## 技术要点

### 四段流水线

**① 自下而上因子发现（`discovery.py`）**
- 不预先定义任何字段
- LLM 自由归纳影响判决的因素
- 归并、去重、规范化成模块化 schema

**② 结构化抽取（`extractor.py`）**
- 用发现的 schema 进行抽取
- LLM 结构化输出（`response_format=json_object`）
- 带磁盘缓存，重跑几乎免费

**③ 聚类成案件原型（`archetypes.py`）**
- 因子翻译成数值向量（one-hot、ln 压缩）
- KMeans 聚类（k 由轮廓系数自动选）
- 计算两级重要性：全局 + 原型内

**④ 对话式建议 Agent（`advisor_agent.py`）**
- 抽取已知因子
- 按全局重要性追问缺失因子
- 匹配最近原型并给出建议

---

## 局限与免责声明

- 本项目**仅用于教学**，演示"从结构化数据中提取隐性知识"这一技术范式。
- 数据为合成、因子集经简化，聚类也无法刻画真实司法量刑的复杂性与非线性。
- **本项目的任何输出都不构成法律意见。** 真实案件量刑受法律条文、司法解释、地域政策与大量具体情节影响，请务必咨询专业律师，切勿据此做任何法律决策。

---

## 迁移说明

本项目已从 `ai-agent-book` 迁移到 `ai-agant`，主要变更：

1. **LLM 配置统一**：使用项目根目录的 `.env` 和 `llm.client` 模块
2. **路径处理**：添加了自动路径处理，确保正确导入模块
3. **配置精简**：`config.py` 仅保留项目特定配置
4. **依赖优化**：核心依赖由根目录统一管理

---

## 参考资料

- [项目规范文档](../../../CONVENTION.md)
- [Chapter 3 目录](../README.md)
- CAIL2018 数据集：中国刑事判决书大数据
