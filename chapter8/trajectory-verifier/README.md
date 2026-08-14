# 实验 8-1：客服 Agent 的三层轨迹验证器

本实验实现了一个用于评估客服 Agent 行为质量的三层轨迹验证系统。该系统不只使用用户满意度或单一总分作为学习信号，而是依次核对环境结果、执行过程与语言质量，并在每个失败维度中保留证据轮次。

## 功能概述

### 三层验证架构

1. **结果层（Environment Result）**：读取最终订单状态，验证任务是否完成
2. **过程层（Process Rules）**：检查业务规则、隐私保护、事实依据和承诺—行动一致性
3. **质量层（LLM Rubric）**：评估表达质量和合规灵活性

### 七个评估维度

| 维度 | 层级 | 说明 |
|------|------|------|
| task_resolution | 结果层 | 任务是否成功完成 |
| rule_compliance | 过程层 | 是否遵守业务规则 |
| privacy_boundary | 过程层 | 是否泄露敏感信息 |
| factual_reliability | 过程层 | 声明是否有事实依据 |
| promise_action_consistency | 过程层 | 承诺是否与行动一致 |
| expression_quality | 质量层 | 措辞是否自然简洁 |
| compliant_flexibility | 质量层 | 遇阻时是否提供合规替代方案 |

## 快速开始

### 1. 环境准备

确保在项目根目录（`ai-agant/`）下工作，虚拟环境已激活：

```bash
cd ai-agant
source .venv/bin/activate
```

### 2. 配置 LLM

在项目根目录的 `.env` 文件中配置 LLM 服务：

```bash
# LLM 配置
API_KEY=your_api_key_here
LLM_PROVIDER=kimi  # 或 openai, deepseek, aliyun 等
LLM_MODEL=kimi-k3  # 可选
BASE_URL=https://api.moonshot.cn/v1  # 某些提供商需要
```

### 3. 运行演示

**确定性模式（无需 API 调用）：**

```bash
python3 chapter8/trajectory-verifier/demo.py
```

**真实 LLM 评估模式：**

```bash
python3 chapter8/trajectory-verifier/demo.py --judge llm
```

### 4. 运行完整实验

```bash
python3 chapter8/trajectory-verifier/run_experiment_8_1.py
```

## 使用方法

### 作为模块使用

```python
from verifier import TrajectoryVerifier
from llm_judge import OpenAIQualityJudge

# 创建验证器
judge = OpenAIQualityJudge()
verifier = TrajectoryVerifier(quality_judge=judge)

# 评估轨迹
report = verifier.evaluate(trajectory_data)
print(f"总分: {report['overall_score']}")
print(f"建议: {report['release_recommendation']}")
```

### 运行单元测试

```bash
# 运行所有测试
python3 -m unittest discover chapter8/trajectory-verifier

# 运行特定测试
python3 -m unittest chapter8.trajectory-verifier.test_verifier
```

## 项目结构

```
chapter8/trajectory-verifier/
├── verifier.py              # 主验证器，组合三层评估
├── evidence_client.py       # LLM 客户端封装（使用项目统一配置）
├── llm_judge.py            # LLM 质量评估器
├── customer_service_env.py # 客服环境模拟
├── calibration.py          # 校准辅助工具
├── demo.py                 # 演示脚本
├── run_experiment_8_1.py   # 完整实验运行
├── sample_trajectories.json # 示例轨迹（含专家标签）
├── real_cases.json         # 真实测试用例
├── results/                # 输出目录
├── logs/                   # 日志目录
└── validation/             # 验证结果目录
```

## 配置说明

### LLM 配置（项目根目录 .env）

所有 LLM 相关配置在项目根目录的 `.env` 文件中统一管理：

```bash
# 必需配置
API_KEY=your_api_key_here
LLM_PROVIDER=kimi  # 支持的提供商：kimi, openai, deepseek, aliyun, siliconflow 等

# 可选配置
LLM_MODEL=kimi-k3   # 模型名称（默认由提供商决定）
BASE_URL=https://...  # 某些提供商需要自定义端点
```

### 支持的 LLM 提供商

| 提供商 | LLM_PROVIDER | 是否需要 BASE_URL |
|--------|---------------|-------------------|
| Kimi | `kimi` | 否 |
| OpenAI | `openai` | 否 |
| DeepSeek | `deepseek` | 否 |
| 阿里云 | `aliyun` | 是 |
| SiliconFlow | `siliconflow` | 否 |

## 输出说明

### 验证器报告结构

```json
{
  "trajectory_id": "案例 ID",
  "overall_score": 0.857,
  "release_recommendation": "review_or_accept",
  "critical_failures": ["维度名称"],
  "review": {
    "required": true,
    "destination": "human_review",
    "status": "pending",
    "reasons": {
      "high_risk_failures": [],
      "low_confidence_or_uncertain": []
    }
  },
  "eligible_as_automatic_learning_signal": false,
  "dimensions": [
    {
      "dimension": "维度名称",
      "layer": "层级名称",
      "verdict": "pass",
      "score": 1.0,
      "evidence": ["证据描述"],
      "confidence": 0.95
    }
  ]
}
```

### 决策建议

- **reject**：存在关键失败（任务失败、严重违规等）
- **review_or_accept**：无关键失败，可能需要人工复核
- **自动学习信号**：`eligible_as_automatic_learning_signal` 为 `true` 时可直接用作训练数据

## 技术要点

### 确定性 vs LLM 评估

- 默认使用 `HeuristicQualityJudge` 进行确定性评估，无需 API 调用
- 使用 `OpenAIQualityJudge` 可获得更精细的语言质量评估
- 结果层和过程层始终保持确定性，只有质量层使用 LLM

### 校准与专家标签

- `sample_trajectories.json` 包含四种场景的带标签轨迹
- `calibration.py` 提供精确率、召回率和标签一致率统计
- 专家标签用于验证评估器的准确性

### 多维诊断 vs 标量基线

- 多维报告为每个失败维度提供具体证据
- 标量基线（`scalar_baseline()`）模拟单一总分的信息损失
- `diagnostic_utility()` 衡量失败维度的证据完整性

## 故障排除

### 问题：无法导入 llm 模块

**解决方法**：确保在项目根目录运行，或设置正确的 PYTHONPATH：

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
```

### 问题：API 调用失败

**解决方法**：检查 `.env` 文件中的配置：

```bash
# 验证配置
cat .env | grep -E "API_KEY|LLM_PROVIDER|BASE_URL"
```

### 问题：中文输出乱码

**解决方法**：确保终端使用 UTF-8 编码：

```bash
export LANG=zh_CN.UTF-8
export LC_ALL=zh_CN.UTF-8
```

## 扩展阅读

本实验对应论文正文"从运行轨迹中获得学习信号"章节。验证器设计强调：

1. **可解释性**：每个维度都有明确的证据来源
2. **可操作性**：失败包含具体轮次，便于定位问题
3. **安全优先**：高风险失败触发人工复核
4. **学习信号**：合格的轨迹可直接用作训练数据
