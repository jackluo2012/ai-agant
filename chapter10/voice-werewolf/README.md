# 实验 10-6：语音狼人杀 Agent 系统

1 名真人通过实时 ASR/TTS 语音与 6 个 AI Agent 玩一局狼人杀。配套《深入理解 AI Agent》第 10 章。

## 功能概述

本实验演示三个核心设计（对应书中「多 Agent 协作与编排」小节）：

- **多 Agent**：每个玩家 = 一个独立的 LLM Agent，拥有**严格隔离的私有上下文**。
  狼人只知道队友、预言家只知道查验结果、村民只能靠公开信息推理——信息不对称
  是狼人杀的灵魂，也是信息权限控制的天然教学场景。
- **信息权限控制**：法官（确定性编排器，不是 LLM）决定每条信息投递进哪些 Agent
  的私有上下文，并逐条登记审计。游戏结束后打印「信息可见性审计表」+ 自动校验，
  客观证明信息隔离正确（例如存在非狼人上下文含队友身份即校验失败）。
- **法官编排**：确定性法官驱动昼夜循环——夜晚（狼人刀人 → 预言家查验 → 女巫用药）
  → 白天（公布死讯 → 依次发言 → 投票放逐）→ 结算胜负。

四种运行模式：

| 模式 | 命令 | 说明 |
|------|------|------|
| 真人实时语音（验收路径） | `python demo.py --confirm-human-consent` | 1 名真人（麦克风 ASR + TTS 播报）+ 6 个 AI，默认 7 人局 |
| LLM 用户模拟器（自动端到端） | `python demo.py --simulate-user` | 独立 LLM 通过工具调用决策，文本必须经过真实 TTS 音频 → ASR 回环 |
| 全 AI 在线（补充诊断） | `python demo.py --ai-only` | 真实 LLM 全 AI 文本局，无音频 |
| 全 AI 离线（CI 补充） | `python demo.py --offline` | 规则策略代替 LLM，零成本、可复现、无需任何 API Key |

## 快速开始

### 1. 环境准备

本实验属于 `ai-agant` 工作区的一个章节项目，建议在项目根目录使用统一虚拟环境：

```bash
cd ai-agant
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r chapter10/voice-werewolf/requirements.txt
```

依赖说明：`openai`、`python-dotenv` 等核心依赖由项目根目录统一提供；实验特定依赖
仅 `sounddevice`（麦克风采集）、`numpy`（音频处理）、`pytest`（单元测试）。

纯文本/离线模式无需麦克风；真人语音模式需要可用麦克风，macOS 播放默认用 `afplay`。

### 3. 配置说明（项目根目录 .env）

所有 LLM 配置统一读取项目根目录 `ai-agant/.env`，本实验目录内**没有也不需要**
独立的 `.env`：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi        # 或 openai / deepseek / anthropic / aliyun / custom
LLM_MODEL=kimi-k3        # 可选；不填用提供商默认模型
BASE_URL=...             # 仅 aliyun / custom 提供商需要
```

`--simulate-user` / `--voice` 的语音接口（TTS/ASR）走统一客户端的音频端点，
要求所配提供商兼容 OpenAI 音频 API。

### 4. 运行

在项目根目录 `ai-agant/` 下运行：

```bash
# 全 AI 离线模式（零成本，先跑通流程）
python chapter10/voice-werewolf/demo.py --offline

# 真人实时语音验收路径（7 人局，必须显式确认知情同意）
python chapter10/voice-werewolf/demo.py --confirm-human-consent

# 自动端到端：LLM 用户模拟器 + 真实语音回环
python chapter10/voice-werewolf/demo.py --simulate-user

# 全 AI 在线诊断 + 可选语音合成
python chapter10/voice-werewolf/demo.py --ai-only --voice
```

## 使用方法

### 常用参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--seed` | 42 | 随机种子（决定身份分布与离线决策，可复现） |
| `--players` | 7 | 玩家总数 |
| `--wolves` | 自动 | 狼人数量（验收路径固定为 2） |
| `--human-seat` | P1 | 真人座位（角色仍由 seed 随机分配） |
| `--simulated-user-seat` | P1 | 用户模拟器座位 |
| `--simulator-model` | 统一模型 | 用户模拟器可独立指定模型 |
| `--simulator-speech-provider` | auto | `api`=托管 TTS+ASR；`local`=本机合成器（espeak/say）+ 多模态 ASR |
| `--max-rounds` | 8 | 昼夜循环回合上限 |
| `--model` | .env 配置 | 覆盖 LLM 模型 |
| `--voice` / `--play` | 关 | 合成 AI 发言语音 / 合成后立即播放 |
| `--log` | 关 | 完整对局日志另存一份 |
| `--no-interruptions` | 关 | 关闭真人实时打断（barge-in） |
| `--report` | `results/acceptance_report.json` | 验收报告输出路径 |
| `--confirm-human-consent` | 关 | 真人路径必填：确认参与者已授权麦克风采集 |

### 验收报告

每局结束自动产出验收报告（默认 `results/acceptance_report.json`），包含：

- 身份花名册与角色计数、完成的昼夜循环数、获胜阵营；
- 信息隔离校验结果（每条敏感信息进入了谁的上下文）；
- 完整行动历史（发言、投票、夜间行动及模型给出的决策理由）；
- 语音事件轨迹（TTS/ASR 延迟、音频哈希、打断事件）；
- 逐项验收门（gates）：花名册、用户座位唯一、真实 ASR/TTS、语音边界完整性、
  3 个完整循环、信息隔离、LLM 策略审计、规则内决出胜负。

对 `--simulate-user` 的报告可再跑独立复核（不发任何网络请求）：

```bash
python chapter10/voice-werewolf/validate_simulator_run.py results/acceptance_report.json
```

### 运行单元测试

```bash
python -m pytest chapter10/voice-werewolf/test_simultaneous_deaths_consensus.py \
    chapter10/voice-werewolf/test_witch_killed_no_poison.py \
    chapter10/voice-werewolf/test_user_simulator.py -v
```

## 项目结构

```
chapter10/voice-werewolf/
├── demo.py                        # 主入口：参数解析、模式分发、验收报告生成
├── werewolf/
│   ├── roles.py                   # 角色/阵营定义 + 各角色策略提示词
│   ├── agent.py                   # 玩家 Agent：私有上下文 + LLM/离线双策略
│   ├── game.py                    # 法官：确定性编排 + 信息权限控制中枢
│   ├── audit.py                   # 信息可见性审计表
│   ├── human.py                   # 真人座位 + 实时语音会话（VAD + barge-in）
│   ├── simulator.py               # LLM 用户模拟器 + 真实语音回环
│   ├── strategy_audit.py          # 赛后 LLM 策略验收（fail-closed）
│   └── tts.py                     # 可选的批量 TTS 合成
├── validate_simulator_run.py      # 独立复核器：音频/动作边界离线校验
├── test_*.py                      # 单元测试
├── results/                       # 验收报告输出目录
├── logs/                          # 对局日志目录
└── requirements.txt               # 实验特定依赖
```

## 配置说明

### 项目特定环境变量（可选，均有默认值）

```bash
# 语音接口（需所配提供商兼容 OpenAI 音频 API）
OPENAI_TTS_MODEL=tts-1            # TTS 模型
OPENAI_TTS_VOICE=coral            # TTS 音色
OPENAI_ASR_MODEL=whisper-1        # ASR 模型
VOICE_LANGUAGE=zh                 # ASR 识别语言
VOICE_SAMPLE_RATE=16000           # 麦克风采样率
VOICE_SILENCE_SECONDS=0.8         # 句末静音判定时长
VOICE_RMS_THRESHOLD=0.025         # 语音能量阈值（VAD）
VOICE_MAX_UTTERANCE_SECONDS=25    # 单次发言最长秒数
AUDIO_PLAYER=afplay               # 语音播放器（macOS）

# 模拟用户 local 语音回环
SIMULATOR_ASR_MODEL=...           # 多模态听写模型（local 回环必填）
SIMULATOR_ESPEAK_VOICE=cmn        # espeak 音色（cmn=普通话）
SIMULATOR_SAY_VOICE=Tingting      # macOS say 中文音色

# LLM 调用
WEREWOLF_LLM_TIMEOUT=45           # 单次请求超时（秒）
WEREWOLF_LLM_RETRIES=1            # 请求重试次数
```

## 故障排除

| 现象 | 原因与处理 |
|------|-----------|
| `API 密钥未设置` | 在**项目根目录** `ai-agant/.env` 配置 `API_KEY` 与 `LLM_PROVIDER`；或先用 `--offline` 离线模式 |
| 想零成本快速验证流程 | `python demo.py --offline`，不需要任何 Key |
| 真人模式拒绝启动 | 真人验收路径必须加 `--confirm-human-consent`（知情同意保护） |
| 语音合成/识别报错 | TTS/ASR 走统一客户端音频端点，确认所配提供商兼容 OpenAI 音频 API；纯文本模式去掉 `--voice` |
| `local` 语音回环启动失败 | 需要 `espeak-ng`（Linux）或 `say`（macOS）+ `ffmpeg`；并设置 `SIMULATOR_ASR_MODEL` 为支持音频输入的多模态模型 |
| 麦克风采集超时 | 检查麦克风权限与 `VOICE_RMS_THRESHOLD`；WSL 环境下需将 Windows 音频设备转发进 WSL |
| AI 发言为空报错 | 推理型模型可能把预算耗在隐藏推理上；代码已内置有界重试，若仍失败可换 `LLM_MODEL` |
| 打断（barge-in）误触发 | 扬声器回声被当成插话，建议戴耳机；或加 `--no-interruptions` 关闭 |

## 技术要点

1. **信息隔离的落点**：每个 `PlayerAgent` 只维护自己的 `memory` 列表；LLM 的每次
   调用只拼接本人上下文。法官的信息投递原语（`broadcast` / `private_send` /
   `wolves_send`）同时写审计日志，事后可机器校验「谁看到了什么」。
2. **语音边界的真实性**：`--simulate-user` 中 LLM 的文本必须经 TTS 合成为真实
   音频、再由 ASR 转写后才能进入游戏；工具选择与 ASR 解析结果不一致即硬失败
   （`simulator_action_mismatch`），保证 ASR 误识别是可观测的一环而非被绕过。
3. **fail-closed 验收**：策略审计对格式不合规的模型评分一律判失败并保留原始
   证据；回合上限打满时如实报告「本局未决」，不虚构胜负。
4. **统一 LLM 封装**：全部模型调用经 `llm.client.get_llm_client()`，密钥与端点
   统一来自项目根目录 `.env`；`_safe_create` 自动兼容推理型模型的参数差异
   （`max_completion_tokens`、禁用自定义 temperature）。
