# 实验 10-3：自主电话/浏览器编排（Autonomous Phone Registration）

本项目实现实验 10-3 的**自主模式**：一个真实的 Playwright Computer Use Agent 打开任意注册页面并读取渲染后的表单；真实 LLM 在 `tool_choice=auto` 下观察页面与已知上下文，**自主决定**是否调用 `initiate_phone_call_agent(purpose, required_info)` 工具——代码中没有任何"字段数大于 N 就启动"的 Python 规则，决策边界完全交给模型。

固定拓扑的对照实验见同章实验 10-2（`book-translation`）。

## 功能概述

- **自主决策**：LLM 看到真实页面观察、上下文字段与一个可选工具，由模型决定是否派生 Phone Agent，并给出决策摘要与 provider 凭据留痕。
- **默认本机 WebRTC 通话**：不需要手机号、PSTN 服务商、公开 webhook 或隧道。页面内完成真实 offer/answer 协商，Agent 语音与参与者音频走双向 RTP 音轨。
- **问一填一并发**：Phone Agent 每拿到一个有效值立即发给 Computer Agent，随后直接问下一项，不等待网页填写完成；`timing_evidence.overlap_checks` 用时间戳证明每个相邻字段对的问填重叠。
- **格式校验与重问**：HTML 类型、pattern、选项与格式提示都会变成 `FieldSpec` 校验器；无效回答触发 `format_invalid`、精确反馈并最多重问三次。
- **错误回流与安全提交**：页面/选择器错误以 `fill_error` 回流给电话侧并播报给用户；有任何错误残留时阻止提交。`--submit` 必须显式授权，演示不会意外创建账号。
- **隐私保护**：语音个人值在控制台与磁盘轨迹中一律脱敏为 `<redacted>`；WebRTC 对端录音临时交给 ASR 后即丢弃，原始音频与转录文本均不保留。

## 快速开始

### 1. 环境准备

- Python 3.10+
- 项目根目录 `ai-agant/` 下已配置好统一 LLM（见下方配置说明）
- Chromium：`playwright install chromium`
- 真人麦克风/扬声器模式还需可用的音频输入输出设备

### 2. 安装依赖

在项目根目录 `ai-agant/` 的虚拟环境中执行：

```bash
source .venv/bin/activate
pip install -r chapter10/autonomous-phone-registration/requirements.txt
playwright install chromium
```

### 3. 配置说明

#### 文本 LLM（项目根目录 .env）

自主决策与字段值抽取统一使用项目根目录 `ai-agant/.env` 的配置：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi        # 或 openai / deepseek / custom 等
LLM_MODEL=kimi-k3        # 可选
BASE_URL=                # 仅 aliyun / custom 提供商需要
```

#### 音频专用配置（可选）

TTS/ASR 是音频接口，模型名独立于文本模型。可参考本目录 `env.example` 配置：

```bash
OPENAI_TTS_MODEL=tts-1          # 统一客户端音频接口的 TTS 模型
OPENAI_ASR_MODEL=whisper-1      # 统一客户端音频接口的 ASR 模型
WEBRTC_SPEECH_PROVIDER=auto     # auto / openai / gemini-system / local-whisper
```

`WEBRTC_SPEECH_PROVIDER=auto` 优先选择本机 `say`/`espeak` TTS + Gemini ASR（若配置了 `GEMINI_API_KEY` 且系统有 ffmpeg），否则回退到统一客户端的音频接口。`local-whisper` 让 ASR 完全离线，需要 `openai-whisper`：

```bash
WEBRTC_SPEECH_PROVIDER=local-whisper
WHISPER_PYTHON=/path/to/python-with-whisper
WHISPER_MODEL=tiny
```

### 4. 运行方法

从项目根目录 `ai-agant/` 运行：

```bash
# 默认：本机浏览器 WebRTC 真人通话
python3 chapter10/autonomous-phone-registration/demo.py \
  --confirm-consent --url 'https://your-site.example/register'

# 无界面模式（只填不提交，避免副作用）
python3 chapter10/autonomous-phone-registration/demo.py \
  --confirm-consent --headless --url 'https://your-site.example/register'

# 允许真实提交（显式授权）
python3 chapter10/autonomous-phone-registration/demo.py \
  --confirm-consent --submit --url 'https://your-site.example/register'
```

命令会同时打开目标表单和一个本地参与者通话页。每听到一个问题后作答，点击**开始回答**发言、点击**结束回答**提交。localhost 是浏览器安全上下文，无需证书即可使用麦克风。

## 使用方法

### 命令行参数（demo.py）

| 参数 | 说明 |
|------|------|
| `--url` | 目标注册/资料表单 URL（默认 demoqa 练习表单） |
| `--known-json` | 上下文中已有字段的 JSON（键为表单 name/id） |
| `--headless` | 无界面运行真实 Chromium |
| `--submit` | 明确允许最终点击提交；默认只填不提交 |
| `--phone-transport` | `webrtc`（默认）/ `local`（本机麦克风）/ `twilio`（可选旧 PSTN 路径） |
| `--confirm-consent` | 确认参与者已授权实验电话/麦克风采集；所有真人语音路径必须传入 |
| `--trace` | 脱敏消息时序输出路径 |
| `--decision-trace` | Agent 决策记录输出路径 |
| `--raw-decision-request` / `--raw-decision-response` | 写入不含凭据的原始编排请求/响应与延迟（必须成对使用） |
| `--acceptance-report` | 机器可读验收门禁输出路径 |
| `--webrtc-headless` | 无界面运行 WebRTC 参与者（仅安全自动验收） |
| `--webrtc-port` | WebRTC 本地通话页端口；0 表示自动选择 |
| `--webrtc-answers-json` | 安全自动验收：字段名到回答（或回答数组）的映射；回答先合成语音、走真实 RTP 音轨、再由 ASR 转录，不直接注入 |
| `--scripted-json` | 仅自动化补充验证：字段名到回答的 JSON；省略则用真实麦克风 ASR/TTS |

### 测试与完整验收

```bash
cd chapter10/autonomous-phone-registration

# 单元测试（无需真实 LLM / 音频设备）
pytest -q

# 完整安全验收：真实 LLM + Playwright + WebRTC/RTP + TTS/ASR + localhost 提交。
# 值为安全的合成数据，但它们确实经过音频媒体路径与 ASR。
python run_acceptance.py

# 校验历史留痕证据（跳过源码哈希：历史证据绑定原书仓库时期的源码）
python validate_acceptance.py validation/runs/exp10-3-webrtc-raw-20260731-v4 --skip-source-hashes
```

`run_acceptance.py` 的表单与提交端点仅监听 localhost；一个故意无效的邮箱用于证明校验反馈与重问。运行结束后会生成包含 manifest 的留痕目录（源码、输入与产物全部以 SHA-256 绑定），并自动做一次 fail-closed 校验。

### 关于 `validation/` 目录

`validation/runs/exp10-3-webrtc-raw-20260731-v4/` 是**原书仓库时期**的正式验收留痕：真实 LLM（Volcengine ARK）自主选出六个必填字段，一通 offer/answer、七次媒体录音、9 次 TTS 与 7 次本机 Whisper ASR；双向 RTP 均有实际收发；一个故意无效的口语邮箱触发 `format_invalid` 与第二次提问；五个相邻问填区间全部重叠；恰好一次脱敏后的六字段提交到达 localhost 端点；9/9 验收门禁通过。它保留不含凭据的原始请求/响应（字面量 `tool_choice: "auto"`、工具参数、响应 ID、模型、usage 与实测延迟），独立校验器可重算全部哈希并把原始工具参数规范化后与 `decision.json` 精确比对。

注意：该历史证据的 `source_sha256` 绑定原书仓库的源码，与本工作区迁移后的源码天然不同，因此参考校验需带 `--skip-source-hashes`（或运行 `pytest` 时校验器会自动跳过该部分）。迁移后新运行的哈希由新 manifest 自行绑定。

## 项目结构

```
chapter10/autonomous-phone-registration/
├── README.md                        # 本文档
├── requirements.txt                 # 实验特定依赖（openai/dotenv 由根目录统一提供）
├── env.example                      # 音频/传输层环境变量示例
├── demo.py                          # 主入口：解析参数、驱动决策与验收门禁
├── decision.py                      # LLM 自主决策点（tool_choice=auto）
├── orchestration.py                 # Phone/Computer 双 Agent 与工具分发器
├── browser.py                       # 真实 Playwright 表单操作面
├── bus.py                           # 点对点异步消息总线（脱敏时序轨迹）
├── models.py                        # 共享数据契约（FieldSpec/AgentMessage/DecisionRecord）
├── voice.py                         # 本机麦克风级联语音通道 + 脚本化测试通道
├── webrtc_channel.py                # 本机 WebRTC 传输层与语音后端
├── twilio_channel.py                # 可选旧 PSTN 传输层
├── run_acceptance.py                # 完整安全验收运行器
├── validate_acceptance.py           # fail-closed 留痕证据校验器
├── test_*.py                        # 测试套件
├── validation/                      # 历史留痕证据（只读参考，来自原书仓库）
├── results/                         # 结果输出目录
└── logs/                            # 日志目录
```

## 故障排除

| 问题 | 处理方法 |
|------|----------|
| `API 密钥未设置` / `提供商需要 BASE_URL` | 检查项目根目录 `ai-agant/.env` 的 `API_KEY`、`LLM_PROVIDER`、`BASE_URL` 配置；本目录不单独配置文本 LLM |
| `无法导入统一 LLM 客户端 llm.client` | 必须从项目根目录 `ai-agant/` 运行（或设置 `PYTHONPATH` 指向根目录），确保 `llm/` 目录存在 |
| 真人模式直接退出并提示 `--confirm-consent` | 所有真人语音路径都要求显式传入 `--confirm-consent`，这是隐私门禁，属于预期行为 |
| 麦克风录不到声音 | 检查系统麦克风权限；WSL/macOS 下确认 `AUDIO_PLAYER` 与采集设备可用；必要时调整 `VOICE_RMS_THRESHOLD`/`VOICE_SILENCE_SECONDS` |
| TTS 报错 `audio` 接口不可用 | 所配置端点不支持音频接口；改用 `WEBRTC_SPEECH_PROVIDER=gemini-system` 或 `local-whisper` |
| Playwright 启动失败 | 在虚拟环境中执行 `playwright install chromium` |
| 历史证据校验失败（source_sha256） | 历史证据绑定原书源码，属预期；加 `--skip-source-hashes` 做参考校验 |
| 模型不调用 Phone Agent 工具 | 属正常自主决策（页面字段少或上下文已齐全时模型会拒绝调用）；可换信息更复杂的表单验证 |

## 技术要点

- **并发与失败语义**：Phone 与 Computer Agent 是两个独立的 `asyncio` 任务、各自独立循环。任一方异常都会取消对方、关闭通话与全部音轨，顶层 `finally` 再关闭浏览器；正常/异常退出路径上的清理都是幂等的。Computer Agent 的空闲上限（600s）大于电话侧单问题最坏延迟（TTS + 收听窗口 + 抽取），避免在用户正常作答时误杀通话。
- **隐私边界**：消息负载通过 `sensitive_keys` 标记敏感键，控制台打印与磁盘轨迹统一脱敏为 `<redacted>`；浏览器错误消息不含表单值与 Playwright 原始文本；WebRTC 对端录音只保留在内存中，转录后立即清空唯一引用；留痕产物全部通过凭据/取值正则扫描。
- **可复核性**：每次正式运行都会生成 manifest，把源码、输入与产物以 SHA-256 绑定，并记录 git HEAD；独立校验器重算全部哈希、独立规范化原始工具参数并要求与 `decision.json` 精确一致，篡改任何一处都会被拒绝。
- **安全默认值**：不传 `--submit` 就绝不点击提交；不传 `--confirm-consent` 就在任何浏览器/音频资源创建之前直接拒绝；WebRTC 全程无需手机号与 PSTN。
- **合成参与者 ≠ 真人研究**：安全合成参与者用于自动化与可复现验收，证明的是媒体、ASR、编排、校验、隐私与提交链路；它不是真人可用性研究，也不是 TURN/NAT 穿透测试。省略 `--webrtc-answers-json` 即进入同一媒体路径的真人麦克风模式。
