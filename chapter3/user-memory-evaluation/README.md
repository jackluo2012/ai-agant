# 用户记忆评估框架

配套《深入理解 AI Agent》第 3 章 **实验 3-1**：三层记忆评测集，含离线 keyword-recall 对照表。

← [返回第 3 章目录](../README.md)

---

## 概述

用真实业务对话，在三层递进难度上评测 Agent 记忆：能否存储、检索并利用用户交互中的信息。

### 第 1 层：基础回忆与直接检索
单会话、明确事实（账号、确认码、预约等）。

### 第 2 层：上下文推理与消歧
多会话、请求含糊；需取回**全部**相关信息并知道何时澄清。

### 第 3 层：跨会话综合与主动协助
跨会话综合、发现关键关联、主动提示。

## 特性

- **60 个测试用例**（每层 20 个，各 50+ 轮对话）
- **实验 6-3 结构化 LLM 评委**：精确度、召回率、推理、主动性四个维度，外加幻觉一票否决；每个维度包含证据和具体的边界案例决策
- 覆盖银行、保险、医疗、出行、零售等领域
- 支持交互式、批处理、编程接口模式
- 生成详细的评估报告

## 快速开始：记忆系统打分对比（实验 3-1）

完全离线运行（无需 API Key），使用 `keyword-recall` 指标：

```bash
python main.py --mode compare --metric keyword-recall
```

示例输出：

```
             记忆系统对比（关键事实召回，0.000-1.000）
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━┓
┃ 层次                          ┃ full_ctx  ┃ json_card ┃ simple_nt ┃ no_memry ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━┩
│ Layer 1 · 基础回忆            │  1.000    │  1.000    │  0.417    │  0.000   │
│ Layer 2 · 消歧                │  1.000    │  1.000    │  0.333    │  0.000   │
│ Layer 3 · 主动综合            │  1.000    │  1.000    │  0.125    │  0.000   │
│ 总体                          │  1.000    │  1.000    │  0.323    │  0.000   │
└───────────────────────────────┴───────────┴───────────┴───────────┴──────────┘
```

分数从 `fixtures/system_responses.example.json` **计算得出**（非手写）。*Simple Notes* 在第 1 层表现尚可，但在第 2/3 层下降；*Advanced JSON Cards* 在各层次都保持稳定。

- `fixtures/gold_facts.json` — 从 `test_cases/*.yaml` 提取的关键事实
- `fixtures/system_responses.example.json` — 替换为您的 `{系统名: {test_id: 回答}}` 格式数据

## 环境准备

### 1. 激活项目虚拟环境

在项目根目录 `ai-agant/` 中：

```bash
# 激活虚拟环境
source .venv/bin/activate  # macOS/Linux
# 或 .venv\Scripts\Activate.ps1  # Windows PowerShell
```

### 2. 配置 LLM（项目根目录）

确保项目根目录（`ai-agant/`）的 `.env` 文件中已配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3   # 可选
```

**注意：** LLM 配置在项目根目录统一管理，各章节项目不创建独立的 `.env` 文件。

## 使用方法

### 查看帮助

```bash
python main.py --help
```

### 主要命令

```bash
# 离线对比多个记忆系统（无需 API）
python main.py --mode compare --metric keyword-recall

# 对比第 3 层测试用例
python main.py --mode compare --metric keyword-recall --category layer3

# 使用 LLM 评委对比（需要 API）
python main.py --mode compare --metric llm-judge --evaluator kimi

# 交互式菜单
python main.py --mode interactive

# 演示模式
python main.py --mode demo

# 批量评估
python main.py --mode batch --responses agent_responses.json

# 仅列出测试用例（离线）
python main.py --list
```

### 命令行参数

| 参数 | 说明 |
| --- | --- |
| `--mode {interactive,demo,batch,compare}` | 运行模式（默认：interactive） |
| `--metric {llm-judge,keyword-recall}` | 评委（需 API）或离线关键事实召回 |
| `--responses PATH` | 回答 JSON 文件路径 |
| `--gold PATH` | 黄金事实文件（默认：fixtures/gold_facts.json） |
| `--category {layer1,layer2,layer3}` | 仅评测某一层次 |
| `--test-cases-dir PATH` | 备用数据集目录 |
| `--evaluator {kimi,openai}` / `--model` | 评委后端配置 |
| `--output PATH` | 报告输出文件路径 |
| `--list` | 离线列出测试用例后退出 |

### 批量评估 JSON 格式

```json
{
  "layer1_01_bank_account": "您的支票账户号码是 4429853327。",
  "layer1_02_insurance_claim": "您的索赔号是 CLM-2024-894327，理赔员 Patricia Wong 将在 24-48 小时内致电。"
}
```

## 编程接口

```python
from framework import UserMemoryEvaluationFramework

# 初始化框架
framework = UserMemoryEvaluationFramework()

# 列出测试用例
test_cases = framework.list_test_cases(category="layer1")

# 获取对话历史
histories = framework.get_conversation_histories("layer1_01_bank_account")

# 获取用户问题
question = framework.get_user_question("layer1_01_bank_account")

# 提交并评估
result = framework.submit_and_evaluate(
    test_id="layer1_01_bank_account",
    agent_response="您的支票账户号码是 4429853327。",
    extracted_memory=None
)

print(f"奖励：{result.reward:.3f}")
print(f"通过：{result.passed}")
print(f"推理：{result.reasoning}")
```

## 测试用例结构

字段：`test_id`、`category`、`title`、`conversation_histories`、`user_question`、`evaluation_criteria`、`expected_behavior`。

- **第 1 层**：银行账户、保险索赔、医疗预约、航班预订、互联网服务安装
- **第 2 层**：多车辆、多信用卡、多保险单、多订阅服务
- **第 3 层**：护照与出行协调、保险覆盖与医疗程序、跨会话税务/保修综合

## 评估指标

### `keyword-recall`（离线）

`奖励 = (回答中的黄金事实数) / (黄金事实总数)`，使用规范化子字符串匹配。

### `llm-judge`（需要 API）

实验 6-3 评委读取权威对话源并返回四个 1-4 档成绩（`优秀/良好/通过/失败`）：
- 事实精确度
- 事实召回率
- 推理正确性
- 主动性

每个成绩包含引用的证据和应用的边界案例。独立的幻觉判定是无条件的零分否决。任务成功 deliberately 比部分奖励更严格：精确度、召回率和推理必须都至少达到`良好`（3/4），且不能触发幻觉否决。主动性保持诊断性，因为完整的直接答案不一定需要额外建议。

### 结构化评分标准验证

```bash
python validate_rubric.py \
  --test-id layer1_01_bank_account \
  --answer '您的支票账户是 4429853327。直接存款路由号码是 123006800。' \
  --output results/live_6_3_layer1.json
```

## 项目结构

```
user-memory-evaluation/
├── config.py              # 项目配置（不含 LLM 配置）
├── framework.py           # 主框架
├── evaluator.py           # LLM 评估器
├── metrics.py            # 离线指标
├── models.py             # 数据模型
├── comparison.py         # 跨系统对比
├── main.py               # 主入口
├── validate_rubric.py    # 评分标准验证
├── requirements.txt      # 项目特定依赖
├── README.md             # 本文档
├── fixtures/             # 固定数据
│   ├── gold_facts.json
│   └── system_responses.example.json
├── test_cases/           # 测试用例 YAML
│   ├── layer1/           # 第 1 层：基础回忆
│   ├── layer2/           # 第 2 层：消歧
│   └── layer3/           # 第 3 层：主动综合
├── results/              # 评估结果输出
└── logs/                 # 日志文件
```

## 扩展方法

在 `test_cases/layer*/` 下添加 YAML 文件。可继承 `LLMEvaluator` 创建自定义评委。

## 系统要求

- Python 3.12+
- 项目虚拟环境（在项目根目录 `ai-agant/.venv`）
- LLM Judge 模式需要配置 API Key
- 建议 8GB+ 内存

## 许可证

MIT License
