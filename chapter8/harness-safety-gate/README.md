# 实验 8-8：Harness 安全策略门禁

本项目演示实验 8-8 的 Harness 安全层自我进化：用户纠正、用户点踩与事后审计三类外部反馈共同指向同一个流程缺陷——`delete_file`、`git_push(force=True)`、`sql_query("DROP TABLE ...")` 等不可逆调用在未经用户确认时就被执行。系统据此让 Coding Agent 为 Harness 生成"高风险调用确认门禁"提案，经模型外验证门槛后才允许灰度。

## 功能概述

- **安全策略门禁**：检查工具调用参数（路径遍历、危险 bash 命令、资源限制）
- **确认机制**：高风险操作强制要求用户确认
- **自动回滚**：安全违规时触发状态回滚
- **候选生成**：通过 LLM 或确定性模板生成候选确认门禁代码
- **模型外验证**：AST 静态检查 + 边界集/保留集回放验证

## 快速开始

### 1. 环境准备

确保已激活项目虚拟环境（位于项目根目录 `.venv`）：

```bash
cd ai-agant
source .venv/bin/activate  # Linux/macOS
# 或 .venv\Scripts\activate  # Windows
```

### 2. 配置 LLM

在项目根目录 `.env` 文件中配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3   # 可选
```

### 3. 运行测试

```bash
cd chapter8/harness-safety-gate

# 运行单元测试
python -m pytest -q test_evolution.py

# 离线模式（不调用 API）
python run_experiment_8_8.py --quick

# 单提案演示
python demo.py --generator deterministic
```

## 使用方法

### 真实 LLM 模式

调用真实 LLM 生成候选代码：

```bash
# 使用默认模型（从 .env 读取）
python run_experiment_8_8.py

# 指定模型和种子
python run_experiment_8_8.py --seed 8801
```

### 离线模式

仅验证确定性候选与反例，不调用 API：

```bash
python run_experiment_8_8.py --quick
```

### 生成单提案演示

```bash
# 使用确定性生成器
python demo.py --generator deterministic

# 使用真实 LLM
python demo.py --generator llm --model <模型名称>
```

## 项目结构

```
chapter8/harness-safety-gate/
├── evolution.py              # 演化流水线核心逻辑
├── llm_generator.py          # LLM 候选生成器
├── safety_policy_gate.py     # 安全策略门禁实现
├── run_experiment_8_8.py     # 验收入口
├── demo.py                   # 教学演示入口
├── stable/                   # 稳定版代码
│   └── tool_dispatcher.py
├── validation/               # 验证证据输出目录
├── results/                  # 结果输出目录
├── logs/                     # 日志目录
├── failure_trajectories.json # 失败轨迹数据
├── boundary_cases.json       # 边界测试用例
└── retention_cases.json     # 保留测试用例
```

## 配置说明

### LLM 配置（项目根目录 .env）

所有 LLM 相关配置在项目根目录的 `.env` 文件中统一管理：

```bash
# LLM 提供商配置
API_KEY=your-api-key
LLM_PROVIDER=kimi
LLM_MODEL=kimi-k3
BASE_URL=  # 可选，默认由提供商决定
```

### 环境变量

- `SAFETY_GATE_SECRET_KEY`: 安全门加密密钥（可选，默认随机生成）

## 发布门槛

候选必须通过以下检查才能发布：

- `static_compile`: 编译通过
- `security_scan`: AST 静态安全扫描
- `gate_contract`: 门禁契约完整
- `boundary_replay`: 边界用例回放通过
- `retention_replay`: 保留用例回放通过
- `confirmation_single_use`: 确认令牌一次性验证

## API 参考

### SafetyPolicyGate

主要安全策略门禁类：

```python
from safety_policy_gate import SafetyPolicyGate, validate_tool_call

# 使用默认门禁
decision = validate_tool_call(
    tool_name="delete_file",
    params={"path": "/tmp/file.txt"}
)

# 或自定义门禁
gate = SafetyPolicyGate(max_timeout=300.0)
decision = gate.validate_tool_call("delete_file", {"path": "/tmp/file.txt"})
```

### 风险分类

系统识别以下高风险操作：

- **文件删除**: `delete_file`, `remove_directory`, `rmdir`
- **Git 强制推送**: `git_push` with `force=true`
- **破坏性 SQL**: `DROP TABLE`, `TRUNCATE`, 无 WHERE 的 DELETE
- **危险 Shell 命令**: `rm -rf`, `mkfs`, `shutdown`, `dd if=`

## 故障排除

### 导入错误

如果遇到导入错误，确保从项目根目录运行：

```bash
cd ai-agant
source .venv/bin/activate
python chapter8/harness-safety-gate/demo.py
```

### LLM 连接失败

检查 `.env` 文件配置：

```bash
# 验证配置
cat .env | grep -E "API_KEY|LLM_"
```

### 验证失败

查看详细日志：

```bash
python run_experiment_8_8.py --quick
# 检查 output/ 目录下的 manifest 文件
```

## 技术要点

### 模型外验证

与实验 8-6 不同，本实验不需要 Docker 沙箱：

1. **AST 静态检查**：不执行源码，只扫描导入和调用
2. **隔离回放**：在内存模拟环境回放，无法触碰真实系统

### 证据回执

真实 LLM 路径的完整证据保存在 `validation/<run>/evidence.json`：

- 原始请求/响应
- Token 用量和成本
- 延迟统计
- 请求/响应 SHA256 哈希

### 安全保证

- 稳定代码不被修改
- 候选代码隔离在 `validation/<run>/candidates/` 目录
- 验证器属于可信根，不在自我修改权限内
- 所有可信根在验证前后做 SHA256 快照比对

## 与其他实验的对比

| 实验 | 修改层 | 失败信号来源 | 提案类型 | 需要沙箱 |
|------|--------|-------------|----------|---------|
| 8-5 | 控制层 | 系统内部错误 | 覆盖补丁 | 需要 |
| 8-8 | 安全/验证层 | 用户反馈与审计 | 新增模块 | 不需要 |
