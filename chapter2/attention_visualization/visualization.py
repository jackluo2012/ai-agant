"""
注意力可视化工具
创建 token 置信度和推理过程的热力图
"""

import warnings
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import numpy as np

from config import VIZ_COLORMAP, VIZ_FIGSIZE, VIZ_DPI, VIZ_OUTPUT_DIR

# 抑制 matplotlib 警告
warnings.filterwarnings('ignore')

# 配置后端
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 直接添加中文字体路径
try:
    # 尝试添加 Noto Sans CJK 字体
    font_path = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    if Path(font_path).exists():
        fm.fontManager.addfont(font_path)
        # 设置为默认字体
        plt.rcParams['font.family'] = ['Noto Sans CJK SC', 'sans-serif']
        plt.rcParams['axes.unicode_minus'] = False
        print(f"✅ 已加载中文字体: Noto Sans CJK SC")
    else:
        # 尝试其他可能的路径
        for alt_path in [
            '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
            '/usr/local/share/fonts/NotoSansCJK-Regular.ttc',
            '~/.local/share/fonts/NotoSansCJK-Regular.ttc',
        ]:
            p = Path(alt_path).expanduser()
            if p.exists():
                fm.fontManager.addfont(str(p))
                plt.rcParams['font.family'] = ['Noto Sans CJK SC', 'sans-serif']
                plt.rcParams['axes.unicode_minus'] = False
                print(f"✅ 已加载中文字体: {p}")
                break
        else:
            print("⚠️  未找到中文字体文件，中文可能显示为方块")
except Exception as e:
    print(f"⚠️  字体加载失败: {e}")


def create_token_confidence_heatmap(
    token_info: List[Dict],
    title: str = "Token Confidence Heatmap",
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = None,
    cmap: str = None,
) -> plt.Figure:
    """创建 token 置信度热力图"""
    figsize = figsize or VIZ_FIGSIZE
    cmap = cmap or VIZ_COLORMAP

    # 提取数据
    tokens = [t.get("token", f"t{i}") for i, t in enumerate(token_info)]
    logprobs = [t.get("logprob", 0.0) for t in token_info]

    if not tokens:
        print("⚠️  没有 token 数据")
        return None

    # 创建图表
    fig, ax = plt.subplots(figsize=figsize, dpi=VIZ_DPI)

    # 归一化用于颜色映射
    logprobs_array = np.array(logprobs).reshape(-1, 1)

    # 绘制热力图
    im = ax.imshow(logprobs_array, cmap=cmap, aspect='auto')

    # 添加颜色条
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('Log Probability', rotation=270, labelpad=20)

    # 设置轴标签
    ax.set_xticks([])
    ax.set_yticks(range(len(tokens)))
    ax.set_yticklabels(tokens)

    # 在格子上显示数值
    for i, (token, logprob) in enumerate(zip(tokens, logprobs)):
        text_color = 'white' if abs(logprob) > 1.5 else 'black'
        ax.text(
            0, i, f'{logprob:.2f}',
            ha="center", va="center",
            color=text_color,
            fontsize=8
        )

    # 设置标题和标签
    ax.set_title(title, fontsize=12, pad=15)
    ax.set_xlabel("Confidence", fontsize=11)

    # 添加统计信息
    if logprobs:
        stats_text = (
            f"Statistics:\n"
            f"Mean: {np.mean(logprobs):.3f}\n"
            f"Std: {np.std(logprobs):.3f}\n"
            f"Min: {np.min(logprobs):.3f}\n"
            f"Max: {np.max(logprobs):.3f}\n"
            f"Tokens: {len(tokens)}"
        )

        fig.text(
            0.98, 0.5, stats_text,
            fontsize=9,
            verticalalignment='center',
            horizontalalignment='left',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='wheat', alpha=0.3)
        )

    plt.tight_layout(rect=[0, 0, 0.92, 1])

    if save_path:
        fig.savefig(save_path, dpi=VIZ_DPI, bbox_inches='tight', facecolor='white')
        print(f"💾 热力图已保存: {save_path}")

    plt.close(fig)
    return fig


def create_token_probability_distribution(
    token_info: List[Dict],
    title: str = "Token Probability Distribution",
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (12, 8),
) -> plt.Figure:
    """创建 token 概率分布折线图"""
    tokens = [t.get("token", f"t{i}") for i, t in enumerate(token_info)]
    logprobs = [t.get("logprob", 0.0) for t in token_info]
    probs = [np.exp(lp) if lp < 20 else 0 for lp in logprobs]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, dpi=VIZ_DPI)

    x_pos = range(len(tokens))

    # 子图1: 概率
    ax1.plot(x_pos, probs, marker='o', linewidth=1.5, markersize=3, color='steelblue')
    ax1.fill_between(x_pos, probs, alpha=0.3, color='steelblue')
    ax1.set_ylabel('Probability', fontsize=11)
    ax1.set_title(title, fontsize=12)
    ax1.grid(True, alpha=0.3, linestyle='--')

    # 子图2: 对数概率
    ax2.plot(x_pos, logprobs, marker='s', linewidth=1.5, markersize=3,
             color='darkorange', label='Logprob')
    mean_lp = np.mean(logprobs)
    ax2.axhline(y=mean_lp, color='red', linestyle='--', linewidth=1.5,
                label=f'Mean: {mean_lp:.3f}')
    ax2.set_xlabel('Token Position', fontsize=11)
    ax2.set_ylabel('Log Probability', fontsize=11)
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3, linestyle='--')

    # X 轴标签
    step = max(1, len(tokens) // 15)
    tick_positions = list(range(0, len(tokens), step))
    if len(tokens) - 1 not in tick_positions:
        tick_positions.append(len(tokens) - 1)

    for ax in [ax1, ax2]:
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(
            [tokens[i][:8] if i < len(tokens) else str(i) for i in tick_positions],
            rotation=45, ha='right', fontsize=8
        )

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=VIZ_DPI, bbox_inches='tight', facecolor='white')
        print(f"💾 概率分布图已保存: {save_path}")

    plt.close(fig)
    return fig


def create_top_alternatives_heatmap(
    token_info: List[Dict],
    title: str = "Top-K Candidate Tokens",
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = None,
    max_alternatives: int = 5,
) -> plt.Figure:
    """创建 top-k 候选 token 热力图"""
    # 提取候选 token
    all_alternatives = []
    position_labels = []

    for i, t in enumerate(token_info):
        top_logprobs = t.get("top_logprobs", [])
        position_label = f"{i}: {t.get('token', '?')[:6]}"
        position_labels.append(position_label)

        row = {}
        for alt_dict in top_logprobs[:max_alternatives]:
            for token, logprob in alt_dict.items():
                token_short = token[:8]
                row[token_short] = logprob

        if t.get("token"):
            selected_token = t.get("token")[:8]
            row[f"✓{selected_token}"] = t.get("logprob", 0.0)

        if row:
            all_alternatives.append(row)

    if not all_alternatives:
        print("⚠️  No top_logprobs data")
        return None

    # 收集所有候选 token
    all_tokens_set = set()
    for row in all_alternatives:
        all_tokens_set.update(row.keys())

    token_list = sorted(list(all_tokens_set))[:max_alternatives * 2]

    # 构建矩阵
    matrix = np.full((len(all_alternatives), len(token_list)), -10.0)

    for i, row in enumerate(all_alternatives):
        for j, token in enumerate(token_list):
            if token in row:
                matrix[i, j] = row[token]

    # 创建图表
    figsize = figsize or (max(len(token_list) * 2, 12), max(len(all_alternatives) * 0.4, 6))
    fig, ax = plt.subplots(figsize=figsize, dpi=VIZ_DPI)

    im = ax.imshow(matrix, cmap='RdYlGn', aspect='auto',
                   vmin=-6, vmax=0)

    # 颜色条
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('Log Probability', rotation=270, labelpad=20)

    # 标签
    ax.set_xticks(range(len(token_list)))
    ax.set_xticklabels(token_list, rotation=45, ha='right', fontsize=9)
    ax.set_yticks(range(len(position_labels)))
    ax.set_yticklabels(position_labels, fontsize=8)

    ax.set_title(title, fontsize=12, pad=15)
    ax.set_xlabel('Candidate Tokens', fontsize=11)
    ax.set_ylabel('Position (Selected)', fontsize=11)

    # 数值标注
    for i in range(len(all_alternatives)):
        for j in range(len(token_list)):
            val = matrix[i, j]
            if val > -9:
                text_color = 'white' if val < -2 else 'black'
                ax.text(j, i, f'{val:.1f}',
                       ha="center", va="center",
                       fontsize=7, color=text_color)

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=VIZ_DPI, bbox_inches='tight', facecolor='white')
        print(f"💾 Top-K 热力图已保存: {save_path}")

    plt.close(fig)
    return fig


def visualize_generation_result(
    result: Dict[str, Any],
    output_dir: Path = None,
    prefix: str = "viz"
):
    """从生成结果创建所有可视化图表"""
    output_dir = output_dir or VIZ_OUTPUT_DIR
    output_dir.mkdir(exist_ok=True)

    timestamp = result.get("timestamp", "unknown")
    category = result.get("category", "default")

    token_info = result.get("result", {}).get("token_info", [])

    if not token_info:
        print(f"⚠️  没有 token 信息，跳过可视化")
        return

    # 1. 置信度热力图
    try:
        create_token_confidence_heatmap(
            token_info,
            title=f"Token Confidence - {category}",
            save_path=output_dir / f"{prefix}_confidence_{category}.png"
        )
    except Exception as e:
        print(f"⚠️  置信度热力图生成失败: {e}")

    # 2. 概率分布图
    try:
        create_token_probability_distribution(
            token_info,
            title=f"Token Probability Distribution - {category}",
            save_path=output_dir / f"{prefix}_distribution_{category}.png"
        )
    except Exception as e:
        print(f"⚠️  概率分布图生成失败: {e}")

    # 3. Top-K 候选热力图
    has_top_logprobs = any(t.get("top_logprobs") for t in token_info)
    if has_top_logprobs:
        try:
            create_top_alternatives_heatmap(
                token_info,
                title=f"Top-K Candidate Tokens - {category}",
                save_path=output_dir / f"{prefix}_topk_{category}.png"
            )
        except Exception as e:
            print(f"⚠️  Top-K 热力图生成失败: {e}")

    print(f"✅ 可视化完成，输出目录: {output_dir}")


def batch_visualize_results(
    results_dir: Path = None,
    output_dir: Path = None
):
    """批量可视化结果目录中的所有 JSON 文件"""
    results_dir = results_dir or Path("results")
    output_dir = output_dir or VIZ_OUTPUT_DIR

    results_dir = Path(results_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    json_files = list(results_dir.glob("generation_*.json"))

    if not json_files:
        print(f"⚠️  在 {results_dir} 中没有找到结果文件")
        return

    print(f"📁 找到 {len(json_files)} 个结果文件")

    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            print(f"\n📊 处理: {json_file.name}")
            visualize_generation_result(data, output_dir)

        except Exception as e:
            print(f"❌ 处理 {json_file} 失败: {e}")

    print(f"\n✅ 批量可视化完成！")


if __name__ == "__main__":
    print("🎨 注意力可视化工具")
    print("=" * 60)

    # 检查是否有结果文件
    results_path = Path("results")
    if results_path.exists():
        batch_visualize_results()
    else:
        print("⚠️  请先运行 agent.py 生成一些结果")
