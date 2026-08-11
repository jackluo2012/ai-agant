"""
智能视频剪辑演示程序

基于两步 Vision 定位 + 提议者-审核者架构的视频剪辑系统。

一条命令跑通：
  python demo.py                 # 默认需求"把冲浪的部分剪出来"
  python demo.py "把滑雪部分剪出来，并加上字幕 Winter"   # 自定义需求

流程：
  1. 程序化生成含 4 个明显不同场景的测试视频（HIKING/SURFING/SKIING/CYCLING）
  2. Proposer 解析自然语言需求 → 目标场景 + 特效
  3. 视频分析子 Agent 两步定位（粗粒度每 10s → 细粒度每 1s）找到精确边界
  4. Proposer 生成 Blender Python API（bpy）脚本剪出片段（可含字幕/慢动作）
     装了 Blender 则无头渲染，否则回退 ffmpeg——但 bpy 脚本始终生成（代码生成产物）
  5. Reviewer 检查成片关键帧，给出反馈；不合格则 Proposer 修正边界重剪，迭代

依赖：
  - ffmpeg/ffprobe（回退后端 + 抽帧）
  - LLM 配置（项目根目录 .env 文件）
  - 可选 Blender（书中原方案，`--backend blender`）

常用命令（完整用法见 `python demo.py --help`）：
  python demo.py                 # 默认需求，完整流程
  python demo.py --quick         # 快速模式：粗采样 + 单轮审查，省时省钱
  python demo.py --smoke         # 冒烟自检：仅剪辑链路 + 生成 bpy 脚本，不调用任何 API
"""
import argparse
import os
import shutil
import sys

# 添加项目根目录到路径
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 添加当前目录到路径
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "output")
SOURCE_VIDEO = os.path.join(OUT_DIR, "source.mp4")   # 测试片输出位置
FINAL_VIDEO = os.path.join(OUT_DIR, "final.mp4")
MAX_ROUNDS = 3  # Reviewer 反馈后最多重剪次数（默认，可用 --max-rounds 覆盖）

DEFAULT_REQUEST = "把冲浪的部分剪出来"


def banner(title):
    """打印分隔线标题"""
    print("\n" + "=" * 74)
    print(f"  {title}")
    print("=" * 74)


def build_arg_parser() -> argparse.ArgumentParser:
    """
    构建命令行参数解析器

    位置参数为中文剪辑需求，另有输入/输出/后端/快速等开关
    """
    p = argparse.ArgumentParser(
        prog="demo.py",
        description="智能视频剪辑：两步 Vision 定位 + 提议者-审核者",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python demo.py\n"
            "  python demo.py \"把滑雪部分剪出来，并加上字幕 Winter\"\n"
            "  python demo.py -i my.mp4 -o out.mp4 \"把演讲开场剪出来\"\n"
            "  python demo.py --backend blender    # 强制用 Blender Python API 渲染\n"
            "  python demo.py --quick    # 更少 Vision 调用，快速验证链路\n"
            "  python demo.py --smoke    # 只跑剪辑链路 + 生成 bpy 脚本，不调用任何 API\n"
        ),
    )
    p.add_argument("request", nargs="?", default=DEFAULT_REQUEST,
                   help="中文剪辑需求（默认：%(default)s）")
    p.add_argument("--input", "-i", metavar="VIDEO", default=None,
                   help="输入视频路径（不指定则程序化生成 4 场景测试片）")
    p.add_argument("--output", "-o", metavar="VIDEO", default=FINAL_VIDEO,
                   help="成片输出路径（默认 output/final.mp4）")
    p.add_argument("--backend", choices=["auto", "blender", "ffmpeg"], default="auto",
                   help="剪辑后端：auto=装了 Blender 用 bpy 否则 ffmpeg；"
                        "blender=强制 Blender Python API；ffmpeg=强制 ffmpeg（默认 auto）")
    p.add_argument("--quick", action="store_true",
                   help="快速模式：粗采样（15s/2s）+ 单轮审查，减少 Vision API 调用")
    p.add_argument("--max-rounds", type=int, default=MAX_ROUNDS, metavar="N",
                   help="Reviewer 反馈后最多重剪轮数（默认 %(default)s；--quick 时强制为 1）")
    p.add_argument("--smoke", action="store_true",
                   help="冒烟自检：仅剪辑链路 + 生成 bpy 脚本，不调用任何 API")
    return p


def smoke_check():
    """
    冒烟自检：不调用 LLM API，验证剪辑链路可用并生成 Proposer 的 bpy 脚本
    """
    from blender_editor import blender_available
    from ffmpeg_utils import ensure_ffmpeg, extract_frame, format_probe
    from make_test_video import GROUND_TRUTH, make as make_test_video
    from video_editor import apply_edit

    banner("冒烟自检 | 剪辑链路 + bpy 脚本生成，不调用任何 API")
    try:
        ensure_ffmpeg()
    except RuntimeError as e:
        print(f"\n[错误] {e}")
        sys.exit(1)
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)

    make_test_video(SOURCE_VIDEO)
    print(f"[1/3] 生成测试视频 OK：{SOURCE_VIDEO}（场景真值={GROUND_TRUTH}）")
    frame_dir = os.path.join(OUT_DIR, "frames")
    os.makedirs(frame_dir, exist_ok=True)   # extract_frame 要求目录已存在
    frame = extract_frame(SOURCE_VIDEO, 20.0, os.path.join(frame_dir, "smoke.png"))
    print(f"[2/3] 抽帧 OK：{frame}")
    clip = os.path.join(OUT_DIR, "smoke_cut.mp4")
    script_path = os.path.join(OUT_DIR, "edit.py")
    # backend="auto"：未装 Blender 则用 ffmpeg 实际渲染，但仍生成 bpy 脚本（代码生成产物）
    apply_edit(SOURCE_VIDEO, {"start": 15.0, "end": 20.0,
                              "effects": [{"type": "subtitle", "text": "SMOKE"}]},
               clip, backend="auto", script_path=script_path)
    used = "Blender bpy" if blender_available() else "ffmpeg（未装 Blender，回退）"
    print(f"[3/3] 剪辑+字幕 OK（后端={used}）：\n{format_probe(clip)}")
    print(f"\n已生成 Proposer 的 Blender 脚本：{script_path}")
    print("（这正是书中'生成 Blender Python API 代码'的产物；装好 Blender 后可直接")
    print(f" `blender --background --python {script_path}` 无头渲染。）")
    print("\n✓ 冒烟自检通过：剪辑链路正常 + bpy 脚本已生成（未调用 LLM API）。")


def preflight():
    """
    启动自检：检查必需的依赖是否可用，给出清晰的错误提示
    """
    from ffmpeg_utils import ensure_ffmpeg

    # 检查 LLM 配置
    from llm.client import get_llm_client
    try:
        client = get_llm_client()
        # 验证客户端可用性
        _ = client.model_name
    except Exception as e:
        print("\n[错误] LLM 配置检查失败。\n"
              "  请确保项目根目录的 .env 文件中已配置有效的 LLM 提供商。\n"
              f"  错误详情：{e}")
        sys.exit(1)

    try:
        ensure_ffmpeg()
    except RuntimeError as e:
        print(f"\n[错误] {e}")
        sys.exit(1)


def main():
    """主函数"""
    args = build_arg_parser().parse_args()
    if args.smoke:                       # 仅剪辑链路，不需要 LLM，提前返回
        smoke_check()
        return

    nl_request = args.request
    # --quick：粗化采样步长并只审查一轮，把 Vision 调用降到最少（用于快速验证链路）
    coarse_interval = 15.0 if args.quick else 10.0
    fine_interval = 2.0 if args.quick else 1.0
    max_rounds = 1 if args.quick else max(1, args.max_rounds)

    preflight()

    # 延迟导入：确保 preflight 的报错优先于任何 SDK 初始化
    from agents import (ProposerAgent, ReviewerAgent, VideoAnalyzerAgent,
                        TokenMeter)
    from llm.client import get_llm_client
    from blender_editor import blender_available
    from ffmpeg_utils import format_probe, probe_duration
    from make_test_video import make as make_test_video, GROUND_TRUTH
    from video_editor import apply_edit

    # 获取模型名称用于显示
    llm_client = get_llm_client()
    model_name = llm_client.model_name

    # 幂等：每次从干净的 output/ 开始
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)

    ground_truth = None
    if args.input:
        banner("步骤 0 | 使用外部输入视频")
        source_video = os.path.abspath(args.input)
        if not os.path.isfile(source_video):
            print(f"\n[错误] 输入视频不存在：{source_video}")
            sys.exit(1)
        print(f"输入视频：{source_video}")
    else:
        banner("步骤 0 | 生成测试视频（4 个明显不同的场景）")
        source_video = SOURCE_VIDEO
        make_test_video(source_video)
        ground_truth = GROUND_TRUTH
        print(f"已生成 {source_video}")
        print(f"场景真值（用于核对定位误差）：{ground_truth}")
    total_dur = probe_duration(source_video)
    print(f"时长 {total_dur:.1f}s")
    print(f"模型={model_name}  剪辑后端={args.backend}")

    # 分离的 token 计量：主 Agent（Proposer+Reviewer）vs 子 Agent（截图定位）
    main_meter = TokenMeter()
    sub_meter = TokenMeter()
    proposer = ProposerAgent(main_meter)
    reviewer = ReviewerAgent(main_meter)
    analyzer = VideoAnalyzerAgent(sub_meter)

    banner("步骤 1 | Proposer 解析自然语言需求")
    print(f"用户需求：{nl_request}")
    intent = proposer.parse_request(nl_request)
    # 模型可能省略 target_query 或返回 null——退化为用原始需求文本做视觉定位
    target_query = intent.get("target_query") or nl_request
    effects = intent.get("effects", [])
    print(f"解析结果：目标场景='{target_query}'  特效={effects}")

    banner("步骤 2 | 视频分析子 Agent：两步 Vision 定位"
           + ("（--quick 快速采样）" if args.quick else ""))
    start, end, trace = analyzer.locate(
        source_video, target_query,
        coarse_interval=coarse_interval, fine_interval=fine_interval,
        frame_dir=os.path.join(OUT_DIR, "frames"),
    )
    c = trace["coarse"]
    print(f"  [粗粒度] 每 {coarse_interval:.0f}s 采样 {len(c['timestamps'])} 帧 → Vision 得区间 "
          f"[{c['start']:.0f}, {c['end']:.0f}]s（依据：{c['reason']}）")
    f = trace["fine"]
    print(f"  [细粒度] 窗口 {f['window']} 内每 {fine_interval:.0f}s 采样 {f['timestamps_count']} 帧 → "
          f"精确边界 [{f['start']:.1f}, {f['end']:.1f}]s（依据：{f['reason']}）")
    print(f"  >>> 最终定位：起 {start:.1f}s  止 {end:.1f}s")

    # 与真值对比，打印定位误差（验收：误差 ≤ ±3s）。仅测试片有真值
    key = _match_ground_truth(target_query, ground_truth) if ground_truth else None
    if key:
        gs, ge = ground_truth[key]
        print(f"  真值 [{gs}, {ge}]s → 起点误差 {abs(start - gs):.1f}s，"
              f"终点误差 {abs(end - ge):.1f}s（验收要求 ≤ 3s）")

    banner("步骤 3-4 | Proposer 生成 bpy 脚本剪辑 + Reviewer 审查（迭代）")
    plan = {"start": start, "end": end, "effects": effects}
    final_path = None
    for rnd in range(1, max_rounds + 1):
        print(f"\n--- 第 {rnd} 轮 ---")
        clip = os.path.join(OUT_DIR, f"cut_round{rnd}.mp4")
        script_path = os.path.join(OUT_DIR, f"edit_round{rnd}.py")
        apply_edit(source_video, plan, clip, backend=args.backend,
                   script_path=script_path)
        cdur = probe_duration(clip)
        used = "Blender bpy" if (args.backend == "blender" or
                                 (args.backend == "auto" and blender_available())) else "ffmpeg"
        print(f"  Proposer 生成 Blender 脚本 → {script_path}")
        print(f"  剪出片段 [{plan['start']:.1f}, {plan['end']:.1f}]s（后端={used}），"
              f"成片时长 {cdur:.1f}s")

        review = reviewer.review(clip, target_query,
                                 frame_dir=os.path.join(OUT_DIR, "review_frames"))
        print(f"  Reviewer：pass={review.get('pass')} score={review.get('score')} "
              f"检查帧={['%.1f' % t for t in review.get('frames_checked', [])]}")
        print(f"  Reviewer 反馈：{review.get('feedback', '（无）')}")

        if review.get("pass"):
            final_path = clip
            print("  ✓ 审核通过。")
            break
        if rnd == max_rounds:
            final_path = clip
            print("  达到最大轮数，采用当前成片。")
            break
        # 未通过：Proposer 据反馈修正边界后重剪
        ns, ne = proposer.revise_bounds(plan["start"], plan["end"],
                                        review.get("feedback", ""), total_dur)
        print(f"  Proposer 据反馈修正边界：[{ns:.1f}, {ne:.1f}]s")
        plan["start"], plan["end"] = ns, ne

    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    shutil.copy(final_path, output_path)

    banner("步骤 5 | 成片信息（ffprobe）")
    print(format_probe(output_path))

    banner("Token 统计（子 Agent 隔离截图，主上下文不被污染）")
    print(f"  主 Agent（Proposer+Reviewer）：{main_meter.total()} tokens "
          f"(prompt={main_meter.prompt}, completion={main_meter.completion})")
    print(f"  子 Agent（两步定位截图）    ：{sub_meter.total()} tokens "
          f"(prompt={sub_meter.prompt}, completion={sub_meter.completion})")
    print(f"\n完成：{output_path}")


def _match_ground_truth(query, gt):
    """
    将查询匹配到场景真值

    Args:
        query: 目标查询
        gt: 场景真值字典

    Returns:
        匹配的场景键，未匹配返回 None
    """
    q = query.lower()
    for key in gt:
        if key in q:
            return key
    # 中文关键词兜底映射
    zh = {"冲浪": "surfing", "徒步": "hiking", "滑雪": "skiing", "骑": "cycling",
          "hik": "hiking", "surf": "surfing", "ski": "skiing", "cycl": "cycling"}
    for k, v in zh.items():
        if k in q:
            return v
    return None


if __name__ == "__main__":
    main()
