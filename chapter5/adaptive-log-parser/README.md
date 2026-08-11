# 自适应日志解析系统

一个具有自愈能力的日志解析系统，能够自动检测未知日志格式，调用大语言模型（LLM）生成解析代码，并通过自动测试后热加载到系统中。

## 功能概述

- **自动检测失败**：当遇到无法解析的日志格式时，自动检测并触发自愈流程
- **代码生成**：使用 LLM 自动生成 Python 解析函数
- **自动测试**：对生成的代码进行数据结构断言测试
- **热加载注册**：测试通过后自动注册到解析引擎
- **持久化复用**：生成的解析器保存到 `parsers/` 目录，下次启动直接加载
- **迭代修复**：测试失败时自动反馈给 LLM 重新生成（最多 3 次）

## 技术亮点

- **自愈闭环**：失败检测 → 生成 → 测试 → 热更新 → 持久化
- **纯函数解析器**：每个解析器都是独立的 `parse(line) -> dict` 函数
- **解析器链式尝试**：依次尝试所有解析器，返回第一个成功的结果
- **离线演示模式**：无需 API Key 即可演示完整流程

## 快速开始

### 1. 环境准备

确保在项目根目录（`ai-agant/`）操作：

```bash
cd ai-agant
source .venv/bin/activate
```

### 2. 配置 LLM

在项目根目录的 `.env` 文件中配置：

```bash
# LLM 配置（必填）
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3   # 可选，使用提供商默认模型
```

### 3. 运行演示

```bash
# 完整演示（需要 LLM API Key）
python3 chapter5/adaptive-log-parser/demo.py

# 离线演示（无需 API Key，使用预置解析器）
python3 chapter5/adaptive-log-parser/demo.py --offline

# 快速模式（仅演示 1 种新格式）
python3 chapter5/adaptive-log-parser/demo.py --quick

# 查看帮助
python3 chapter5/adaptive-log-parser/demo.py --help
```

## 使用方法

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--offline` | 离线模式：使用预置解析器，无需 API Key |
| `--quick` | 快速模式：仅演示 1 种新格式 |
| `--model MODEL` | 指定使用的模型名称 |
| `--log-file PATH` | 使用外部日志文件进行持久化验证 |
| `--output PATH` | 将解析结果输出为 JSONL 格式 |

### 编程接口

```python
from engine import LogParserEngine, builtin_json_parser
from agent import CodeGenAgent

# 创建引擎并注册内置解析器
engine = LogParserEngine()
engine.register("builtin_json", builtin_json_parser)

# 解析日志
result = engine.parse_line('{"timestamp": "...", "level": "INFO", "message": "..."}')
print(result)
```

## 项目结构

```
chapter5/adaptive-log-parser/
├── agent.py          # 代码生成 Agent（LLM 调用封装）
├── engine.py         # 日志解析引擎（解析器注册表）
├── tester.py         # 自动测试模块（数据结构断言）
├── demo.py           # 演示主程序
├── requirements.txt  # 依赖声明（核心依赖由项目根目录提供）
├── parsers/          # 生成的解析器存放目录
│   └── .gitkeep
├── results/          # 输出结果目录
└── logs/             # 日志目录
```

## 配置说明

### LLM 配置

本项目使用项目根目录的统一 LLM 配置（`.env` 文件）：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或其他支持的提供商
LLM_MODEL=kimi-k3   # 可选
```

### 支持的 LLM 提供商

| 提供商 | `LLM_PROVIDER` | 示例模型 |
|--------|----------------|----------|
| Kimi | `kimi` | `kimi-k3` |
| SiliconFlow | `siliconflow` | `Qwen/Qwen2.5-7B-Instruct` |
| DeepSeek | `deepseek` | `deepseek-chat` |
| 阿里云 | `aliyun` | `qwen3.7-max-2026-05-20` |
| 自定义 | `custom` | 任意（需配置 `BASE_URL`） |

## 自愈流程详解

```
一行日志
   │
   ▼
[解析引擎] 依次尝试已注册的解析器
   │
   ├── 有解析器认识 → 输出结构化字段 ✅
   │
   └── 全部失败（检测到新格式）❌
           │  失败样本 + 报错
           ▼
      [代码生成 Agent]  ← LLM API
           │  生成 def parse(line)->dict|None
           ▼
      [自动测试]  数据结构断言
           │
           ├── 不通过 → 把失败报告反馈给 Agent 重试（最多 3 次）
           │
           └── 通过 → [热加载注册] + 持久化到 parsers/*.py
                        │
                        ▼
              系统现在能正确解析该新格式 ✅（下次重启直接复用）
```

### 流程步骤

1. **失败检测**：解析引擎遇到无法识别的格式，抛出 `ParseError`
2. **代码生成**：将失败样本和错误信息发送给 LLM，生成解析代码
3. **自动测试**：对生成的代码进行数据结构断言测试
4. **迭代修复**：如果测试失败，将失败报告反馈给 LLM 重新生成（最多 3 次）
5. **热加载注册**：测试通过后，将解析器注册到引擎
6. **持久化**：将生成的代码保存到 `parsers/` 目录

## 演示的三种日志格式

1. **基础 JSON 行**（系统原生支持）：
   ```
   {"timestamp": "2026-07-17T10:22:31Z", "level": "INFO", "message": "Agent started"}
   ```

2. **竖线分隔格式**（Agent 自动生成）：
   ```
   2026-07-17T10:23:01Z|INFO|agent.planner|step=3|Generated plan with 5 actions
   ```

3. **嵌套括号格式**（Agent 自动生成）：
   ```
   [2026-07-17 10:24:55] (ERROR) <tool=web_search> {latency_ms=812} :: upstream failed
   ```

## 故障排除

### 问题：导入错误 `No module named 'llm'`

**原因**：Python 路径未正确设置

**解决**：确保从项目根目录运行，或设置 `PYTHONPATH`：

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 chapter5/adaptive-log-parser/demo.py
```

### 问题：API Key 错误

**原因**：`.env` 文件配置缺失或错误

**解决**：检查项目根目录 `.env` 文件中的 `API_KEY` 配置

### 问题：离线模式运行正常，在线模式报错

**原因**：LLM API 配置问题或网络问题

**解决**：检查 `.env` 中的 LLM 配置，或使用 `--offline` 模式测试

## 技术要点

### 解析器接口规范

每个解析器必须遵循以下接口：

```python
def parse(line: str) -> dict | None:
    """
    解析一行日志

    Args:
        line: 日志字符串

    Returns:
        解析出的字段字典，或 None（格式不匹配时）
    """
    # 实现解析逻辑
    ...
```

**重要**：如果日志行不符合该解析器的格式，必须返回 `None`（而不是抛出异常），以便其他解析器有机会尝试。

### 必需字段验证

测试模块会验证：
1. 解析函数不抛出异常
2. 返回非空字典
3. 包含所有必需字段且值不为空

### 热加载机制

解析器代码动态加载方式：

1. 将生成的代码写入 `parsers/xxx.py`
2. 使用 `importlib` 动态导入模块
3. 提取 `parse` 函数并注册到引擎

## 扩展指南

### 添加新的日志格式

在 `demo.py` 中按以下格式添加：

```python
# 定义日志样本
YOUR_LOGS = [
    "你的日志样本1",
    "你的日志样本2",
]

# 定义必需字段
YOUR_REQUIRED = ["field1", "field2", "field3"]

# 调用自愈函数
ok = self_heal(engine, agent, "your_parser", YOUR_LOGS, YOUR_REQUIRED)
```

### 接入真实日志流

```python
from engine import LogParserEngine, ParseError

engine = LogParserEngine()
engine.load_persisted("parsers/")  # 加载已学习的解析器

for line in log_stream:
    try:
        result = engine.parse_line(line)
        print(result)
    except ParseError as e:
        print(f"无法解析：{e.line}")
        # 这里可以触发自愈流程
```

## 输出示例

```
============================================================================
步骤 1：遇到新格式 A —— 自定义竖线分隔格式
(a) 先让系统解析，预期【失败】：
  ❌ 解析失败：2026-07-17T10:23:01Z|INFO|agent.planner|step=3|Generated plan...

触发自愈闭环：
  🔎 检测到无法解析的新格式，触发自愈。

  --- 第 1/3 次：Agent 生成解析代码 ---
    | import re
    | def parse(line: str) -> dict | None:
    |     pattern = r"^(?P<timestamp>\S+)\|(?P<level>\S+)\|..."
    |     ...

  🧪 自动测试（数据结构断言）：
    [样本1] 通过，解析出字段：['level', 'message', 'module', 'step', 'timestamp']

  ✅ 自动测试通过，已热更新注册解析器 'pipe_parser'

(c) 热更新后重新解析同样的日志，预期【成功】：
  ✅ [pipe_parser] {'timestamp': '...', 'level': 'INFO', ...}
```

## 注意事项

- **代码安全**：Agent 生成的代码通过 `importlib` 直接执行，仅适用于可信实验环境
- **不确定性**：LLM 生成代码存在不确定性，设置了最多 3 次重试机制
- **离线模式**：使用 `--offline` 参数可无需 API Key 演示完整流程
