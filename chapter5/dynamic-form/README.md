# 动态表单生成的意图澄清系统

## 功能概述

当用户请求缺少关键信息时，Agent 不是逐条追问，而是**动态生成一个自包含的 HTML 表单**（含级联显示逻辑），让用户"一次提交"补全所有澄清点。前端把表单汇总成 JSON 交回 Agent，Agent 解析后继续任务。

### 核心特性

- **动态表单生成**：Agent 根据用户请求自动生成包含所有缺失字段的 HTML 表单
- **级联逻辑支持**：支持字段间的级联显示/隐藏和动态选项更新
- **双模式运行**：
  - **在线模式**：使用 LLM 实时生成表单代码
  - **离线模式**：使用内置 schema 确定性渲染表单，无需 API Key
- **自包含 HTML**：生成的表单为单文件 HTML，可直接在浏览器中打开使用
- **结构化校验**：自动验证生成的表单是否符合要求

### 支持的级联类型

1. **显示/隐藏级联**（`show_when`）：某字段仅当另一字段等于某值时才显示
   - 示例：返程日期仅在选择"往返"时显示

2. **选项动态级联**（`options_when`）：某下拉框的可选项随另一字段的取值动态更新
   - 示例：免费行李额度随舱位等级变化

## 快速开始

### 1. 环境准备

确保项目根目录的虚拟环境已激活：

```bash
cd ai-agant
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r chapter5/dynamic-form/requirements.txt
```

### 3. 配置 LLM（在线模式）

在项目根目录的 `.env` 文件中配置：

```bash
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或其他支持的提供商
LLM_MODEL=kimi-k3   # 可选，使用默认模型
```

支持的提供商：`kimi`、`openai`、`deepseek`、`anthropic`、`aliyun` 等

### 4. 运行

#### 在线模式（使用 LLM 生成表单）

```bash
python chapter5/dynamic-form/demo.py
```

#### 离线模式（使用内置 schema，无需 API Key）

```bash
python chapter5/dynamic-form/demo.py --offline
```

#### 启动本地服务（浏览器体验）

```bash
python chapter5/dynamic-form/demo.py --offline --serve
```

服务将在 `http://127.0.0.1:8000` 启动并自动打开浏览器。

## 使用方法

### 命令行参数

```bash
python demo.py [选项]

选项：
  -r, --request TEXT    用户的模糊请求（默认："我想订一张去北京的机票"）
  -o, --output PATH     生成的 HTML 输出路径（默认：generated_form.html）
  --model MODEL         覆盖模型名
  --offline             离线模式：不调用 LLM
  --serve               生成后启动本地 HTTP 服务
  --port N              服务端口（默认：8000）
  -h, --help            显示帮助信息
```

### 内置表单 Schema

离线模式使用预定义的机票预订表单 schema：

| 字段 | 类型 | 必填 | 级联逻辑 |
|------|------|------|----------|
| departure_city | text | 是 | - |
| departure_date | date | 是 | - |
| trip_type | radio | 是 | - |
| return_date | date | 否 | 仅当 trip_type=round_trip 时显示 |
| cabin_class | select | 否 | - |
| baggage_count | select | 否 | 可选项随 cabin_class 变化 |

## 项目结构

```
chapter5/dynamic-form/
├── demo.py                  # 主程序
├── generated_form.html      # 生成的表单（运行后生成）
├── requirements.txt         # 项目特定依赖
├── results/                 # 结果输出目录
├── logs/                    # 日志目录
└── README.md               # 本文档
```

## 技术要点

### 1. 统一 LLM 客户端

项目使用统一的 LLM 客户端封装：

```python
from llm.client import get_llm_client

client = get_llm_client()
model = client.model_name
```

### 2. 路径处理

为确保模块可正常导入，每个文件开头添加路径处理代码：

```python
import sys
import os

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
```

### 3. 表单 Schema 定义

使用声明式 schema 定义表单结构和级联逻辑：

```python
FLIGHT_FORM_SCHEMA = {
    "title": "机票预订 · 意图澄清表单",
    "fields": [
        {
            "name": "return_date",
            "label": "返程日期",
            "type": "date",
            "show_when": {"field": "trip_type", "equals": "round_trip"},
        },
        # ...
    ],
}
```

### 4. 级联运行时

表单包含原生 JavaScript 运行时，支持：
- 字段显示/隐藏控制
- 下拉选项动态更新
- 提交数据 JSON 化

## 故障排除

### 问题：无法导入 llm.client

**原因**：未从项目根目录运行

**解决**：确保在项目根目录运行，或添加 PYTHONPATH

```bash
export PYTHONPATH=$PYTHONPATH:/path/to/ai-agant
```

### 问题：API_KEY 未配置

**原因**：项目根目录 .env 文件未配置

**解决**：
1. 在 `ai-agant/.env` 中添加 `API_KEY=your-key`
2. 或使用 `--offline` 参数跳过 LLM 调用

### 问题：生成的表单校验未通过

**原因**：LLM 输出不稳定

**解决**：
1. 重试生成
2. 或使用 `--offline` 模式获得稳定输出

## 运行示例

```
====================================================================
用户请求: 我想订一张去北京的机票
运行模式: 在线（Agent 调用 LLM，模型 kimi-k3）
====================================================================

[步骤 1] 生成澄清表单 HTML ...
  已保存到 generated_form.html （共 2456 字符）

[步骤 2] 结构化校验表单字段与级联逻辑：
  [PASS] 出发城市(文本输入)
  [PASS] 出发日期(日期选择器)
  [PASS] 旅行类型(单选:单程)
  [PASS] 旅行类型(单选:往返)
  [PASS] 返程日期(日期选择器)
  [PASS] 返程字段级联逻辑(仅往返显示)

[步骤 3] 模拟用户一次性提交表单（往返场景）：
{
  "departure_city": "上海",
  "departure_date": "2026-08-01",
  "trip_type": "round_trip",
  "return_date": "2026-08-07",
  "cabin_class": "business",
  "baggage_count": "2",
  "destination_city": "北京"
}

[步骤 3] 解析 JSON 并继续任务，输出订票摘要：
--------------------------------------------------------------------
已收到您的订票信息：上海 → 北京，出发日期 2026-08-01。
行程类型：往返，返程日期 2026-08-07。
舱位：公务舱，免费托运 2 件。
正在为您检索航班...
-------------------------------------------------------------------- （模型 kimi-k3）

====================================================================
表单字段/级联校验: 全部通过
提交 JSON 解析: 成功（见上方订票摘要）
====================================================================
```
