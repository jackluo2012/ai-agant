# 论文讲解视频自动生成

基于论文内容自动生成带讲解配音的视频。将论文要点渲染为幻灯片，调用大模型生成口语化讲解词，通过 TTS 合成语音，最后用 ffmpeg 逐页同步合成视频。

## 功能概述

- **幻灯片渲染**：使用 PIL 将论文要点渲染为 1280×720 的 PNG 幻灯片
- **讲解词生成**：调用大模型为每页生成口语化、引导性的讲解文字
- **语音合成**：使用 TTS 将讲解词合成为音频文件
- **视频合成**：使用 ffmpeg 将幻灯片与音频逐页同步合成为视频
- **自包含流程**：端到端完整流水线，无需依赖其他项目

## 快速开始

### 1. 环境准备

确保系统已安装以下依赖：

**命令行工具：**
- `ffmpeg` / `ffprobe`（视频处理核心工具）
  - macOS: `brew install ffmpeg`
  - Ubuntu: `sudo apt install ffmpeg`

**Python 环境：**
- Python 3.8+
- 项目虚拟环境（位于项目根目录 `.venv/`）

### 2. 安装依赖

从项目根目录激活虚拟环境并安装依赖：

```bash
cd /home/jackluo/my/ai-agent/ai-agant
source .venv/bin/activate
pip install -r chapter5/paper-to-video/requirements.txt
```

### 3. 配置 LLM

在项目根目录的 `.env` 文件中配置 LLM 服务：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=openai  # 或 kimi, deepseek, siliconflow 等
LLM_MODEL=gpt-4o     # 可选，默认使用提供商推荐模型
```

**支持的 LLM 提供商：**
- Kimi（`kimi`）
- OpenAI（`openai`）
- DeepSeek（`deepseek`）
- 阿里云（`aliyun`）
- 其他兼容 OpenAI API 的服务

### 4. 运行

```bash
# 从项目根目录运行
python3 chapter5/paper-to-video/demo.py

# 或进入项目目录运行
cd chapter5/paper-to-video
python3 demo.py
```

## 使用方法

### 基本用法

```bash
# 生成完整视频（5 页，约 2-3 分钟）
python3 demo.py

# 快速测试（只处理第 1 页）
python3 demo.py --quick

# 限制页数（只处理前 2 页）
python3 demo.py --limit 2

# 离线验证（无需 API，验证 ffmpeg 流水线）
python3 demo.py --offline

# 环境自检（不调用 API）
python3 demo.py --check
```

### 高级选项

| 参数 | 说明 |
|------|------|
| `--slides FILE` | 外部幻灯片 JSON 文件，替换内置示例 |
| `--script FILE` | 现成讲解词 JSON（字符串列表），跳过 LLM 生成 |
| `-o, --output FILE` | 最终视频输出路径（默认 `output/lecture.mp4`） |
| `--tts-provider {openai,offline}` | TTS 供应商 |
| `--offline` | 完全离线模式（占位静音音轨 + 占位讲解词） |
| `--text-model NAME` | 讲解词生成模型 |
| `--tts-model NAME` | TTS 模型 |
| `--tts-voice NAME` | TTS 音色（默认 `alloy`） |
| `--limit N` | 只处理前 N 页 |
| `--quick` | 快速测试（等价于 `--limit 1`） |
| `--check` | 环境自检 |

### 自定义幻灯片

创建 JSON 文件（`my_slides.json`）：

```json
[
  {
    "title": "论文标题",
    "subtitle": "副标题",
    "bullets": ["要点1", "要点2", "要点3"]
  },
  {
    "title": "第二页标题",
    "subtitle": "第二页副标题",
    "bullets": ["要点1", "要点2"]
  }
]
```

使用自定义幻灯片：

```bash
python3 demo.py --slides my_slides.json
```

### 自定义讲解词

创建 JSON 文件（`my_script.json`）：

```json
[
  "第一页的讲解词内容...",
  "第二页的讲解词内容..."
]
```

使用自定义讲解词：

```bash
python3 demo.py --script my_script.json
```

## 项目结构

```
chapter5/paper-to-video/
├── demo.py              # 主程序
├── requirements.txt     # 项目特定依赖
├── test_*.py           # 测试文件
├── output/              # 输出目录
│   ├── slides/         # 幻灯片 PNG
│   ├── audio/          # 讲解音频 MP3
│   ├── segments/       # 分段视频 MP4
│   ├── narration.json  # 讲解词清单
│   └── lecture.mp4     # 最终视频
├── results/            # 额外结果目录
└── logs/               # 日志目录
```

## 输出说明

运行完成后，`output/` 目录包含：

- `slides/slide_*.png` - 每页幻灯片图片
- `audio/audio_*.mp3` - 每页讲解音频
- `segments/seg_*.mp4` - 每页分段视频
- `narration.json` - 讲解词与音频时长清单
- `lecture.mp4` - 最终拼接的视频

查看视频元信息：

```bash
ffprobe -v error -show_format -show_streams output/lecture.mp4
```

## 内置示例

项目内置了《Attention Is All You Need》（Transformer）的 5 页幻灯片示例：

1. 论文概述
2. 研究背景与动机
3. 核心方法：自注意力
4. 实验结果
5. 总结与影响

## 配置说明

### LLM 配置（项目根目录 .env）

确保项目根目录的 `.env` 文件中已配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
```

### 项目特定配置

可通过命令行参数或环境变量配置：

```bash
# 讲解词模型
TEXT_MODEL=gpt-4o

# TTS 模型与音色
TTS_MODEL=tts-1
TTS_VOICE=alloy
```

## 故障排除

### 问题：找不到 ffmpeg

**错误信息：** `ffmpeg: 未找到`

**解决方法：**
- macOS: `brew install ffmpeg`
- Ubuntu: `sudo apt install ffmpeg`

### 问题：中文字体显示异常

**原因：** 系统缺少中文字体

**解决方法：** 修改 `demo.py` 中的 `FONT_CANDIDATES` 列表，添加系统中文字体路径

### 问题：LLM 客户端初始化失败

**错误信息：** `[错误] 初始化 LLM 客户端失败`

**解决方法：**
1. 检查项目根目录 `.env` 文件是否存在
2. 确认 `.env` 中已配置 `API_KEY` 和 `LLM_PROVIDER`
3. 确认 API Key 有效

### 问题：导入 llm.client 失败

**错误信息：** `[错误] 无法导入 llm.client 模块`

**解决方法：**
1. 确保从项目根目录运行脚本
2. 或将项目根目录添加到 PYTHONPATH：
   ```bash
   export PYTHONPATH=$PYTHONPATH:/home/jackluo/my/ai-agent/ai-agant
   ```

## 技术要点

### 流水线设计

```
论文要点（内置或外部）
       │ PIL 渲染
       ▼
每页 PNG 幻灯片 → LLM 生成讲解词 → TTS 合成音频
       │                                  │
       └────────── ffmpeg 逐页合成 ───────┘
                    │
                    ▼
            ffmpeg concat 拼接
                    │
                    ▼
            output/lecture.mp4
```

### 时长对齐

每页视频时长精确等于该页音频时长，确保幻灯片展示与语音讲解同步。

### 离线模式

`--offline` 参数无需任何 API 调用：
- 讲解词使用要点占位文本
- 音频使用 ffmpeg 生成的静音占位
- 用于验证 ffmpeg 流水线正确性

## 开发者信息

- **所属章节：** Chapter 5 - 高级 Agent 应用
- **实验编号：** 5-5
- **依赖项目：** 无（自包含）
