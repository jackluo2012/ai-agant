# 代码辅助数学解题工具

> 实验对比同一模型在 AIME 风格竞赛数学题上的两种解题模式：
> - 纯思维链（CoT）：仅靠自然语言推理
> - 代码辅助：使用 Python 沙箱执行精确计算

---

## 功能概述

本实验旨在验证「代码辅助」模式对数学解题准确率的提升效果。在同一组 AIME 风格竞赛数学题上，使用同一个模型进行对照实验：

- **纯思维链模式**：仅用自然语言逐步推理，不执行代码
- **代码辅助模式**：将问题形式化为 Python 代码，在沙箱中执行，获得精确计算结果

### 工作原理

```
题目 ──► 模型
            │  纯思维链：自然语言推理 ──► 最终答案（易出错）
            │
            └─ 代码辅助：生成 Python 代码
                        │  通过 function calling
                        ▼
                  run_python 工具（子进程沙箱，预装 sympy/numpy/scipy，超时保护）
                        │  标准输出
                        ▼
                  模型基于精确结果继续推理 ──► 最终答案（更准确）
```

### 技术特点

- **工具调用**：通过 OpenAI 兼容的 function calling 暴露 `run_python` 工具
- **沙箱隔离**：在子进程中执行代码，防止崩溃或死循环影响主进程
- **超时保护**：默认 20 秒超时，避免计算量过大导致挂起
- **数学库支持**：沙箱预装 sympy、numpy、scipy
- **离线验证**：支持无需 LLM 的自检模式，验证沙箱和题库

---

## 快速开始

### 1. 环境准备

确保在项目根目录（`ai-agant/`）下操作，且虚拟环境已激活：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r chapter5/code-for-math/requirements.txt
```

依赖说明：
- 核心依赖（openai）由项目根目录提供
- 本实验仅需数学计算库：sympy、numpy、scipy

### 3. 配置 LLM

在**项目根目录**的 `.env` 文件中配置 LLM 服务：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow、doubao、deepseek 等
LLM_MODEL=kimi-k3   # 可选，默认使用供应商推荐模型
```

### 4. 运行实验

#### 离线自检（无需 LLM）

验证沙箱和题库功能：

```bash
cd chapter5/code-for-math
python demo.py --selfcheck
```

输出示例：
```
离线自检：在沙箱中执行题库参考解，并按真值判分（无需配置 LLM）

题号   考点                             真值      沙箱输出
--------------------------------------------------------
1    数论（容斥原理）                    925       925   ✓
2    模运算                              216       216   ✓
...
11   格点计数                           1245      1245   ✓
--------------------------------------------------------
参考解命中真值：11/11

全部通过：沙箱可用，题库真值自洽，可放心用于打分。
```

#### 完整对照实验

对比两种模式的准确率：

```bash
python demo.py                           # 运行完整对照实验
python demo.py --verbose                 # 打印生成的代码和执行结果
python demo.py --limit 3                # 仅前 3 题（节省调试成本）
python demo.py --mode code              # 仅代码辅助模式
python demo.py --mode cot               # 仅纯思维链模式
python demo.py --output result.json     # 将结果写入 JSON
python demo.py --problems mine.json     # 使用自定义题库
```

---

## 使用说明

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--mode {both,code,cot}` | 求解模式；默认 `both`（两种模式都运行并对比） |
| `--selfcheck` | 离线自检模式；仅运行沙箱参考解，无需配置 LLM |
| `--model 名称` | 覆盖模型名（优先级高于 `.env` 配置） |
| `--problems 路径` | 题库 JSON 文件路径；默认 `problems.json` |
| `--limit N` | 仅运行前 N 题（节省调试成本） |
| `--output 路径` | 将逐题结果和汇总写入指定 JSON 文件 |
| `--verbose` | 打印模型生成的代码和沙箱执行结果 |

### 题库格式

`problems.json` 格式示例：

```json
[
  {
    "id": "1",
    "topic": "数论（容斥原理）",
    "question": "在 1 到 2025 中，既不能被 3 整除，也不能被 5 整除，也不能被 7 整除的整数有多少个？",
    "answer": 925,
    "solution": "print(sum(1 for n in range(1,2026) if n%3 and n%5 and n%7))"
  }
]
```

### 输出格式

逐题对照结果：
```
题号   考点                             真值     CoT预测          代码预测
------------------------------------------------------------------------------
1    数论（容斥原理）                   925       925   ✓       925   ✓
2    模运算                             216       215   ✗       216   ✓
...
------------------------------------------------------------------------------
准确率                                    8/11 =  73%       10/11 =  91%
==============================================================================

结论：纯 CoT 准确率 73%，代码辅助准确率 91%，提升 +18%。
```

---

## 项目结构

```
chapter5/code-for-math/
├── README.md              # 本文档
├── demo.py                # 主程序：对照实验逻辑
├── sandbox.py             # Python 沙箱实现
├── problems.json          # AIME 风格数学题库（含参考解）
├── requirements.txt       # 本实验特定依赖
├── test_empty_problems.py # 单元测试
├── results/               # 结果输出目录
└── logs/                  # 日志目录
```

---

## 配置说明

### LLM 配置（项目根目录 .env）

确保项目根目录的 `.env` 文件中已配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow、doubao、deepseek 等
LLM_MODEL=kimi-k3   # 可选
```

支持的提供商：
- `kimi` - Moonshot AI（推荐，性价比高）
- `siliconflow` - SiliconFlow
- `doubao` - 字节跳动豆包
- `deepseek` - DeepSeek
- `openai` - OpenAI
- `anthropic` - Anthropic Claude

### 项目特定配置（可选）

本实验无额外配置项，所有配置通过命令行参数传入。

---

## 故障排除

### 问题：无法导入 llm.client

**原因**：未在项目根目录运行，或虚拟环境未激活

**解决**：
```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
python chapter5/code-for-math/demo.py --selfcheck
```

### 问题：未配置 LLM

**现象**：运行实验时报错"未配置 LLM"

**解决**：在项目根目录 `.env` 文件中配置 LLM 提供商和 API Key

### 问题：沙箱执行超时

**现象**：代码执行报错"执行超时"

**解决**：检查生成的代码是否存在死循环或计算量过大

### 问题：模块导入错误

**现象**：`ModuleNotFoundError: No module named 'sympy'`

**解决**：安装依赖
```bash
pip install -r chapter5/code-for-math/requirements.txt
```

---

## 技术要点

### 1. 统一 LLM 客户端

使用项目统一的 LLM 封装，自动从 `.env` 读取配置：

```python
from llm.client import get_llm_client

client = get_llm_client()
model = client.model_name
```

### 2. 子进程沙箱

通过 `subprocess` 模块实现隔离执行：
- 写入临时文件
- 使用当前解释器执行
- 20 秒超时保护
- 合并 stdout 和 stderr

### 3. Function Calling

通过 OpenAI 兼容的工具调用接口暴露 `run_python` 工具，模型自主决定何时使用。

### 4. 答案抽取

支持多种答案格式：
- `FINAL ANSWER: <整数>`（优先）
- `\boxed{<整数>}`（LaTeX 格式）
- 最后一个整数（退化）

---

## 扩展思路

- 支持更多数学库（如 mpmath、sympy 的扩展模块）
- 添加代码执行结果的缓存机制
- 支持多轮工具调用的结果聚合
- 添加代码安全性检查（限制文件访问、网络请求等）
- 支持更多编程语言（如 JavaScript、Julia）
