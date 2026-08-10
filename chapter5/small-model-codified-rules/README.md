# 实验 5-3：小模型通过代码化规则追平大模型

## 一句话结论

同一个小模型、同一批任务，仅仅把"业务规则从提示词搬进代码/工具"，就把**任务成功率从 88% 提升到 100%，政策违规从 1 次降到 0 次**——并能观察到工具内代码校验实时拦截了模型的错误认知。

**核心主张：** 把业务规则代码化为守卫，能让一个小模型在复杂政策执行上追平大模型裸跑。

## 功能概述

本实验模拟航空客服场景，通过代码化退款政策对比两种模式：

| 模式 | 说明 |
|------|------|
| `control`（控制组） | 纯自然语言政策，工具无条件执行 |
| `codified`（实验组） | 三重保障：系统提示 + 工具描述 checklist + 工具内代码化校验 |

### 三层守卫对照

| 层级 | 控制组 | 实验组 |
|------|--------|--------|
| ① 系统提示 | 自然语言政策 | 自然语言政策（相同） |
| ② 工具描述 | 极简、无 checklist | 列出完整政策 + 引导参数 |
| ③ 工具内部 | 天真执行：无条件退款 | 基于数据库真值代码化校验 |

### 退款政策

- 经济舱基础票（`basic_economy`）默认**不可退款**
- 例外 1：下单 **24 小时内**可全额退款
- 例外 2：航班被**航司取消**或**延误 ≥ 3 小时**可全额退款
- 灵活票 / 商务舱可全额退款
- 不可退款时应解释政策并**主动提议替代方案**

## 快速开始

### 1. 环境准备

确保项目根目录存在虚拟环境（`.venv`）并已激活：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
```

### 2. 配置 LLM

在项目根目录 `.env` 文件中配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3
```

### 3. 运行实验

```bash
# 离线自检（无需 API Key）：直接看代码化守卫的校验逻辑
python3 chapter5/small-model-codified-rules/demo.py --selftest

# 默认：跑全部 8 个 case，控制组 vs 实验组
python3 chapter5/small-model-codified-rules/demo.py

# 只跑前 4 个 case（省钱快看）
python3 chapter5/small-model-codified-rules/demo.py --quick -v

# 只运行特定 case
python3 chapter5/small-model-codified-rules/demo.py --task R009
```

## 使用方法

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--mode {control,codified,both}` | 运行模式（默认 `both`） |
| `--task ID [ID ...]` | 只运行匹配的 case |
| `--small-model NAME` | 指定小模型名称 |
| `--big-model NAME` | 指定大模型基线名称 |
| `--quick` | 只运行前 4 个 case |
| `-v, --verbose` | 打印每步工具调用 |
| `--output PATH` | 输出结果到 JSON 文件 |
| `--selftest` | 离线演示代码化校验逻辑 |

### 三方对照实验

验证"小模型+规则 ≈ 大模型裸跑"：

```bash
python3 chapter5/small-model-codified-rules/demo.py --big-model gpt-4o
```

## 运行结果示例

```
指标                  控制组                     实验组
--------------------------------------------------------------------
任务成功率               7/8 = 88%               8/8 = 100%
政策违规次数              1                       0
无效工具调用次数            0                       1
```

**关键观察：**
- 实验组成功率 100%，零违规
- 控制组违规 case R009：航司改签时刻被误判为可退
- 工具内代码化校验稳定拦截模型的错误认知

## 项目结构

```
chapter5/small-model-codified-rules/
├── agent.py          # Agent 实现，包含系统提示和工具 schema
├── airline_env.py    # 航空环境模拟，包含代码化退款政策
├── tasks.py          # 8 个评测任务
├── demo.py           # 主程序，对照实验和评分
├── requirements.txt  # 依赖（核心依赖由根目录提供）
├── results/          # 结果输出目录
└── logs/             # 日志目录
```

## 技术要点

### 代码化政策示例

```python
def is_refundable(res: Reservation, now: datetime) -> tuple[bool, str]:
    """基于数据库真值 + 服务端时钟判断某预订是否可全额退款。"""
    if res.cabin != "basic_economy":
        return True, "flexible_fare"
    if now - res.booked_at <= timedelta(hours=24):
        return True, "within_24h"
    if res.flight_status in ("cancelled_by_airline", "delayed_major"):
        return True, "airline_caused"
    return False, "non_refundable_basic_economy"
```

### 拦截示例

```
模型 checklist 自报：expected_refundable=True（认为可退）
数据库真值        ：refundable=False
工具代码化校验返回：status=rejected
  → 系统已拦截退款操作，模型转为解释政策并提议替代方案
```

## 故障排除

### ImportError: No module named 'llm.client'

确保从项目根目录运行，或设置 PYTHONPATH：

```bash
export PYTHONPATH=/home/jackluo/my/ai-agent/ai-agant:$PYTHONPATH
```

### LLM 配置错误

检查项目根目录 `.env` 文件中的 LLM 配置是否正确。

### 虚拟环境问题

确保虚拟环境已激活并安装了必要的依赖：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
```

## 注意事项

- 推理模型（gpt-5/o 系列）不接受 `temperature=0`，代码会自动改用 `temperature=1`
- 服务端时钟固定为 `2026-07-17 12:00`，所有时间判断以它为准
- 次级指标（无效工具调用数、expected_* 不一致比例）会小幅波动，但核心结论稳定成立
