# 多角色自主移交系统

实验 10-1：在同一条共享对话轨迹上，对比两种实现多角色行为的方法。

## 功能概述

本项目实现了一个多角色自主移交系统，Agent 可以根据任务需求自主判断并移交控制权给更合适的专业角色。系统支持两种实现路径：

1. **系统提示词切换**：`transfer_to_agent(target_role, reason)` 替换当前角色的系统提示词和工具集，保留对话历史
2. **Skill 加载**：固定系统提示词和工具目录，通过 `load_skill(name)` 将相应的 `SKILL.md` 追加到对话轨迹

### 五个专业角色

| 角色 | 说明 | 专属工具集 |
|------|------|-----------|
| `triage` | 前台分诊/默认入口，拆解需求并按序移交、最后收尾 | 仅 `transfer_to_agent` |
| `research` | 信息检索专家 | `web_search`（真实 Tavily 检索） |
| `coding` | 编程专家 | `execute_python`（真实执行代码） |
| `data_analysis` | 数据分析专家 | `calculate`、`descriptive_stats` |
| `writing` | 写作专家 | `count_characters` |

## 快速开始

### 1. 环境准备

确保项目根目录的虚拟环境已激活：

```bash
# 从项目根目录
cd ai-agant
source .venv/bin/activate  # Linux/macOS
# 或 .\.venv\Scripts\Activate.ps1  # Windows PowerShell
```

### 2. 安装依赖

```bash
pip install -r chapter10/multi-role-transfer/requirements.txt
```

### 3. 配置 LLM

在**项目根目录**的 `.env` 文件中配置 LLM 服务：

```bash
# LLM 配置（必填）
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 openai、deepseek、siliconflow 等
LLM_MODEL=kimi-k3   # 可选，默认使用 kimi-k3

# 搜索服务（research 角色需要）
TAVILY_API_KEY=your-tavily-key
```

支持的 LLM 提供商：
- `kimi`（Moonshot）
- `openai`（OpenAI）
- `deepseek`
- `siliconflow`
- `doubao`（字节跳动）
- `aliyun`（阿里云，需配置 BASE_URL）

### 4. 运行演示

```bash
cd chapter10/multi-role-transfer

# 基础演示（默认 CAGR 场景）
python demo.py

# 离线查看角色/场景清单（无需 API Key）
python demo.py --list-roles

# 指定场景
python demo.py --scenario coding

# 交互式多轮对话
python demo.py --interactive
```

## 使用方法

### demo.py — 单次演示

```bash
# 查看帮助
python demo.py --help

# 常用参数
python demo.py --scenario cagr           # 选择内置场景
python demo.py --task "自定义任务"       # 自定义任务
python demo.py --role research          # 指定起始角色
python demo.py --model gpt-4o            # 临时更换模型
python demo.py --max-steps 30            # 设置最大步数
```

### run_comparison.py — 成对对比运行

```bash
# 基础对比
python run_comparison.py \
  --model kimi-k3 \
  --trials 5 \
  --output validation/comparison/result.json

# 使用任务文件
python run_comparison.py \
  --task-file tasks.example.json \
  --trials 10 \
  --output validation/comparison/pilot.json

# 带成本计算
python run_comparison.py \
  --input-price-per-million 0.5 \
  --output-price-per-million 2.0 \
  --output validation/comparison/cost-result.json
```

### run_official_experiment.py — 正式实验运行

```bash
python run_official_experiment.py \
  --run-id exp10-1-kimi-tavily-$(date +%Y%m%d)
```

## 项目结构

```
chapter10/multi-role-transfer/
├── demo.py                    # 演示入口
├── orchestrator.py            # 移交编排器（路径一）
├── skill_orchestrator.py      # Skill 编排器（路径二）
├── roles.py                   # 角色定义
├── tools.py                   # 工具实现
├── evaluation.py              # 评分标准
├── run_comparison.py          # 成对对比运行
├── run_official_experiment.py # 正式实验
├── skills/                    # Skill 目录（路径二）
│   ├── triage/
│   ├── research/
│   ├── coding/
│   ├── data_analysis/
│   └── writing/
├── results/                   # 输出目录
├── logs/                      # 日志目录
└── validation/                # 验证数据
```

## 内置场景

- `cagr`（默认）：新能源汽车销量 → CAGR 计算 → 投资总结
- `solar`：光伏装机数据 → CAGR 计算 → 结论
- `coding`：斐波那契数列计算 → 结果解释

## 配置说明

### LLM 配置（项目根目录 .env）

```bash
# 必填
API_KEY=your-api-key
LLM_PROVIDER=kimi

# 可选
LLM_MODEL=kimi-k3
BASE_URL=https://api.moonshot.cn/v1  # 自定义端点（部分提供商需要）
```

### Tavily 搜索配置

```bash
TAVILY_API_KEY=your-tavily-key
TAVILY_TIMEOUT_SECONDS=20
TAVILY_MAX_RESULTS=5
```

## 命令行参数

### demo.py 参数

| 参数 | 说明 |
|------|------|
| `--list-roles` | 离线查看角色/场景清单 |
| `--scenario` | 选择内置场景（cagr/solar/coding） |
| `--task` | 自定义任务文本 |
| `--role` | 指定起始角色 |
| `--interactive` | 交互式多轮模式 |
| `--model` | 临时覆盖模型 |
| `--max-steps` | 最大步数（默认 20） |

### run_comparison.py 参数

| 参数 | 说明 |
|------|------|
| `--model` | 模型名称 |
| `--trials` | 每个任务的重复次数 |
| `--task-file` | 任务 JSON 文件 |
| `--task` | 单个任务文本 |
| `--output` | 输出文件路径 |
| `--max-steps` | 最大步数 |
| `--skip-boundary` | 跳过边界测试 |
| `--input-price-per-million` | 输入价格（每百万 token） |
| `--cached-input-price-per-million` | 缓存输入价格 |
| `--output-price-per-million` | 输出价格 |

## 输出说明

### 运行汇总

每次运行后输出：
- 自主移交链（如：triage → research → data_analysis → writing）
- 各角色分工（谁用了什么工具）
- 移交次数和原因
- 最终成果

### 验证输出

正式实验运行保存：
- `evidence.json` — 完整轨迹
- `moonshot_receipts.json` — LLM 回执
- `tavily_receipts.json` — 搜索回执
- `acceptance.json` — 验收结论
- `manifest.json` — 完整性清单

## 故障排除

### LLM 客户端初始化失败

```
错误：无法导入 LLM 客户端
```

**解决方法**：确保项目根目录的 `.env` 文件存在且包含有效的 `API_KEY` 和 `LLM_PROVIDER`。

### Tavily 搜索失败

```
web_search requires TAVILY_API_KEY; no mock fallback is allowed
```

**解决方法**：在 `.env` 文件中配置 `TAVILY_API_KEY`。

### 移交死循环

系统设有 `max_steps`（默认 20）硬上限，以及重复调用检测，防止死循环。

### 模型指令遵循差异

不同模型的指令遵循能力不同，可能影响移交链的完整性。建议使用能力较强的模型。

## 技术要点

### 共享对话历史

两条路径都维护一段共享的对话历史（user/assistant/tool 消息），角色切换时历史保持不变，确保新角色能看到此前的全部内容。

### 自主移交机制

- **路径一**：通过 `transfer_to_agent(target_role, reason)` 替换系统提示词和工具集
- **路径二**：通过 `load_skill(name)` 追加 Skill 文档到轨迹

### 真实工具执行

- `web_search`：真实 Tavily 联网检索，无 mock 回退
- `execute_python`：真实执行 Python 代码
- `calculate`：安全数学表达式求值
- `count_characters`：中英文字数统计

### 前缀缓存差异

- **路径一**：每次切换角色都会改变前缀（系统提示词+工具集）
- **路径二**：保持固定前缀，Skill 内容通过工具结果追加

## 离线验证

```bash
# 语法验证（无需 API Key）
python -m py_compile chapter10/multi-role-transfer/*.py

# 离线测试
python demo.py --list-roles
```

## 测试

```bash
cd chapter10/multi-role-transfer
python -m pytest tests/
```

测试包含：
- 工具分发错误处理
- `execute_python` 超时处理
- 角色移交机制验证

## 架构权衡

| 属性 | 路径一（系统提示词） | 路径二（Skill 加载） |
|------|---------------------|-------------------|
| 角色指令位置 | 替换 system prompt | 追加 Skill 工具结果 |
| 工具可见性 | 只暴露当前角色工具 | 固定暴露全部工具 |
| 前缀缓存 | 每次切换重新计算 | 保持稳定 |
| 硬约束 | 可限制越界工具 | 需额外权限门 |
| 实现复杂度 | 动态切换 | 固定循环+加载器 |

## 注意事项

1. **API Key 安全**：不要将 API Key 提交到版本控制系统
2. **成本控制**：正式运行前建议先小规模测试
3. **模型选择**：不同模型的指令遵循能力会影响移交链完整性
4. **缓存收益**：Skill 加载路径可能有更好的前缀缓存收益，但需要更长任务才能体现
