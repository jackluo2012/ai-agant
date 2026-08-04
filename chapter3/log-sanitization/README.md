# 日志脱敏系统 / Log Sanitization

> 配套《深入理解 AI Agent》第 3 章——在保留调试信息的同时检测并脱敏日志中的敏感数据。

← [返回第 3 章目录](../README.md)

---

## 概述

演示如何从 Agent 的日志与工具输出中检测并脱敏敏感信息。提供**两种互补的脱敏引擎**：

1. **离线规则引擎（regex，默认）** —— 纯正则表达式 + 校验算法（Luhn、身份证校验码），**无需 LLM、无需网络**，结果确定、速度快，适合作为日志落盘前的第一道防线。同时覆盖 Agent 场景中最常泄露的**密钥类**敏感信息（API Key、云厂商令牌、私钥、连接串口令）与传统 **PII**（身份证、手机号、信用卡、邮箱等）。

2. **LLM 引擎（llm）** —— 使用统一 LLM 客户端语义识别 Level 3 PII（社保号、信用卡、病历号等）。**自动读取项目根目录 `.env` 配置**。

### 离线规则引擎覆盖的敏感信息类别

| 类别 | 占位符 | 说明 |
| --- | --- | --- |
| 私钥 / 证书 | `[REDACTED_PRIVATE_KEY]` | PEM 私钥块 |
| JWT | `[REDACTED_JWT]` | `eyJ...` 三段式令牌 |
| 连接串凭据 | `[REDACTED_URL_CRED]` | `scheme://user:PASSWORD@host` |
| AWS 访问密钥 | `[REDACTED_AWS_KEY]` | `AKIA...` |
| GitHub / Slack / Google / OpenAI 密钥 | `[REDACTED_*_TOKEN]` / `[REDACTED_API_KEY]` | `ghp_`、`xoxb-`、`AIza`、`sk-` |
| Bearer 令牌 | `[REDACTED_BEARER_TOKEN]` | `Authorization: Bearer ...` |
| 口令 / 密钥赋值 | `[REDACTED_SECRET]` | `password=...`、`token: ...` 等 |
| 邮箱 | `[REDACTED_EMAIL]` | |
| 信用卡号 | `[REDACTED_CREDIT_CARD]` | 通过 Luhn 校验，降低误报 |
| IBAN | `[REDACTED_IBAN]` | 国际银行账号 |
| 美国社保号 | `[REDACTED_SSN]` | |
| 身份证号 | `[REDACTED_ID_CARD]` | 中国大陆 18 位，含校验码验证 |
| 手机号 | `[REDACTED_PHONE]` | 中国大陆 |
| IP 地址 | `[REDACTED_IP]` | IPv4 |

### Level 3 PII 类别（LLM 引擎）

隐私架构中的高敏感信息，包括：社保号、信用卡、银行账号、病历号、诊断与治疗信息、处方、驾照、护照、金融 PIN、税号、医保 ID、生物特征数据等。

## 功能

- **离线规则引擎**：正则 + Luhn/身份证校验；覆盖密钥/机密与 PII；无需模型与网络
- **LLM 引擎**：使用统一 LLM 客户端做隐私友好的 PII 检测
- **自动配置读取**：自动读取项目根目录 `.env` 配置
- **双模型支持**：支持大模型（阿里云等）和小模型（Ollama）
- **流式输出**：实时显示检测进度
- **性能指标**：TTFT、token 数、处理速度

## 配置

### LLM 配置（项目根目录 `.env`）

项目已配置阿里云大模型，无需额外设置：

```bash
# 当前配置（大模型）
LLM_PROVIDER=aliyun
LLM_MODEL=qwen3.7-max-2026-05-20
BASE_URL=https://ws-i3szl9yu7ek6ihrf.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
```

### 小模型配置（llama.cpp）

项目已配置 llama.cpp 小模型服务器：

```bash
# llama.cpp 配置
服务器地址: 192.168.1.158:11434
模型: MiniCPM5-1B-Q4_K_M.gguf
```

## 用法

### 离线规则演示（推荐，无需 LLM）

```bash
cd ai-agant
source .venv/bin/activate
python chapter3/log-sanitization/main.py --demo
```

### 使用 LLM 引擎（自动读取 .env 配置）

```bash
# 使用 .env 配置的模型（默认阿里云大模型）
python chapter3/log-sanitization/main.py --demo --mode llm

# 脱敏日志文件
python chapter3/log-sanitization/main.py --input app.log --mode llm
```

### 使用本地小模型（llama.cpp）

```bash
# 使用 llama.cpp 小模型
python chapter3/log-sanitization/main.py --demo --mode llm --small-model
python chapter3/log-sanitization/main.py --input app.log --mode llm --small-model
```

### 批量处理评测用例

```bash
# 使用 .env 配置的模型
python chapter3/log-sanitization/main.py

# 指定用例
python chapter3/log-sanitization/main.py --test-id layer3_01_travel_coordination

# 限制数量
python chapter3/log-sanitization/main.py --limit 3
```

## 输出结构

脱敏日志与指标保存在 `results/` 目录：

```
results/
├── <test_id>_sanitized.txt        # 脱敏后的对话文本
├── <test_id>_summary.json         # 发现与替换的 PII 摘要
├── performance_metrics.json       # 详细性能指标
└── performance_summary.json       # 聚合性能统计
```

## 性能指标

**时间：** Prefill（TTFT）、输出时间、总时间（毫秒）
**Token：** 输入/输出数量；Prefill/输出速度（tok/s）
**脱敏：** 发现的 PII 条数；替换为 `[REDACTED]` 的次数

## 架构

1. **regex_sanitizer.py**：离线规则脱敏（正则 + Luhn/身份证校验）
2. **samples.py**：离线演示用的代表性 Agent 日志样本
3. **config.py**：PII 类别配置
4. **test_loader.py**：从评测框架加载用例
5. **agent.py**：基于统一 LLM 客户端的脱敏逻辑
6. **metrics.py**：性能指标采集与报告
7. **main.py**：入口与编排

## 工作原理（LLM 路径）

1. 从评测框架加载对话历史
2. 将每段对话送入 LLM（.env 配置的模型或小模型）
3. 用专用提示检测 Level 3 PII
4. 将检出值替换为 `[REDACTED]`
5. 采集性能指标
6. 将脱敏日志与性能摘要写入 `results/`

## 隐私考量

- LLM 路径会向配置的 API 端点发送数据
- 小模型（Ollama）在本地运行，数据不离开本机
- 脱敏日志使用占位符；任何原始 PII 日志都应妥善保管

## 故障排除

**找不到评测框架：** 确认 `../user-memory-evaluation/` 存在
**LLM 初始化失败：** 检查项目根目录 `.env` 配置
**小模型不可用：** 确认 llama.cpp 服务器正在运行（192.168.1.158:11434）

---

## 技术要点

### 离线规则引擎设计

- 优先级处理：高优先级规则（如私钥）优先匹配
- 校验算法：Luhn 算法用于信用卡，加权校验用于身份证
- 性能优化：预编译正则表达式

### LLM 引擎设计

- 自动配置读取：使用 `llm.client` 统一客户端
- 双模型支持：大模型（.env 配置）和小模型（Ollama）
- 结构化输出：使用 JSON Schema 约束输出格式
- 流式处理：实时显示检测进度和性能指标
- 容错处理：JSON 解析失败时回退到简单分行处理

---

## 说明

- 建议先运行 `--demo` 查看效果；规则路径无需 LLM。
- LLM 模式自动读取项目根目录的 `.env` 配置。
- 小模型模式需要单独配置并启动 Ollama。
