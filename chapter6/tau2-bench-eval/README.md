# 实验 6-1：τ²-bench 电信领域评估

本目录保存了原稿要求的有界 τ²-bench 评估活动：五个电信任务，每个任务一次试验，使用同一模型同时扮演客服代理和用户模拟器。

## 代码结构说明

- **首先运行：** 按照下方固定的外部检出命令，以 num-trials 1 运行一个任务
- **起点：** τ²-bench CLI 是运行器；本目录是可复现性和证据包装器
- **核心行为：** 外部电信环境执行代理/用户轮次；本项目记录产生的轨迹
- **状态/协议：** 在 validation/runs/ 下保存原始轨迹、任务种子、模型 ID 和运行清单
- **验证器：** 任务奖励加上章节接受检查；检查失败任务记录，而不仅仅是 4/5 的汇总结果
- **实验变量：** 固定任务集、模型对、并发和种子
- **首次浏览时跳过：** 上游框架内部和成本报告格式

## 可复现性

外部检出刻意未作为供应商代码提供。首先克隆并固定权威源：

```bash
git clone https://github.com/sierra-research/tau2-bench.git chapter6/tau2-bench
git -C chapter6/tau2-bench checkout --detach 8d005b0e5b9e4af0bc055886fa7f95fc86d1710e
cd chapter6/tau2-bench
uv venv --python 3.12
uv pip install -e .
```

配置 `OPENROUTER_API_KEY` 后，保存的评估活动使用：

```bash
.venv/bin/tau2 run \
  --domain telecom \
  --agent-llm openrouter/openai/gpt-4.1-mini \
  --user-llm openrouter/openai/gpt-4.1-mini \
  --num-trials 1 \
  --num-tasks 5 \
  --max-concurrency 3 \
  --save-to exp6-1-openrouter-gpt41mini-telecom-5tasks-20260802-v1 \
  --log-level INFO
```

两个模型的温度均为 `0`；τ²-bench 记录的种子为 `300`。保留的原始轨迹位于
[`validation/runs/exp6-1-openrouter-gpt41mini-telecom-20260802-v1/`](validation/runs/exp6-1-openrouter-gpt41mini-telecom-20260802-v1/)。

## 结果

代理通过了 4/5 任务，平均奖励和 Pass@1 为 **0.80**。所有五个模拟均正常以 `user_stop` 结束；无提供商错误。保留的提供商报告成本总计约 **$0.151312**：代理成本 $0.112672，用户模拟器成本 $0.0386396。

失败的任务是
`[mobile_data_issue]data_saver_mode_on|data_usage_exceeded[PERSONA:Easy]`。
客户提供的电话号码是 `555-123-2002`，但代理选择了线路
`L1001`。后续的 `get_details_by_id(L1001)` 结果明确将该线路与电话 `555-123-2001` 关联；
尽管如此，代理继续使用其 3.2/5 GB 的使用读数。它正确地让用户禁用了数据节省模式，
但没有检查匹配的 `L1002` 线路或执行所需的 2 GB 数据充值。
它在 71 条消息轨迹的剩余时间里进行了不相关的诊断，并最终转交给人工。
因此，`refuel_data` 和所有三个下游环境断言失败。轨迹还暴露了一个早期的策略违规，
代理在一轮中发出了两个客户查询工具调用，而电信策略每次只允许一个。

这是一个有用的双重控制失败：用户侧的数据节省模式操作已发生并在共享环境中得到验证，
而代理侧的线路选择错误阻止了第二次状态变更和最终恢复。

## 验证边界

上游公共验证器报告：

- 格式验证：通过
- 试验计数验证：通过
- 任务验证：失败，因为公共排行榜提交必须覆盖完整的电信任务集

对于本书实验指定的五任务命令，该覆盖失败是预期的。因此此证据建立的是有界实验
6-1 活动，而非完整域的 τ²-bench 排行榜结果。参见
[`evidence.json`](validation/runs/exp6-1-openrouter-gpt41mini-telecom-20260802-v1/evidence.json)
了解机器可读结果，参见 [`manifest.json`](validation/runs/exp6-1-openrouter-gpt41mini-telecom-20260802-v1/manifest.json)
了解内容哈希。
