# 生产日志的智能诊断系统

基于 LLM 的生产日志智能诊断系统，能够分析 Agent 轨迹、识别问题模式、生成结构化报告，并自动创建回归测试用例。

## 功能概述

- **智能诊断**：分析生产轨迹、系统架构和 PRD，自动识别问题并生成结构化报告
- **回归测试生成**：基于诊断结果，自动生成可执行的回归测试用例
- **重放验证**：通过确定性仿真系统重放测试，验证问题修复效果
- **GitHub 集成**：支持通过 MCP 协议在 GitHub 仓库创建 Issue（mock 或真实）

## 快速开始

### 1. 环境准备

确保已安装 Python 3.8+，并在项目根目录激活虚拟环境：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
```

### 2. 配置 LLM

在**项目根目录**的 `.env` 文件中配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3   # 可选，默认使用提供商默认模型
```

支持的 LLM 提供商：
- Kimi (`kimi`)
- SiliconFlow (`siliconflow`)
- DeepSeek (`deepseek`)
- 阿里云 (`aliyun`)
- 自定义 (`custom`)

### 3. 安装依赖

```bash
pip install -r chapter5/log-diagnosis/requirements.txt
```

**注意**：核心 LLM 依赖（如 `openai`）由项目根目录统一提供，此处仅包含项目特定依赖（如 `mcp`）。

### 4. 运行

```bash
# 完整流程（需要 LLM API）
python chapter5/log-diagnosis/demo.py

# 快速自检（无需 LLM API）
python chapter5/log-diagnosis/demo.py --smoke

# 使用自定义模型
python chapter5/log-diagnosis/demo.py --model your-model-name

# 真实创建 GitHub Issue（需要 GITHUB_TOKEN 和 GITHUB_REPO）
python chapter5/log-diagnosis/demo.py --create-issue
```

## 使用方法

### 基本流程

1. **输入数据准备**：
   - `data/architecture.md` - 系统架构文档
   - `data/PRD.md` - 产品需求文档
   - `data/trajectories.jsonl` - 生产轨迹数据（JSONL 格式）

2. **诊断阶段**：
   - LLM 分析轨迹与架构/PRD 的偏离
   - 输出结构化问题报告（优先级/模块/描述/建议）

3. **测试用例生成**：
   - 基于问题报告自动生成回归测试用例
   - 每个用例包含轨迹引用、交互轮次、断言 DSL

4. **重放验证**：
   - 使用确定性仿真系统重放测试
   - 分别验证"未修复"（预期失败）和"修复后"（预期通过）

### 轨迹数据格式

```json
{
  "trajectory_id": "T-1001",
  "task": "退款处理",
  "task_input": {
    "intent": "refund",
    "order_id": "ORD-001",
    "order_status": "paid",
    "payment_flaky": true
  },
  "final_status": "success",
  "turns": [
    {
      "index": 0,
      "role": "tool",
      "module": "order_service",
      "tool": "query_order",
      "input": {"order_id": "ORD-001"},
      "output": {"status": "paid"},
      "status": "success",
      "latency_ms": 210
    }
  ]
}
```

### 支持的断言类型

| 类型 | 参数 | 说明 |
|------|------|------|
| `step_present` | `tool` | 检查某工具是否在轨迹中出现 |
| `tool_succeeds` | `tool` | 检查某工具最终是否成功 |
| `latency_under` | `tool`, `threshold_ms` | 检查某工具延迟是否低于阈值 |
| `final_status_is` | `value` | 检查任务最终状态 |

## 项目结构

```
chapter5/log-diagnosis/
├── data/                    # 输入数据目录
│   ├── architecture.md      # 系统架构文档
│   ├── PRD.md               # 产品需求文档
│   └── trajectories.jsonl   # 生产轨迹数据
├── diagnoser.py            # 诊断 Agent（LLM 调用）
├── demo.py                 # 主入口文件
├── replay.py               # 回归测试重放框架
├── sut.py                  # 被测系统仿真
├── github_mcp.py           # GitHub Issue 创建（MCP 协议）
├── results/                # 结果输出目录
├── logs/                   # 日志目录
└── README.md               # 本文档
```

## 配置说明

### LLM 配置（项目根目录 .env）

确保项目根目录的 `.env` 文件中已配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3   # 可选
```

### GitHub 配置（可选）

如需真实创建 GitHub Issue，设置以下环境变量：

```bash
export GITHUB_TOKEN=ghp_your_token
export GITHUB_REPO=owner/repo
```

## 命令行参数

```
python demo.py [选项]

选项：
  --smoke              快速自检（无需 LLM API）
  --model MODEL        临时覆盖模型
  --data-dir DIR       自定义输入数据目录
  --output FILE        GitHub Issue 输出路径
  --create-issue       真实创建 GitHub Issue（需 GITHUB_TOKEN 和 GITHUB_REPO）
  --no-github          跳过 GitHub Issue 步骤
  -h, --help           显示帮助信息
```

## 故障排除

### 问题：未配置 LLM API_KEY

**错误信息**：`错误：未配置 LLM API_KEY`

**解决方法**：
1. 在项目根目录创建或编辑 `.env` 文件
2. 添加 `API_KEY=your-api-key` 和 `LLM_PROVIDER=kimi`
3. 重新运行

### 问题：模块导入失败

**错误信息**：`ModuleNotFoundError: No module named 'llm'`

**解决方法**：
1. 确保从项目根目录运行
2. 检查 `llm/client.py` 是否存在
3. 激活虚拟环境：`source .venv/bin/activate`

### 问题：轨迹文件不存在

**错误信息**：`FileNotFoundError: trajectories.jsonl`

**解决方法**：
1. 检查 `data/trajectories.jsonl` 是否存在
2. 使用 `--data-dir` 指定正确的数据目录
3. 使用 `--smoke` 模式进行快速测试

## 技术要点

### 1. 确定性仿真

被测系统（`sut.py`）是确定性仿真器，相同输入始终产生相同输出，确保测试可重复。

### 2. 双模式重放

- **buggy 模式**：复现线上问题，测试应失败
- **fixed 模式**：模拟修复后系统，测试应通过

### 3. 断言 DSL

简洁的断言语言，支持工具调用检查、延迟验证、状态验证等。

### 4. MCP 协议集成

通过标准 MCP 协议连接 GitHub MCP Server，支持真实 Issue 创建。

## 示例输出

```
======================================================================
步骤 1｜Agent 诊断（真实调用 LLM）：定位问题并生成结构化报告
======================================================================

[问题 1] 未进行退款资格校验
  优先级 : P0    模块: order_service    PRD: R1
  轨迹   : ['T-1001', 'T-1002']  关键轮次: [3]
  描述   : 退款前缺失强制的 verify_refund_eligibility 校验。
  建议   : 在 process_refund 前增加 verify_refund_eligibility 调用

======================================================================
步骤 3｜重放框架真正执行测试用例
======================================================================
(A) 对『线上未修复』系统重放 —— 期望复现 bug（FAIL）
    [FAIL] RT-001  (T-1001)  工具 verify_refund_eligibility 缺失
    [FAIL] RT-002  (T-1002)  process_refund 调用 3 次, 失败 3 次, 末次失败

(B) 对『修复后』系统重放 —— 期望修复被验证（PASS）
    [PASS] RT-001  (T-1001)  工具 verify_refund_eligibility 出现
    [PASS] RT-002  (T-1002)  process_refund 调用 2 次, 失败 1 次, 末次成功

  小结：复现 bug 2/2 条；修复后通过 2/2 条。
```

## 扩展与适配

### 使用自定义 LLM 提供商

在项目根目录 `.env` 中设置：

```bash
API_KEY=your-custom-key
LLM_PROVIDER=custom
BASE_URL=https://your-custom-endpoint/v1
LLM_MODEL=your-model-name
```

### 自定义断言类型

在 `replay.py` 的 `_eval_assertion` 函数中添加新的断言类型处理逻辑。

## 相关文档

- [ai-agant 规范](../../.claude/skills/ai-agant-convention/README.md)
- [LLM 配置指南](../../llm/README.md)
