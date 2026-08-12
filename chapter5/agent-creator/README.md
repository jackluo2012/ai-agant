# 实验 5-13：创建 Agent 的 Agent

这是《AI Agent 开发实战》第 5 章实验 5-13 的可运行代码。该项目实现了完整的对比实验，使用真实的 LLM 来创建两个专门的 Agent：

1. **从零创建**：无参考实现，完全生成 Agent 循环、工具协议、领域工具、CLI 和测试
2. **模板适配**：复制已验证的 `reference_agent`，保留其标准消息/工具循环，仅生成领域特定的提示词、工具模式、实现、文档和测试

两个输出都通过相同的验证门：
- 必需文件和密钥扫描
- Python AST/编译验证
- 标准 `assistant.tool_calls → role=tool` 协议审计
- 有界循环审计
- 生成的 pytest 测试套件
- 在其自己的示例任务上真实运行生成的 Agent

## 功能概述

- **统一 LLM 配置**：使用项目根目录的统一 `.env` 配置，支持多种 LLM 提供商
- **双模式对比**：从零创建 vs 模板适配的完整对比实验
- **可恢复生成**：支持断点续传，避免重复消耗 token
- **语义验证**：使用 LLM 对生成的 Agent 进行语义判断
- **完整验证链**：结构检查 → 编译验证 → 测试通过 → 实时运行 → 语义审计

## 快速开始

### 1. 环境准备

确保您已设置项目根目录的虚拟环境：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
```

### 2. 配置 LLM

在项目根目录 `.env` 文件中配置 LLM：

```bash
# LLM 配置（所有章节共享）
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3   # 可选，使用提供商默认模型
BASE_URL=  # 可选，使用提供商默认端点
```

### 3. 安装依赖

```bash
cd chapter5/agent-creator
pip install -r requirements.txt
```

注意：核心依赖（`openai>=1.30.0`, `python-dotenv>=1.0.0`）由项目根目录 `requirements.txt` 提供。

### 4. 运行实验

```bash
# 使用默认需求运行
python demo.py --output runs/release-agent

# 使用自定义需求运行
python demo.py \
  --requirements "创建一个事件分流 Agent，查询服务健康状况并起草基于证据的升级处理" \
  --output runs/incident-triage

# 跳过实时运行（仅用于 CI/测试）
python demo.py --no-live --output runs/test-only

# 断点续传（修复和重新验证已生成的分支）
python demo.py --resume --output runs/release-agent
```

## 项目结构

```
agent-creator/
├── creator.py           # 核心创建器，实现两种生成策略
├── validator.py         # 结构、测试和实时运行验证
├── demo.py              # 命令行入口
├── experiment_protocol.json  # 实验协议配置
├── requirements.txt     # 项目特定依赖
├── env.example          # 配置示例
├── reference_agent/     # 参考实现（模板模式使用）
│   ├── agent.py         # Agent 核心循环
│   ├── domain_tools.py  # 领域工具
│   ├── main.py          # CLI 入口
│   ├── system_prompt.md # 系统提示词
│   ├── domain_spec.json # 领域规范
│   └── tools.json       # 工具模式
├── results/             # 输出目录
└── logs/                # 日志目录
```

## 配置说明

### LLM 配置（项目根目录 .env）

所有 LLM 相关配置统一在项目根目录的 `.env` 文件中管理：

```bash
# 必需配置
API_KEY=your-api-key-here
LLM_PROVIDER=kimi  # 提供商：kimi, siliconflow, doubao, deepseek, aliyun 等

# 可选配置
LLM_MODEL=kimi-k3
BASE_URL=https://api.moonshot.cn/v1
```

### 实验特定配置（本地 env.example）

```bash
# 请求超时（秒）
AGENT_CREATOR_REQUEST_TIMEOUT=600

# 提供商选择（测试用）
# AGENT_CREATOR_PROVIDER=auto
# AGENT_CREATOR_MODEL=
```

## 输出说明

实验运行后，输出目录包含：

```
runs/release-agent/
├── scratch/              # 从零创建的 Agent
├── template/             # 模板适配的 Agent
└── comparison.json       # 对比结果报告
```

`comparison.json` 包含：
- 生成时间和 token 使用
- 每个验证门的结果
- 实时 Agent 追踪
- 获胜策略
- 语义判断结果

## 安全边界

- 生成的路径经过白名单限制
- 凭据绝不放入提示词或生成的文件
- 仅在通过结构和测试门之后才执行实时运行
- 生成的领域工具仍执行本地代码，使用前请审查

## 技术要点

1. **统一 LLM 封装**：通过 `llm.client.get_llm_client()` 获取统一客户端
2. **路径处理**：每个 Python 文件都包含项目根目录路径处理代码
3. **中文化**：所有提示词、注释、用户可见消息均已中文化
4. **可恢复性**：生成过程使用检查点机制，支持断点续传

## 故障排除

### 导入错误

如果出现 `ImportError: No module named 'llm.client'`：

```bash
# 确保从项目根目录运行
cd /home/jackluo/my/ai-agent/ai-agant
export PYTHONPATH=$PYTHONPATH:$(pwd)
source .venv/bin/activate
python chapter5/agent-creator/demo.py
```

### API 密钥错误

确保项目根目录 `.env` 文件中配置了有效的 `API_KEY`。

### 超时错误

增加请求超时时间：

```bash
AGENT_CREATOR_REQUEST_TIMEOUT=1200 python demo.py
```
