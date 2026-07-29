"""
注意力可视化 CLI 工具
======================

命令行工具，用于快速生成 token 置信度和推理过程可视化图表。

由于 llama.cpp 的 OpenAI 兼容 API 不直接返回注意力权重，
本工具展示以下替代分析：
  - Token 级别的对数概率（反映模型置信度）
  - Top-K 候选 token 分析
  - 概率分布曲线

使用示例:
    # 使用默认提示词
    python attention_cli.py

    # 自定义提示词
    python attention_cli.py --prompt "北京今天的天气怎么样？"

    # 指定输出文件
    python attention_cli.py -p "什么是机器学习？" -o ml_viz.png

    # 调整生成参数
    python attention_cli.py -p "写一首诗" --max-tokens 200 --temperature 0.9
"""

import argparse
import sys
from pathlib import Path

from agent import AttentionVisualizationAgent, GenerationResult
from visualization import (
    create_token_confidence_heatmap,
    create_token_probability_distribution,
    create_top_alternatives_heatmap,
    VIZ_OUTPUT_DIR
)
from config import (
    LLAMA_HOST, LLAMA_PORT, LLAMA_MODEL,
    DEFAULT_MAX_NEW_TOKENS, DEFAULT_TEMPERATURE
)


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog="attention_cli.py",
        description="使用 llama.cpp 生成文本并创建置信度可视化图表",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python attention_cli.py
  python attention_cli.py -p "北京今天的天气怎么样？"
  python attention_cli.py -p "解释什么是 AI" --max-tokens 200
  python attention_cli.py -p "写一首关于春天的诗" --temperature 0.9 -o spring.png
        """
    )

    # 输入/输出参数
    io_group = parser.add_argument_group("输入/输出")
    io_group.add_argument(
        "-p", "--prompt",
        default="北京今天的天气怎么样？",
        help="要可视化的提示文本"
    )
    io_group.add_argument(
        "-o", "--output",
        default=None,
        help="输出文件路径（默认自动生成）"
    )
    io_group.add_argument(
        "--output-dir",
        default=str(VIZ_OUTPUT_DIR),
        help=f"输出目录（默认: {VIZ_OUTPUT_DIR}）"
    )

    # 模型参数
    model_group = parser.add_argument_group("模型配置")
    model_group.add_argument(
        "--host",
        default=LLAMA_HOST,
        help=f"llama.cpp 服务器地址（默认: {LLAMA_HOST}）"
    )
    model_group.add_argument(
        "--port",
        type=int,
        default=LLAMA_PORT,
        help=f"llama.cpp 服务器端口（默认: {LLAMA_PORT}）"
    )
    model_group.add_argument(
        "--model",
        default=LLAMA_MODEL,
        help=f"模型名称（默认: {LLAMA_MODEL}）"
    )

    # 生成参数
    gen_group = parser.add_argument_group("生成参数")
    gen_group.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_NEW_TOKENS,
        help=f"最大生成 token 数（默认: {DEFAULT_MAX_NEW_TOKENS}）"
    )
    gen_group.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help=f"采样温度（默认: {DEFAULT_TEMPERATURE}）"
    )
    gen_group.add_argument(
        "--top-logprobs",
        type=int,
        default=5,
        help="记录前 N 个候选 token 的概率（默认: 5）"
    )

    # 可视化参数
    viz_group = parser.add_argument_group("可视化选项")
    viz_group.add_argument(
        "--type",
        choices=["confidence", "distribution", "topk", "all"],
        default="all",
        help="可视化类型（默认: all）"
    )
    viz_group.add_argument(
        "--cmap",
        default="viridis",
        help="matplotlib 色图名称（默认: viridis）"
    )
    viz_group.add_argument(
        "--figsize",
        default="14,10",
        help="图表大小，格式: 宽,高（默认: 14,10）"
    )
    viz_group.add_argument(
        "--no-display",
        action="store_true",
        help="不显示图表，只保存"
    )

    # 其他
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示详细输出"
    )

    return parser


def main():
    """主函数"""
    parser = build_parser()
    args = parser.parse_args()

    print("=" * 60)
    print("🎨 注意力可视化 CLI 工具")
    print("=" * 60)

    # 显示配置
    print(f"\n📋 配置:")
    print(f"  服务器: {args.host}:{args.port}")
    print(f"  模型: {args.model}")
    print(f"  提示: {args.prompt[:50]}...")
    print(f"  最大 token: {args.max_tokens}")
    print(f"  温度: {args.temperature}")

    # 初始化 Agent
    print(f"\n🔌 连接到 llama.cpp 服务器...")
    agent = AttentionVisualizationAgent(
        host=args.host,
        port=args.port,
        model=args.model,
        verbose=args.verbose
    )

    # 生成文本
    print(f"\n🤖 生成中...")
    try:
        result = agent.generate_with_logprobs(
            prompt=args.prompt,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            top_logprobs=args.top_logprobs,
            save_result=False
        )

        print(f"\n✅ 生成完成！")
        print(f"  Token 数量: {len(result.output_tokens)}")
        print(f"  Finish reason: {result.finish_reason}")

        print(f"\n📄 生成内容:")
        print("─" * 60)
        print(result.output_text)
        print("─" * 60)

    except Exception as e:
        print(f"\n❌ 生成失败: {e}")
        sys.exit(1)

    # 准备输出目录
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    # 准备输出文件名
    if args.output:
        output_base = Path(args.output).stem
        output_ext = Path(args.output).suffix
    else:
        output_base = "attention_viz"
        output_ext = ".png"

    # 转换 token_info 为字典格式
    token_info = [t.to_dict() for t in result.token_info]

    # 生成可视化
    print(f"\n🎨 生成可视化...")

    figsize = tuple(map(int, args.figsize.split(",")))

    saved_files = []

    if args.type in ["confidence", "all"]:
        path = output_dir / f"{output_base}_confidence{output_ext}"
        create_token_confidence_heatmap(
            token_info,
            title=f"Token 置信度 - {args.prompt[:30]}",
            save_path=str(path),
            figsize=figsize,
            cmap=args.cmap
        )
        saved_files.append(path)

    if args.type in ["distribution", "all"]:
        path = output_dir / f"{output_base}_distribution{output_ext}"
        create_token_probability_distribution(
            token_info,
            title=f"Token 概率分布 - {args.prompt[:30]}",
            save_path=str(path)
        )
        saved_files.append(path)

    if args.type in ["topk", "all"]:
        has_top_logprobs = any(
            t.get("top_logprobs") for t in token_info
        )
        if has_top_logprobs:
            path = output_dir / f"{output_base}_topk{output_ext}"
            create_top_alternatives_heatmap(
                token_info,
                title=f"Top-K 候选 - {args.prompt[:30]}",
                save_path=str(path),
                figsize=(max(args.top_logprobs * 3, 12), max(len(token_info) * 0.5, 8))
            )
            saved_files.append(path)
        else:
            print("⚠️  没有 top_logprobs 数据，跳过 Top-K 可视化")

    # 总结
    print("\n" + "=" * 60)
    print("✨ 完成！")
    print(f"\n💾 已保存文件:")
    for f in saved_files:
        print(f"  - {f}")

    # 显示统计信息
    if result.token_info:
        logprobs = [t.logprob for t in result.token_info]
        print(f"\n📊 统计信息:")
        print(f"  平均 logprob: {sum(logprobs)/len(logprobs):.4f}")
        print(f"  最小 logprob: {min(logprobs):.4f}")
        print(f"  最大 logprob: {max(logprobs):.4f}")

    print("=" * 60)

    # 显示图表（如果没有 --no-display）
    if not args.no_display:
        try:
            import matplotlib.pyplot as plt
            print("\n📺 显示图表（关闭窗口后退出）...")
            plt.show()
        except Exception as e:
            print(f"⚠️  无法显示图表: {e}")


if __name__ == "__main__":
    main()
