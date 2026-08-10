# 代码辅助逻辑推理工具

> 实验 5-2：用代码生成工具提升逻辑思考能力
>
> 对比在三种模式下求解「骑士与无赖」(Knights & Knaves) 谜题的准确率：
> - 纯思考(pure)：LLM 仅靠自然语言链式推理直接给出答案
> - 代码辅助(code)：LLM 配备 Code Interpreter，把谜题形式化为约束满足问题(CSP)，调用求解器搜索答案
> - 约束求解(solver)：离线基线，直接用 python-constraint 求解结构化陈述

## 功能概述

本项目评估 AI Agent 通过**约束求解**代码来辅助逻辑思考的能力。为 LLM 配备一个预装 `python-constraint` 的代码解释器，让它把「骑士与无赖」逻辑谜题转化为形式化的**约束满足问题(CSP)**——识别变量、定义约束，再调用求解器搜索满足所有约束的解。

### 核心思想：为什么代码辅助更强

「骑士与无赖」谜题的关键建模规则只有一条——对每位居民 X 加一条**双条件(等价)约束**：

```
X 是骑士(True)  <=>  X 说的那句话为真
```

即 `X == (该陈述的语义真值)`。把它交给确定性求解器**穷举**所有布尔组合，逻辑上不会出错；而纯思考在多人、含计数("恰好两个骑士")或自指("我和 B 同类")的谜题上，很容易在心算真值传播时出错。

## 快速开始

### 1. 环境准备

确保已安装项目虚拟环境：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r chapter5/code-for-logic/requirements.txt
```

### 3. 配置 LLM

在项目根目录 `.env` 文件中配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3   # 可选
```

### 4. 运行

#### 离线约束求解基线（不花钱、不联网，推荐先跑）

```bash
python chapter5/code-for-logic/demo.py --mode solver
```

#### LLM 对照实验

```bash
# 默认 both：跑 纯思考 vs 代码辅助 全部题目
python chapter5/code-for-logic/demo.py

# 只跑纯思考
python chapter5/code-for-logic/demo.py --mode pure

# 只跑前 4 题(省钱冒烟测试)
python chapter5/code-for-logic/demo.py --limit 4

# 只跑不超过 3 人的谜题(按难度筛选)
python chapter5/code-for-logic/demo.py --max-people 3
```

## 使用方法

### 运行模式

| 模式 | 说明 | 是否需要 LLM |
|------|------|--------------|
| `both` | 纯思考 + 代码辅助（默认） | 是 |
| `pure` | 仅纯思考 | 是 |
| `code` | 仅代码辅助 | 是 |
| `solver` | 离线约束求解基线 | 否 |

### 命令行参数

```
--mode {both,pure,code,solver}  运行模式（默认 both）
--model MODEL                   LLM 模型名（solver 模式忽略）
--limit N                       只跑前 N 题（0=全部）
--min-people N                  只跑居民数 >= N 的谜题（0=不限）
--max-people N                  只跑居民数 <= N 的谜题（0=不限）
--puzzles PATH                  谜题数据集路径（默认 puzzles.json）
--output PATH                   逐题记录输出路径（默认 last_run.json）
```

### 生成/扩充谜题数据集

```bash
# 导出内置 12 道精选题（默认）
python chapter5/code-for-logic/build_puzzles.py

# 随机生成 20 道解唯一的谜题
python chapter5/code-for-logic/build_puzzles.py --generate 20 --min-people 3 --max-people 5 --seed 7
```

## 项目结构

```
chapter5/code-for-logic/
├── demo.py              # 主程序：纯思考/代码辅助/约束求解对照实验
├── csp_solver.py        # 离线约束求解器：结构化陈述 DSL + python-constraint
├── sandbox.py           # 极简 Code Interpreter：子进程沙箱执行 Python 代码
├── build_puzzles.py     # 生成/校验谜题：用 python-constraint 求解并断言解唯一
├── puzzles.json         # 12 道谜题数据
├── requirements.txt     # 项目特定依赖
├── env.example          # 配置示例
├── results/             # 结果输出目录
└── logs/                # 日志目录
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

### 项目特定配置（可选）

项目没有额外的必需配置。如需自定义，可参考 `env.example`。

## 真实运行结果

### 离线约束求解基线（--mode solver，无需 API）

```
== 约束求解(solver，离线) ==
  [solver] kk01 (2人) ✓  解数=1  预测={'A': 'knight', 'B': 'knave'}
  [solver] kk05 (3人) ✓  解数=1  预测={'A': 'knave', 'B': 'knave', 'C': 'knight'}
  [solver] kk11 (5人) ✓  解数=1  预测={'A': 'knight', 'B': 'knight', 'C': 'knave', 'D': 'knave', 'E': 'knight'}
  ...
------------------------------------------------------------
准确率            100.0%
============================================================
约束求解   准确率: 100.0%  (12/12)
```

### LLM 对照实验（12 题）

```
准确率对比表
============================================================
题号      人数    纯思考       代码辅助
------------------------------------------------------------
kk01    2     ✓         ✓
kk02    2     ✓         ✓
kk03    2     ✓         ✓
kk04    3     ✓         ✓
kk05    3     ✗         ✓
kk06    3     ✗         ✓
kk07    3     ✗         ✓
kk08    4     ✗         ✓
kk09    4     ✗         ✓
kk10    4     ✓         ✓
kk11    5     ✗         ✓
kk12    5     ✓         ✓
------------------------------------------------------------
准确率             50.0%    100.0%
============================================================
纯思考    准确率:  50.0%  (6/12)
代码辅助   准确率: 100.0%  (12/12)
提升(代码辅助 - 纯思考): +50.0 个百分点
```

## 技术要点

### 约束建模代码示例

题面：A 说"B 是骑士"；B 说"C 是无赖"；C 说"D 是骑士"；D 说"E 是无赖"；E 说"我们五人当中至少有两个骑士"。

```python
from constraint import Problem

p = Problem()
for name in ['A', 'B', 'C', 'D', 'E']:
    p.addVariable(name, [True, False])   # True=骑士(说真话), False=无赖(说假话)

# 每句话都写成「X == (那句话的真值)」的双条件约束
p.addConstraint(lambda a, b: a == (b == True), ['A', 'B'])          # A:"B 是骑士"
p.addConstraint(lambda b, c: b == (c == False), ['B', 'C'])        # B:"C 是无赖"
p.addConstraint(lambda c, d: c == (d == True), ['C', 'D'])         # C:"D 是骑士"
p.addConstraint(lambda d, e: d == (e == False), ['D', 'E'])        # D:"E 是无赖"
p.addConstraint(lambda a, b, c, d, e: e == ((a + b + c + d + e) >= 2),
                ['A', 'B', 'C', 'D', 'E'])                          # E:"至少两个骑士"

for s in p.getSolutions():
    print({k: ('knight' if v else 'knave') for k, v in s.items()})
# 输出: {'A': 'knight', 'B': 'knight', 'C': 'knave', 'D': 'knave', 'E': 'knight'}
```

## 故障排除

### 错误：无法获取 LLM 客户端

**原因**：项目根目录 `.env` 文件未配置或配置错误。

**解决**：检查项目根目录 `.env` 文件中的 LLM 配置。

### 错误：筛选后没有任何谜题

**原因**：`--min-people`、`--max-people` 或 `--limit` 参数设置过于严格。

**解决**：放宽筛选条件或使用默认值（全部谜题）。

## 注意事项

- **成本**：默认使用配置的模型，12 谜题两种模式开销较小
- **沙箱**：`sandbox.py` 用子进程 + 超时执行代码，属教学用极简沙箱；生产环境应使用容器/gVisor 等更强隔离
- **谜题可靠性**：`build_puzzles.py` 用 `python-constraint` 求解每题并断言"解唯一"，确保真值解无歧义
