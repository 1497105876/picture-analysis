"""混合检索融合：RRF（纯函数）。"""

from __future__ import annotations

RRF_K = 60


def rrf_merge(
    ranked_lists: list[list[int]],
    weights: list[float] | None = None,
    k: int = RRF_K,
) -> list[tuple[int, float]]:
    """多路结果按 RRF 融合，返回 (id, score) 按分数降序。"""
    if weights is None:
        weights = [1.0] * len(ranked_lists)
    scores: dict[int, float] = {}
    for rank_list, weight in zip(ranked_lists, weights, strict=True):
        for rank, item_id in enumerate(rank_list, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


def expand_query(query: str, synonyms: dict[str, list[str]]) -> list[str]:
    """同义词展开：命中组内任一词则并入同组词（去重保序）。"""
    terms = [term for term in query.replace(",", " ").split() if term]
    seen = list(dict.fromkeys(terms))
    for term in list(seen):
        for group in synonyms.values():
            if term in group:
                for member in group:
                    if member not in seen:
                        seen.append(member)
    return seen


def weighted_terms(terms: list[str], weights: dict[str, float]) -> list[str]:
    """术语加权：重复高权词提升 FTS 命中权重（OR 查询天然受益）。"""
    expanded: list[str] = []
    for term in terms:
        expanded.append(term)
        weight = weights.get(term, 1.0)
        if weight > 1.0:
            expanded.append(term)
    return expanded
