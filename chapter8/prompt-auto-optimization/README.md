# 实验 8-3：基于失败轨迹的系统提示词自动优化

## 项目概述

本项目是《AI Agent 实战：从零构建智能系统》第 8 章的实验 8-3，展示如何从失败的客服轨迹中提取学习信号，自动优化系统提示词。

### 核心功能

- **失败轨迹诊断**：将评估失败的三维分析（规则合规性、任务解决、合规灵活性）转化为结构化的学习信号
- **Coding Agent**：通过精确的搜索/替换编辑（而非整篇重写）来修改提示词，生成可审计的 diff
- **发布门槛**：用保留任务集和边界案例集双重约束，确保优化后的提示词可以灰度发布
- **完整验证**：与人工调优版对照，展示自动优化的有效性

### 实验场景

模拟「云舒航空」客服场景，解决初始提示词的**过度转接**问题：
- 初始问题：遇到政策争议（如不可退票要退款）就转接人工
- 优化目标：收紧转接边界，仅两种情况可转接——乘客明确要求人工、紧急安全情况
- 评估方式：保留任务集（确保不退化）+ 边界案例集（验证过度转接已改善）

---

## 快速开始

### 1. 环境准备

确保已安装 Python 3.10+，并在项目根目录激活虚拟环境：

```bash
cd ai-agant
source .venv/bin/activate
```

### 2. 配置 LLM（项目根目录 .env）

在项目根目录的 `.env` 文件中配置 LLM 提供商：

```bash
# LLM 配置
API_KEY=your-api-key-here
LLM_PROVIDER=kimi          # 或 openai, deepseek, doubao 等
LLM_MODEL=kimi-k3          # 可选，使用提供商默认模型
```

支持的提供商：
- **Kimi（月之暗面）**：`kimi`，默认模型 `kimi-k3`
- **OpenAI**：`openai`，默认模型 `gpt-4o`
- **DeepSeek**：`deepseek`，默认模型 `deepseek-chat`
- **豆包（字节跳动）**：`doubao`，需配置 BASE_URL
- **自定义端点**：`custom`，需配置 BASE_URL

### 3. 运行实验

```bash
# 完整运行：10 个用例 × 3 份 prompt（初始、自动优化、人工对照）
python3 chapter8/prompt-auto-optimization/demo.py

# 快速演示：每组只取 2 个用例，省时省钱
python3 chapter8/prompt-auto-optimization/demo.py --quick

# 指定模型和提供商（覆盖 .env 配置）
python3 chapter8/prompt-auto-optimization/demo.py --provider kimi --model kimi-k3

# 输出 JSON 格式证据
python3 chapter8/prompt-auto-optimization/demo.py --output results/run.json
```

---

## 使用方法

### 命令行参数

```
--quick              快速演示模式：每组只取 2 个用例
--limit N            每组最多评测 N 个用例（覆盖 --quick）
--group {holdout|boundary|both}
                     选择评测的任务集（默认 both）
--rounds N           Coding Agent 最大重试轮数（默认 3）
--provider NAME      覆盖 LLM 提供商
--model NAME         覆盖 LLM 模型名
--output PATH        将结果写入 JSON 文件
--dry-run            离线自检：仅打印配置，不调用 API
```

### 示例

```bash
# 只评测边界案例集（关注过度转接问题）
python3 chapter8/prompt-auto-optimization/demo.py --group boundary

# 使用推理模型，允许更多优化轮数
python3 chapter8/prompt-auto-optimization/demo.py --model kimi-k3 --rounds 5

# 离线验证配置（不消耗 API 配额）
python3 chapter8/prompt-auto-optimization/demo.py --dry-run
```

---

## 项目结构

```
chapter8/prompt-auto-optimization/
├── prompts/                 # 系统提示词文件
│   ├── system_prompt.txt              # 初始版本（有过度转接问题）
│   └── system_prompt_manual.txt       # 人工调优版本（对照）
├── results/                 # 实验结果输出目录
├── logs/                    # 日志目录
├── local_config.py          # 本地配置（API 调用跟踪）
├── airline_env.py           # 航空客服模拟环境 + 评测用例
├── evaluate.py              # 评测器（运行 Agent + LLM 裁判）
├── learning_signal.py       # 失败轨迹 → 三维诊断
├── coding_agent.py          # Coding Agent（精确编辑提示词）
├── release_gate.py          # 发布门槛检查
├── demo.py                  # 主入口：完整实验流程
└── run_experiment_8_3.py    # 实验脚本（保存证据）
```

---

## 核心模块说明

### 1. 航空客服模拟环境 (airline_env.py)

提供精简的航空客服场景：
- **工具定义**：查询订单、改签、退票政策、行李政策、选座、转接人工
- **Agent 循环**：带工具调用的最小 Agent 实现
- **评测用例**：
  - 保留任务集（holdout）：正常请求，既不能该转不转、也不能不该转乱转
  - 边界案例集（boundary）：政策争议，应解释政策而非一转了之

### 2. 评测器 (evaluate.py)

对给定提示词在用例集上评估：
- 运行 Agent 获取行为（是否转接、最终回复）
- LLM-as-judge 判断非转接用例是否妥善处理
- 返回分组正确率和明细

### 3. 学习信号提取 (learning_signal.py)

将失败轨迹转化为结构化的改进请求：
- **三维诊断**：规则合规性、任务解决、合规灵活性
- **来源用例**：记录所有失败用例 ID
- **诊断结论**：生成对问题的描述

### 4. Coding Agent (coding_agent.py)

读取诊断并生成精确的提示词编辑：
- 使用 `apply_edits` 工具提交 (old_str → new_str) 编辑
- 原子性：任一编辑失败则全部回滚，反馈给模型重试
- 可审计：生成统一 diff 和编辑清单

### 5. 发布门槛 (release_gate.py)

检查候选版本是否满足发布条件：
- 补丁非空
- 补丁可审计（包含精确的 old→new 编辑）
- 来源用例已记录
- 保留任务集未退化
- 边界案例集有改善

---

## 配置说明

### LLM 配置（项目根目录 .env）

所有 LLM 配置在项目根目录的 `.env` 文件中统一管理：

```bash
# 必填：API 密钥
API_KEY=sk-xxx

# 可选：提供商（默认 openai）
LLM_PROVIDER=kimi

# 可选：模型名（使用提供商默认模型）
LLM_MODEL=kimi-k3

# 可选：自定义端点（某些提供商需要）
BASE_URL=https://api.example.com/v1
```

### 项目特定配置

本项目无额外配置文件，所有参数通过命令行传入。

---

## 输出说明

### 控制台输出

```
======================================================================
# 实验 8-3：基于失败轨迹的系统提示词自动优化（航空客服场景）
# LLM 提供商: kimi   模型: kimi-k3
# 用例数: 10（保留集 + 边界集）   Coding Agent 优化轮数上限: 3
======================================================================

【步骤 1】用初始系统提示词评测（观察是否过度转接）
  初始结果：保留集 5/5 (100%)，边界集 1/5 (20%)
  边界案例中出现【过度转接】的用例数：4 / 5
    ...

【步骤 2】将失败轨迹整理为三维诊断
...
【步骤 3】Coding Agent 读取诊断并生成候选系统提示词……
【步骤 4】评测候选系统提示词并运行发布门槛
【步骤 5】对照组：人工调优版系统提示词
```

### JSON 输出（--output）

```json
{
  "schema_version": 2,
  "experiment_id": "8-3",
  "provider": "kimi",
  "model": "kimi-k3",
  "evaluations": {
    "initial": {...},
    "automatic_candidate": {...},
    "manual": {...}
  },
  "release_gate": {
    "decision": "release_to_canary",
    "checks": {...}
  },
  "usage": {
    "prompt_tokens": 12345,
    "completion_tokens": 6789,
    "total_tokens": 19134
  }
}
```

---

## 技术要点

### 1. 精确编辑 vs 整篇重写

本项目采用精确编辑方式：
- 模型输出 `(old_str, new_str)` 编辑对
- 代码执行字符串替换并写入文件
- 好处：可审计、可回滚、安全

### 2. 三维评估框架

- **规则合规性**：是否遵守强制规则（如必须转接时是否转接）
- **任务解决**：是否正确处理请求
- **合规灵活性**：政策争议时是否提供替代方案而非一转了之

### 3. 双重约束发布门槛

- **保留任务集**：确保既有正确行为不退化
- **边界案例集**：验证目标问题（过度转接）已改善

### 4. 原子性编辑

- 任一编辑失败则全部回滚
- 把错误反馈给模型重试
- 确保文件始终处于一致状态

---

## 故障排除

### Q: 提示 "环境变量 XXX_API_KEY 未设置"

A: 确保在项目根目录的 `.env` 文件中配置了 API_KEY，格式如下：

```bash
API_KEY=your-actual-api-key
LLM_PROVIDER=kimi
```

### Q: 提示 "ModuleNotFoundError: No module named 'llm'"

A: 请确保：
1. 在项目根目录运行
2. 虚拟环境已激活
3. 使用 `python3 chapter8/prompt-auto-optimization/demo.py` 而非 `cd` 后直接运行

### Q: LLM 调用失败

A: 检查：
1. API_KEY 是否正确
2. LLM_PROVIDER 是否支持
3. 网络连接是否正常
4. 使用 `--dry-run` 验证配置

---

## 依赖说明

核心 LLM 依赖由项目根目录提供，本项目仅使用 Python 标准库：
- `json`：处理配置和输出
- `argparse`：命令行参数解析
- `pathlib`：文件路径处理
- `unittest.mock`：测试模拟

---

## 相关章节

- 《AI Agent 实战：从零构建智能系统》第 8 章：Agent 评测与优化
- 实验 8-1：客服 Agent 的三层轨迹验证器
- 实验 8-2：Codex 作为人工基准测试操作员
