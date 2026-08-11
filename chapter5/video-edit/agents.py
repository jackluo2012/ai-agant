"""
视频剪辑智能代理系统

本模块实现三个核心 Agent：

  VideoAnalyzerAgent —— 视频分析子 Agent，使用"两步 Vision 定位"查找目标场景边界。
  ProposerAgent      —— 将自然语言需求解析为剪辑计划，调用子 Agent 定位并执行剪辑。
  ReviewerAgent      —— 抽取成片关键帧，使用 Vision 检查剪辑是否正确，给出结构化反馈。

设计原理：将视频分析封装为独立子 Agent，大量截图只进入子 Agent 的一次性上下文，
不会污染主 Agent（Proposer/Reviewer）的对话历史——有效控制 token 消耗。
"""
import base64
import json
import os
import sys

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

from llm.client import get_llm_client
from ffmpeg_utils import extract_frame, probe_duration

# 获取 LLM 客户端
_llm_client = None


def _get_llm_client():
    """获取（并缓存）LLM 客户端"""
    global _llm_client
    if _llm_client is None:
        _llm_client = get_llm_client()
    return _llm_client


def _get_model_name():
    """获取配置的模型名称"""
    client = _get_llm_client()
    return client.model_name


def _temp_for(model):
    """推理模型（gpt-5 / o 系列等）不接受 temperature=0"""
    model_name = model or _get_model_name()
    return (1 if any(k in model_name.lower()
                     for k in ("gpt-5", "o1", "o3", "o4", "thinking", "reasoner", "kimi-k3"))
            else 0)


def _img_part(path: str) -> dict:
    """
    将图片路径转换为 Vision API 消息格式

    Args:
        path: 图片文件路径

    Returns:
        Vision API 消息格式的字典
    """
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return {"type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "low"}}


def _extract_json(text: str) -> dict:
    """
    从 LLM 回复中稳健地提取第一个 JSON 对象

    Args:
        text: LLM 返回的文本

    Returns:
        提取的 JSON 对象

    Raises:
        ValueError: 无法解析 JSON 时抛出异常
    """
    start = text.find("{")
    if start < 0:
        raise ValueError(f"未能从回复中解析 JSON：{text[:200]}")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text, start)
    except json.JSONDecodeError as e:
        raise ValueError(f"未能从回复中解析 JSON：{text[:200]}") from e
    if not isinstance(obj, dict):
        raise ValueError(f"未能从回复中解析 JSON：{text[:200]}")
    return obj


def _num(value, default: float) -> float:
    """
    将 LLM 返回的数值字段转换为 float

    字段缺失、为 null 或非法时回退到默认值

    Args:
        value: 要转换的值
        default: 默认值

    Returns:
        转换后的浮点数
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class TokenMeter:
    """
    Token 计数器

    累计 token 使用量，用于对比"子 Agent 隔离截图"带来的主上下文节省效果
    """

    def __init__(self):
        """初始化计数器"""
        self.prompt = 0
        self.completion = 0

    def add(self, resp):
        """
        累加一次 API 响应的 token 数量

        Args:
            resp: API 响应对象
        """
        u = getattr(resp, "usage", None)
        if u:
            self.prompt += u.prompt_tokens
            self.completion += u.completion_tokens

    def total(self):
        """返回总 token 数量"""
        return self.prompt + self.completion


# --------------------------------------------------------------------------- #
# 视频分析子 Agent：两步 Vision 定位
# --------------------------------------------------------------------------- #
class VideoAnalyzerAgent:
    """
    视频分析子 Agent

    使用两步 Vision 定位策略：
      1. 粗粒度定位：大间隔采样，快速找到大致场景范围
      2. 细粒度定位：在小范围内精细采样，精确定位边界
    """

    def __init__(self, meter: TokenMeter = None):
        """
        初始化视频分析 Agent

        Args:
            meter: Token 计数器（可选）
        """
        self.meter = meter or TokenMeter()

    def _vision_locate(self, video, timestamps, question, frame_dir):
        """
        抽取指定时间点的帧，连同问题交给 Vision LLM，返回 {start, end}

        Args:
            video: 视频文件路径
            timestamps: 时间戳列表
            question: 定位问题
            frame_dir: 帧输出目录

        Returns:
            (start, end, reason) 元组
        """
        content = [{
            "type": "text",
            "text": (
                f"下面是同一段视频在不同时间点的截图（每张图前标注了该帧的时间，单位秒）。\n"
                f"目标问题：{question}\n"
                f"请判断'目标场景'在视频中出现的时间区间。只依据画面内容判断。\n"
                f"严格输出 JSON：{{\"start\": <起点秒>, \"end\": <终点秒>, "
                f"\"reason\": \"<简要依据>\"}}。若所有截图都看不到目标场景，"
                f"令 start=end=-1。"
            ),
        }]
        for t in timestamps:
            png = os.path.join(frame_dir, f"f_{t:.1f}.png")
            extract_frame(video, t, png)
            content.append({"type": "text", "text": f"[时间 t={t:.1f}s]"})
            content.append(_img_part(png))

        client = _get_llm_client()
        model = _get_model_name()

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            temperature=_temp_for(model),
            max_tokens=300,
        )
        self.meter.add(resp)
        data = _extract_json(resp.choices[0].message.content)
        # 模型可能省略 start/end 或返回 null——按约定的 -1 哨兵处理，走兜底逻辑
        return _num(data.get("start"), -1.0), _num(data.get("end"), -1.0), data.get("reason", "")

    def locate(self, video, question, coarse_interval=10.0, fine_interval=1.0,
               frame_dir="output/frames"):
        """
        两步定位目标场景

        第一步（粗）：每 coarse_interval 秒一帧，Vision 给出大致场景区间
        第二步（细）：在粗区间上下各扩一个粗间隔，每 fine_interval 秒一帧，
                      Vision 精确定位边界

        Args:
            video: 视频文件路径
            question: 定位问题
            coarse_interval: 粗粒度采样间隔（秒）
            fine_interval: 细粒度采样间隔（秒）
            frame_dir: 帧输出目录

        Returns:
            (start, end, trace) 元组，trace 包含定位过程信息
        """
        os.makedirs(frame_dir, exist_ok=True)
        duration = probe_duration(video)
        trace = {}

        # ---- 第一步：粗粒度 ----
        coarse_ts = [t for t in _frange(0, duration, coarse_interval)]
        cs, ce, creason = self._vision_locate(video, coarse_ts, question, frame_dir)
        trace["coarse"] = {"timestamps": coarse_ts, "start": cs, "end": ce,
                           "reason": creason}

        if cs < 0 or ce < 0:
            # 兜底：粗定位失败——退化为全视频精扫（步长放大以控制成本）
            trace["coarse_fallback"] = True
            step = max(fine_interval, duration / 20.0)
            scan_ts = list(_frange(0, duration, step))
            cs, ce, creason = self._vision_locate(video, scan_ts, question, frame_dir)
            trace["coarse"]["fallback_scan"] = {"start": cs, "end": ce}
            if cs < 0:
                raise RuntimeError(
                    "Vision 定位失败：在整段视频里都没找到匹配'{}'的场景。\n"
                    "请检查需求描述是否与视频内容相符，或更换视频。".format(question)
                )

        # ---- 第二步：细粒度（在粗区间外扩一个粗间隔）----
        lo = max(0.0, cs - coarse_interval)
        hi = min(duration, ce + coarse_interval)
        fine_ts = list(_frange(lo, hi, fine_interval))
        fs, fe, freason = self._vision_locate(video, fine_ts, question, frame_dir)
        trace["fine"] = {"window": [lo, hi], "timestamps_count": len(fine_ts),
                         "start": fs, "end": fe, "reason": freason}

        if fs < 0 or fe < 0 or fe <= fs:
            # 兜底：细定位失败——采用粗定位结果，保证流程可继续
            trace["fine_fallback"] = True
            fs, fe = cs, ce

        # 收敛到视频范围内
        fs = max(0.0, fs)
        fe = min(duration, fe)
        return fs, fe, trace


def _frange(start, stop, step):
    """
    浮点数范围生成器（含首项，含接近末尾的采样点）

    Args:
        start: 起始值
        stop: 结束值
        step: 步长

    Returns:
        浮点数列表
    """
    out = []
    t = start
    while t < stop - 1e-6:
        out.append(round(t, 3))
        t += step
    # 补一个接近末尾的采样点，确保末段场景被覆盖
    last = round(max(start, stop - 0.5), 3)
    if not out or abs(out[-1] - last) > step / 2:
        out.append(last)
    return out


# --------------------------------------------------------------------------- #
# Proposer Agent（提议者 Agent）
# --------------------------------------------------------------------------- #
class ProposerAgent:
    """
    提议者 Agent

    负责解析用户的自然语言需求，生成结构化的剪辑计划，
    并根据 Reviewer 的反馈调整剪辑边界
    """

    def __init__(self, meter: TokenMeter = None):
        """
        初始化提议者 Agent

        Args:
            meter: Token 计数器（可选）
        """
        self.meter = meter or TokenMeter()

    def parse_request(self, nl_request: str) -> dict:
        """
        将自然语言需求解析为结构化意图

        输出格式：{"target_query": "...", "effects": [...]}

        Args:
            nl_request: 自然语言剪辑需求

        Returns:
            结构化的剪辑意图字典
        """
        client = _get_llm_client()
        model = _get_model_name()

        resp = client.chat.completions.create(
            model=model,
            temperature=_temp_for(model),
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": (
                    "你是视频剪辑规划器。把用户的中文剪辑需求解析成 JSON。\n"
                    "字段：\n"
                    "  target_query: 用于视觉定位的一句话描述（英文更利于匹配画面文字），"
                    "说明要剪出哪个场景；\n"
                    "  effects: 特效数组，元素形如 "
                    "{\"type\":\"subtitle\",\"text\":\"...\"} 或 "
                    "{\"type\":\"slowmo\",\"factor\":2.0}，无特效则为 []。\n"
                    f"用户需求：{nl_request}\n"
                    "只输出 JSON。"
                ),
            }],
        )
        self.meter.add(resp)
        return _extract_json(resp.choices[0].message.content)

    def revise_bounds(self, start, end, feedback, duration):
        """
        根据 Reviewer 的反馈微调剪辑边界（保守外扩/内收）

        Args:
            start: 当前起点（秒）
            end: 当前终点（秒）
            feedback: Reviewer 的反馈意见
            duration: 视频总时长（秒）

        Returns:
            (new_start, new_end) 调整后的边界
        """
        client = _get_llm_client()
        model = _get_model_name()

        resp = client.chat.completions.create(
            model=model,
            temperature=_temp_for(model),
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    f"当前剪辑区间 start={start:.1f}s end={end:.1f}s，视频总长 {duration:.1f}s。\n"
                    f"审核反馈：{feedback}\n"
                    "请给出修正后的区间，输出 JSON {\"start\":..,\"end\":..}。"
                    "若反馈指出包含了无关片段则内收，若指出遗漏内容则外扩，幅度 1~5 秒。"
                ),
            }],
        )
        self.meter.add(resp)
        d = _extract_json(resp.choices[0].message.content)
        # 模型可能省略 start/end 或返回 null——缺失时维持当前区间不变
        return max(0.0, _num(d.get("start"), start)), min(duration, _num(d.get("end"), end))


# --------------------------------------------------------------------------- #
# Reviewer Agent（审核者 Agent）
# --------------------------------------------------------------------------- #
class ReviewerAgent:
    """
    审核者 Agent

    抽取成片关键帧，使用 Vision 检查剪辑质量，
    给出是否通过、评分和反馈意见
    """

    def __init__(self, meter: TokenMeter = None):
        """
        初始化审核者 Agent

        Args:
            meter: Token 计数器（可选）
        """
        self.meter = meter or TokenMeter()

    def review(self, clip_path, target_query, frame_dir="output/review_frames"):
        """
        抽取成片的首/中/尾关键帧，使用 Vision 检查

        检查项目：
          - 是否完整包含目标场景（无遗漏）
          - 是否夹带了无关场景（无多余）

        Args:
            clip_path: 剪辑成片路径
            target_query: 目标场景描述
            frame_dir: 帧输出目录

        Returns:
            结构化审核结果 {pass, score, feedback, frames_checked}
        """
        os.makedirs(frame_dir, exist_ok=True)
        dur = probe_duration(clip_path)
        # 取首/中/尾，并在首尾稍微内缩避开黑帧
        keyts = [min(0.5, dur * 0.1), dur / 2.0, max(0.0, dur - 0.5)]

        content = [{
            "type": "text",
            "text": (
                f"这是剪辑成片的几个关键帧（首/中/尾）。剪辑目标是：{target_query}。\n"
                "请检查：(1) 成片是否完整呈现了目标场景；(2) 是否夹带了不该出现的其他场景。\n"
                "严格输出 JSON：{\"pass\": true/false, \"score\": 0-10, "
                "\"feedback\": \"<发现的问题或确认无误>\"}。"
            ),
        }]
        for t in keyts:
            png = os.path.join(frame_dir, f"r_{t:.1f}.png")
            extract_frame(clip_path, t, png)
            content.append({"type": "text", "text": f"[成片内 t={t:.1f}s]"})
            content.append(_img_part(png))

        client = _get_llm_client()
        model = _get_model_name()

        resp = client.chat.completions.create(
            model=model,
            temperature=_temp_for(model),
            max_tokens=300,
            messages=[{"role": "user", "content": content}],
        )
        self.meter.add(resp)
        data = _extract_json(resp.choices[0].message.content)
        data["frames_checked"] = keyts
        return data
