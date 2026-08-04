"""混合检索的结果融合模块。

本模块实现混合检索流水线的*融合*阶段——即将分别排序的稠密和稀疏候选列表
合并为单一、统一的候选池，然后在神经重排序之前使用。

提供两种生产级融合策略，对应书中讨论的两种方法（第3章「混合检索流水线」）：

1. 倒排秩融合（RRF）
   score(d) = Σ_r  1 / (k + rank_r(d))
   仅使用排名，原始分数被丢弃。鲁棒且无尺度依赖，因为永远不需要比较
   余弦相似度与 BM25 分数。

2. 加权分数融合（min-max 归一化）
   score(d) = Σ_r  w_r * normalize_r(score_r(d))
   保留原始相关性信号，代价是需要通过各列表的 min-max 归一化来对齐分数尺度。

两种函数都接受排序的 ``(doc_id, score)`` 元组列表（按分数降序排序），并返回
排序的 ``(doc_id, fused_score)`` 元组列表，同样按分数降序。只在一个列表中出现的
文档仍然会被融合——来自缺失列表的贡献为零。
"""

from typing import Dict, List, Optional, Sequence, Tuple

RankedList = Sequence[Tuple[str, float]]

# RRF 默认平滑常数。k=60 来自 Cormack 等人的原始论文，也是实践中最常见的
# 选择；它会压缩最顶级排名之间的分数差距。
DEFAULT_RRF_K = 60


def min_max_normalize(scores: Dict[str, float]) -> Dict[str, float]:
    """将 doc_id -> score 映射 min-max 归一化到 [0, 1] 范围。

    Args:
        scores: 从文档ID到原始分数的映射

    Returns:
        从文档ID到归一化分数的映射。如果所有分数相等（或只有一个文档），
        则所有文档获得 1.0 分数
    """
    if not scores:
        return {}

    values = list(scores.values())
    lo, hi = min(values), max(values)
    span = hi - lo

    if span <= 0:
        # 退化情况：所有分数相同 -> 视为同等相关
        return {doc_id: 1.0 for doc_id in scores}

    return {doc_id: (score - lo) / span for doc_id, score in scores.items()}


def reciprocal_rank_fusion(
    ranked_lists: Dict[str, RankedList],
    k: int = DEFAULT_RRF_K,
    weights: Optional[Dict[str, float]] = None,
) -> List[Tuple[str, float]]:
    """使用倒排秩融合（RRF）融合多个排序列表。

    Args:
        ranked_lists: 从源名称（如 "dense", "sparse"）到 ``(doc_id, score)``
            元组列表的映射，列表按分数降序排序。只有每列表的*顺序*重要，
            分数被忽略
        k: RRF 平滑常数（默认 60）
        weights: 可选的各源权重。默认每个源均为 1.0

    Returns:
        融合后的 ``(doc_id, fused_score)`` 元组列表，按分数降序排序
    """
    weights = weights or {}
    fused: Dict[str, float] = {}

    for source, ranked in ranked_lists.items():
        weight = weights.get(source, 1.0)
        for rank, (doc_id, _score) in enumerate(ranked, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + weight * (1.0 / (k + rank))

    return sorted(fused.items(), key=lambda kv: kv[1], reverse=True)


def weighted_score_fusion(
    ranked_lists: Dict[str, RankedList],
    weights: Optional[Dict[str, float]] = None,
) -> List[Tuple[str, float]]:
    """使用加权、min-max 归一化分数融合多个排序列表。

    每个源列表独立地 min-max 归一化到 [0, 1]，然后用加权和组合归一化分数。
文档在某个源中缺失时，该源的贡献为零。

    Args:
        ranked_lists: 从源名称到 ``(doc_id, score)`` 元组的映射
        weights: 可选的各源权重。默认每个源均为 1.0

    Returns:
        融合后的 ``(doc_id, fused_score)`` 元组列表，按分数降序排序
    """
    weights = weights or {}
    normalized_by_source = {
        source: min_max_normalize(dict(ranked))
        for source, ranked in ranked_lists.items()
    }

    fused: Dict[str, float] = {}
    for source, normalized in normalized_by_source.items():
        weight = weights.get(source, 1.0)
        for doc_id, norm_score in normalized.items():
            fused[doc_id] = fused.get(doc_id, 0.0) + weight * norm_score

    return sorted(fused.items(), key=lambda kv: kv[1], reverse=True)


def fuse(
    ranked_lists: Dict[str, RankedList],
    method: str = "rrf",
    k: int = DEFAULT_RRF_K,
    weights: Optional[Dict[str, float]] = None,
) -> List[Tuple[str, float]]:
    """分发辅助函数：使用指定方法融合排序列表。

    Args:
        ranked_lists: 从源名称到 ``(doc_id, score)`` 元组的映射
        method: "rrf" 表示倒排秩融合，"weighted" 表示加权 min-max
            归一化分数融合
        k: RRF 平滑常数（仅当 method="rrf" 时使用）
        weights: 可选的各源权重

    Returns:
        融合后的 ``(doc_id, fused_score)`` 元组列表，按分数降序排序

    Raises:
        ValueError: 如果 ``method`` 无法识别
    """
    if method == "rrf":
        return reciprocal_rank_fusion(ranked_lists, k=k, weights=weights)
    if method == "weighted":
        return weighted_score_fusion(ranked_lists, weights=weights)
    raise ValueError(f"未知的融合方法: {method!r}（应为 'rrf' 或 'weighted'）")
