# 实验 8-5：从浏览器轨迹生成可验证工作流

本项目展示"把经验写成程序"的第一种形式：Agent 首次探索网页任务后，把动作轨迹参数化为工作流；但首次成功只产生 `candidate`（待验证工作流），不能直接进入能力库。待验证工作流必须在重置后的环境中完整重放，并通过每一步的状态谓词与最终状态谓词，才会成为 `validated`。页面变化导致谓词失败时，旧版本转为 `invalid`，系统退回完整 Agent 重新探索。

## 功能概述

- **学习模式**：Agent 通过 browser-use 首次探索任务，捕获动作轨迹
- **验证机制**：待验证工作流必须在重置环境中完整回放通过状态验证
- **参数化回放**：通过不同参数高速回放学习的工作流，无需 LLM 调用
- **失效检测**：页面变化导致谓词失败时自动标记工作流为失效
- **状态验证**：基于真实 Playwright 页面的前置/后置/最终状态验证

## 快速开始

### 1. 环境准备

确保项目根目录的 `.env` 文件中已配置 LLM：

```bash
# 在项目根目录 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 openai, deepseek, anthropic 等
LLM_MODEL=kimi-k3   # 可选
```

### 2. 安装依赖

```bash
# 安装 Chromium
playwright install chromium

# 安装项目依赖
pip install -r requirements.txt
```

### 3. 运行演示

```bash
# 快速测试（单个任务）
python demo_email.py --quick --headless

# 完整演示（学习+回放对比）
python demo_email.py

# 自定义任务
python demo_email.py --task "给 user@example.com 发送邮件" \
                     --replay-task "给 admin@test.com 发送周报"
```

## 使用方法

### 离线机制预检

```bash
# 运行生命周期演示（无需真实浏览器）
python workflow_validation_demo.py

# 运行状态谓词测试
python -m unittest -v test_state_predicates.py
```

### 真实浏览器验收

```bash
# 运行真实实验
python run_experiment_8_4.py --provider ark --model doubao-seed-1-6-flash-250615 --seed 8401
```

### 快速启动脚本

```bash
# 交互式菜单
python quickstart.py
```

## 项目结构

```
browser-use-rpa/
├── learning_agent/           # 学习代理核心模块
│   ├── __init__.py          # 模块导出
│   ├── agent.py             # 学习代理主类
│   ├── workflow.py          # 工作流数据结构
│   ├── knowledge_base.py    # 知识库管理
│   └── replay.py            # 工作流回放器
├── browser-use/              # browser-use 库副本
├── demo_email.py             # 邮件发送演示
├── demo_weather.py           # 天气检查演示
├── quickstart.py             # 快速启动脚本
├── run_experiment_8_4.py     # 真实实验脚本
├── llm_factory.py            # LLM 工厂（使用统一配置）
├── local_mail_sandbox.py    # 可重置邮件沙盒
├── requirements.txt          # 项目依赖
├── env.example              # 配置示例
├── results/                  # 结果输出目录
└── logs/                     # 日志目录
```

## 配置说明

### LLM 配置（项目根目录 .env）

确保项目根目录的 `.env` 文件中已配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 openai, deepseek, anthropic 等
LLM_MODEL=kimi-k3   # 可选
```

### 项目特定配置（可选）

```bash
# Browser-use 日志配置
BROWSER_USE_DEBUG_LOG_FILE=./logs/debug.log
BROWSER_USE_INFO_LOG_FILE=./logs/info.log

# Headless 模式
HEADLESS_MODE=false
```

## 工作流生命周期

```
首次轨迹 → candidate → 重置环境 → 完整回放通过 → validated → 能力库
                                                        │
                                               页面或接口发生变化
                                                        ↓
                                      谓词失败 → invalid → 完整 Agent 重学
```

### 状态说明

- **candidate**（候选）：首次探索后创建，需要验证
- **validated**（已验证）：通过完整回放验证，可复用
- **invalid**（失效）：页面变化导致谓词失败，需要重新学习

## API 使用示例

### 基本使用

```python
from learning_agent import LearningAgent
from llm_factory import make_llm

# 创建代理
agent = LearningAgent(
    task="前往 ethereal.email 并发送测试邮件",
    llm=make_llm(),
    knowledge_base_path="./my_knowledge",
    headless=False
)

# 运行任务
result = await agent.run(max_steps=20)

print(f"成功：{result['success']}")
print(f"耗时：{result['execution_time']:.2f}秒")
print(f"LLM 调用：{result['llm_calls']}")
print(f"工作流复用：{result.get('replay_used', False)}")
```

### 带验证回调

```python
import os

async def reset_sandbox():
    """重置测试环境"""
    # 清空本地邮件沙盒状态
    os.system("curl -X POST http://localhost:8000/api/reset")

agent = LearningAgent(
    task="发送邮件",
    llm=make_llm(),
    knowledge_base_path="./knowledge",
    validation_reset=reset_sandbox  # 提供重置回调
)
```

## 技术要点

### 状态谓词类型

- `URL_CONTAINS`：URL 包含指定字符串
- `ELEMENT_VISIBLE`：元素可见
- `ELEMENT_TEXT_CONTAINS`：元素文本包含
- `ELEMENT_VALUE_EQUALS`：元素值相等
- `PAGE_STATE_EQUALS`：页面状态值相等

### 工作流参数化

工作流支持参数化回放，使用 `{placeholder}` 占位符：

```python
# 学习时捕获
task = "向 test@example.com 发送主题为'报告'的邮件"
# 参数：{recipient: "test@example.com", subject: "报告"}

# 回放时替换
task = "向 admin@test.com 发送主题为'周报'的邮件"
# 自动提取新参数并回放
```

### 性能指标

首次探索需要多次 LLM 调用，参数化回放无需 LLM：

- 探索阶段：~5 秒，4 次 LLM 调用
- 回放阶段：~4 秒，0 次 LLM 调用
- 加速比：1.2x+

## 故障排除

### 问题：无法找到 browser-use 模块

```bash
# 确保在项目虚拟环境中运行
cd ai-agant
source .venv/bin/activate
cd chapter8/browser-use-rpa
```

### 问题：Chromium 未安装

```bash
playwright install chromium
```

### 问题：工作流验证失败

检查以下内容：
1. 是否提供了 `validation_reset` 回调
2. 页面是否发生变化（元素 ID、CSS 选择器等）
3. 网络是否正常

### 问题：LLM 调用失败

检查项目根目录 `.env` 配置：
- `API_KEY` 是否正确
- `LLM_PROVIDER` 是否支持
- `LLM_MODEL` 是否可用

## 实验结果

2026-07-30 的证据为 `validation/real_20260729T171233Z/evidence.json`，SHA-256 为
`a673c657c670482c7d4bedc0dd340ee51586f3e8d6feb440bb7cc216edca426c`。

本次结果：
- 探索：5.313 秒、4 次 LLM 调用
- 回放：4.447 秒、0 次 LLM 调用
- 加速：1.195 倍
- 匹配率、回放成功率、页面变化检出率：100%
- 回退重学计数：1

## 安全说明

真实系统应考虑：
- 高风险动作的权限检查
- 幂等键机制
- 沙盒账号隔离
- 人工批准流程

本项目使用虚构数据和本地沙盒，运行不会产生站外副作用。
