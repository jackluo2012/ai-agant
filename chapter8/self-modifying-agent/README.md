# 实验 8-5：由失败轨迹触发的可验证 Agent 自我修改流水线

本项目演示实验 8-5 的 Agent 自我修改机制：当生产轨迹显示同一个 `retryable=false` 错误仍被连续调用时，系统应修改 Agent 的重试与熔断控制代码，而不是只在 Prompt 中追加一句"不要重复调用"。

## 功能概述

- **失败诊断**：从多条失败轨迹中识别重复的非可重试故障模式
- **候选生成**：支持确定性生成器和真实 LLM 编码代理两种模式
- **沙箱验证**：在 Docker 容器中隔离执行候选代码，验证行为正确性
- **发布门控**：通过多重检查后才允许候选进入灰度阶段
- **可审计性**：完整的证据链记录，包括请求/响应哈希、代码 diff 等

## 快速开始

### 1. 环境准备

确保已安装 Python 3.12+ 和 Docker：

```bash
python3 --version
docker --version
```

### 2. 安装依赖

在项目根目录（ai-agant/）激活虚拟环境并安装依赖：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
```

### 3. 配置 LLM

在项目根目录的 `.env` 文件中配置 LLM 服务：

```bash
# LLM 配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 openai, deepseek, aliyun 等
LLM_MODEL=kimi-k3  # 可选，默认使用提供商默认模型
```

### 4. 运行实验

#### 使用确定性生成器（无需 LLM）

```bash
python3 chapter8/self-modifying-agent/demo.py
```

#### 使用真实 LLM 编码代理

```bash
python3 chapter8/self-modifying-agent/run_experiment_8_5.py \
  --provider kimi \
  --model kimi-k3 \
  --seed 8501
```

## 使用方法

### 运行单元测试

```bash
python3 -m pytest -q chapter8/self-modifying-agent/test_evolution.py
```

### 运行完整实验

运行完整实验包括三个候选：
1. **确定性候选**：用于可复现对照
2. **真实 LLM 候选**：由 LLM 编码代理生成
3. **负对照候选**：已知的错误补丁（用于验证门控有效性）

```bash
python3 chapter8/self-modifying-agent/run_experiment_8_5.py \
  --provider kimi \
  --model kimi-k3 \
  --seed 8501 \
  --output-dir chapter8/self-modifying-agent/validation/my_run
```

### 查看结果

实验完成后，查看输出目录：

```bash
# 查看发布清单
cat chapter8/self-modifying-agent/output/release_manifest.json

# 查看完整证据
cat chapter8/self-modifying-agent/validation/latest.json
```

## 项目结构

```
chapter8/self-modifying-agent/
├── stable/                    # 稳定版本代码（只读）
│   └── retry_policy.py        # 重试和熔断策略
├── evolution.py              # 诊断、生成和验证逻辑
├── llm_generator.py          # LLM 编码代理封装
├── candidate_sandbox.py      # Docker 沙箱管理
├── sandbox_runner.py         # 容器入口点
├── demo.py                   # 单提案教学入口
├── run_experiment_8_5.py     # 完整实验入口
├── failure_trajectories.json  # 输入：失败轨迹数据
├── output/                   # 输出：候选代码和清单
├── validation/               # 输出：证据和验证结果
└── results/                  # 用户自定义结果目录
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

### 沙箱配置（可选）

```bash
# 使用预构建的沙箱镜像
export SELF_MODIFY_SANDBOX_IMAGE=my-registry/self-modifying-sandbox:v1.0
```

### 命令行参数

- `--provider`: LLM 提供商（ark, openrouter, openai）
- `--model`: 模型名称
- `--seed`: 随机种子（默认 8501）
- `--output-dir`: 输出目录（默认 validation/<timestamp>）

## 安全机制

待验证代码在 Docker 容器中执行，容器具有以下安全限制：

- **网络隔离**：`--network none`
- **只读根文件系统**：`--read-only`
- **非 root 用户**：`--user 65534:65534`
- **资源限制**：
  - 内存：64MB
  - CPU：0.5 核心
  - 进程数：16
  - 文件描述符：64
  - 墙钟时间：8 秒

超时、OOM、Docker 不可用或协议输出异常都会导致验证失败。

## 发布门控

候选代码必须通过以下检查才能进入灰度：

1. **静态编译检查**：代码可编译为 Python 字节码
2. **安全扫描**：AST 检查拒绝危险调用
3. **沙箱执行**：在容器中成功执行
4. **公共 API 兼容**：函数签名未改变
5. **失败重放**：原失败轨迹不再重复
6. **非可重试熔断**：永久错误首次即熔断
7. **临时恢复**：临时错误仍可恢复
8. **旧任务回归**：不破坏原有行为
9. **灰度就绪**：满足灰度发布条件
10. **回滚就绪**：回滚版本哈希正确

## 故障排除

### Docker 相关错误

```bash
# 检查 Docker 是否运行
docker info

# 手动构建沙箱镜像
docker build -f chapter8/self-modifying-agent/Dockerfile.sandbox \
  -t self-modifying-sandbox chapter8/self-modifying-agent/
```

### LLM 调用失败

检查 `.env` 配置是否正确：

```bash
# 测试 LLM 连接
python3 -c "from llm.client import get_llm_client; print(get_llm_client().model_name)"
```

### 权限错误

确保虚拟环境已激活且在项目根目录运行：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
```

## 技术要点

### 可审计的自我修改

- **不可变输入**：稳定代码和失败轨迹的 SHA-256 哈希在生成前后保持一致
- **隔离执行**：候选代码仅在一次性容器中执行，永不覆盖稳定版本
- **证据链**：完整记录请求/响应、哈希、时间戳等元数据
- **零信任**：LLM 生成的代码必须通过模型外验证门控

### 影响预测

LLM 编码代理需要在生成代码前预测：
- 非可重试调用的数量变化
- 临时错误恢复率的变化
- 潜在的回退风险

### 回滚保证

- 回滚版本的哈希固定为稳定版本的哈希
- 灰度发布仅影响影子流量
- 任何非可重试重复或恢复回归都会触发回滚

## 实验结果参考

使用 Kimi kimi-k3 模型的规范运行：

- **输入 Token**：~839
- **输出 Token**：~392
- **总 Token**：~1,231
- **成本**：约 0.015 美元

验证结果：
- 确定性候选：`release_to_canary`
- 真实 LLM 候选：`release_to_canary`
- 负对照候选：`reject_candidate`

行为指标：
- 非可重试调用均值：3.5 → 1.0
- 临时错误恢复率：1.0 → 1.0
- 旧任务回归数：0
