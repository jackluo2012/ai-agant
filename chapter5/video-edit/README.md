# 智能视频剪辑系统

基于两步 Vision 定位 + 提议者-审核者架构的视频剪辑系统，演示 LLM Agent 在视频处理领域的应用。

## 功能概述

本系统实现了一个完整的智能视频剪辑流程：

- **两步 Vision 定位**：粗粒度快速定位 + 细粒度精确边界
- **自然语言解析**：将中文剪辑需求转换为结构化指令
- **双后端支持**：Blender Python API（bpy）或 ffmpeg 剪辑
- **质量审核**：自动检查剪辑结果并迭代优化
- **代码生成**：生成可执行的 Blender Python 脚本

### 核心组件

1. **VideoAnalyzerAgent（视频分析子 Agent）**
   - 使用 Vision 模型分析视频帧
   - 两步定位策略：粗粒度采样 → 细粒度精确定位
   - 大量截图只在子 Agent 上下文中，不污染主对话历史

2. **ProposerAgent（提议者 Agent）**
   - 解析自然语言剪辑需求
   - 生成结构化剪辑计划
   - 生成 Blender Python API 脚本
   - 根据反馈调整剪辑边界

3. **ReviewerAgent（审核者 Agent）**
   - 抽取成片关键帧进行视觉检查
   - 评估剪辑质量并给出反馈
   - 驱动迭代优化

## 快速开始

### 1. 环境准备

**系统依赖：**
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

**可选依赖（用于 Blender 后端）：**
```bash
# 从官网下载安装
# https://www.blender.org/download/
```

### 2. 配置

在**项目根目录**的 `.env` 文件中配置 LLM：

```bash
# 在 ai-agant/.env 中配置
API_KEY=your-api-key
LLM_PROVIDER=kimi  # 或 siliconflow, doubao, deepseek 等
LLM_MODEL=kimi-k3   # 可选
```

### 3. 运行

```bash
# 激活虚拟环境（从项目根目录）
cd ai-agant
source .venv/bin/activate

# 运行演示（默认需求：把冲浪的部分剪出来）
python chapter5/video-edit/demo.py

# 自定义需求
python chapter5/video-edit/demo.py "把滑雪部分剪出来，并加上字幕 Winter"

# 快速模式（减少 Vision API 调用）
python chapter5/video-edit/demo.py --quick

# 冒烟自检（不调用 LLM API）
python chapter5/video-edit/demo.py --smoke

# 使用外部视频
python chapter5/video-edit/demo.py -i my_video.mp4 -o output.mp4 "把精彩片段剪出来"
```

## 使用方法

### 命令行参数

| 参数 | 说明 |
|------|------|
| `request` | 中文剪辑需求（默认："把冲浪的部分剪出来"） |
| `--input`, `-i` | 输入视频路径（不指定则生成测试视频） |
| `--output`, `-o` | 成片输出路径（默认：output/final.mp4） |
| `--backend` | 剪辑后端：auto/blender/ffmpeg（默认：auto） |
| `--quick` | 快速模式：减少采样和审查轮数 |
| `--max-rounds` | 最多重剪轮数（默认：3） |
| `--smoke` | 冒烟自检：仅测试剪辑链路 |

### 剪辑需求示例

```
"把冲浪的部分剪出来"
"把滑雪部分剪出来，并加上字幕 Winter"
"把演讲开场剪出来，加上慢动作效果"
"提取骑车的片段，标注 CYCLING"
```

### 支持的特效

- **字幕**：`{"type": "subtitle", "text": "文本内容"}`
- **慢动作**：`{"type": "slowmo", "factor": 2.0}`

## 项目结构

```
chapter5/video-edit/
├── agents.py           # 核心代理实现
├── demo.py             # 主入口文件
├── video_editor.py     # 视频剪辑执行层
├── blender_editor.py   # Blender 后端
├── ffmpeg_utils.py     # FFmpeg 工具函数
├── make_test_video.py  # 测试视频生成器
├── results/            # 结果输出目录
└── logs/                # 日志目录
```

## 技术要点

### 1. 两步 Vision 定位

- **粗粒度**：每 10 秒采样一帧，快速锁定大致范围
- **细粒度**：在粗定位范围内每 1 秒采样一帧，精确定位边界

### 2. 子 Agent 隔离

视频分析大量截图只在子 Agent 的一次性上下文中，不会污染主 Agent 的对话历史，有效控制 token 消耗。

### 3. 代码生成

Proposer Agent 生成完整的 Blender Python API 脚本，体现了 LLM 的代码生成能力：
- 可人工核对和修改
- 可迁移到其他机器执行
- 与实际渲染解耦

### 4. 双后端设计

- **Blender 后端**：生成可复用的 bpy 脚本（书中原方案）
- **FFmpeg 后端**：快速、轻量、CI 友好

## 输出示例

### 冒烟自检模式（`--smoke`）

```text
==========================================================================
  冒烟自检 | 剪辑链路 + bpy 脚本生成，不调用任何 API
==========================================================================
[1/3] 生成测试视频 OK：output/source.mp4（场景真值={'hiking': (0, 15), 'surfing': (15, 30), 'skiing': (30, 42), 'cycling': (42, 54)}）
[2/3] 抽帧 OK：output/frames/smoke.png
[3/3] 剪辑+字幕 OK（后端=ffmpeg（未装 Blender，回退））：
  文件: smoke_cut.mp4
  时长: 5.03s
  容器: mov,mp4,m4a,3gp,3g2,mj2
  大小: 121.4 KB
  视频流: h264 1280x720 @ 30/1 fps
  音频流: aac 44100Hz 1ch

已生成 Proposer 的 Blender 脚本：output/edit.py
（这正是书中'生成 Blender Python API 代码'的产物；装好 Blender 后可直接
 `blender --background --python output/edit.py` 无头渲染。）

✓ 冒烟自检通过：剪辑链路正常 + bpy 脚本已生成（未调用 LLM API）。
```

### 快速模式（`--quick`）

```text
步骤 1 | Proposer 解析自然语言需求
解析结果：目标场景='surfing scene'  特效=[]

步骤 2 | 视频分析子 Agent：两步 Vision 定位（--quick 快速采样）
  [粗粒度] 每 15s 采样 5 帧 → Vision 得区间 [15, 30]s（依据：The word 'SURFING' appears at t=15s and changes at t=30s.）
  [细粒度] 窗口 [0.0, 45.0] 内每 2s 采样 23 帧 → 精确边界 [16.0, 28.0]s
  >>> 最终定位：起 16.0s  止 28.0s
  真值 [15, 30]s → 起点误差 1.0s，终点误差 2.0s（验收要求 ≤ 3s）

步骤 3-4 | Proposer 剪辑 + Reviewer 审查（迭代）
  Proposer 剪出片段 [16.0, 28.0]s，成片时长 12.0s
  Reviewer：pass=... score=... 检查帧=['0.5', '6.0', '11.5']

Token 统计（子 Agent 隔离截图，主上下文不被污染）
  主 Agent（Proposer+Reviewer）：573 tokens
  子 Agent（两步定位截图）    ：2934 tokens
```

## 故障排除

### 问题：找不到 ffmpeg

**解决方案：**
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

### 问题：LLM 配置检查失败

**解决方案：**

确保项目根目录的 `.env` 文件中已配置：
```bash
API_KEY=your-api-key
LLM_PROVIDER=kimi
LLM_MODEL=kimi-k3
```

### 问题：Vision 定位失败

**可能原因：**
- 视频内容与需求描述不匹配
- 场景不明显或时间过短
- 模型理解偏差

**解决方案：**
- 检查需求描述是否准确
- 尝试更明确的场景描述
- 使用 `--quick` 模式快速验证

### 问题：Blender 渲染失败

**解决方案：**
- 使用 `--backend ffmpeg` 切换到 FFmpeg 后端
- 或安装 Blender：`brew install blender`（macOS）

## 技术要点总结

1. **Vision API 应用**：使用视觉模型分析视频帧，理解场景内容
2. **Agent 协作**：提议者-审核者双 Agent 迭代优化
3. **上下文隔离**：子 Agent 独立处理大量图片，节省主对话 token
4. **代码生成**：生成可执行的 Blender 脚本，体现 LLM 编程能力
5. **双后端设计**：兼顾教学价值（bpy）和工程实用性（ffmpeg）

## 局限性

- 定位精度取决于场景在画面上的可辨识度
- 细粒度步长固定 1s，边界精度约 ±1s
- 慢动作音频使用 `atempo` 变速，倍率过大时音质下降
- Reviewer 仅抽首/中/尾三帧，长片段中段的偶发错误可能漏检
