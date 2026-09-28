"""检索服务：查询增强、同义词展开、FTS + 向量 RRF、cursor 分页、以图搜图。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from app.ai.prompts import build_chat_parse_prompt, parse_chat_json
from app.ai.protocol import ChatClient
from app.domain.errors import ValidationAppError
from app.domain.fusion import expand_query, rrf_merge, weighted_terms
from app.storage.search_repo import SORT_COLUMNS, Filters

if TYPE_CHECKING:
    from app.services.state import AppState


def validate_sort(params: dict[str, Any]) -> None:
    """排序字段白名单（列表/检索共用，越界给出人话报错）。"""
    sort = params.get("sort")
    if sort and str(sort) not in SORT_COLUMNS:
        raise ValidationAppError(f"不支持的排序字段：{sort}")


def _filters_from(params: dict[str, Any]) -> Filters:
    def as_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    tags = params.get("tags") or []
    if isinstance(tags, str):
        tags = [t for t in tags.split(",") if t]
    return Filters(
        category=params.get("category") or None,
        tags=[str(t) for t in tags],
        rating_min=as_int(params.get("rating_min")),
        favorite=(
            None
            if params.get("favorite") in (None, "")
            else str(params.get("favorite")).lower() in ("1", "true", "yes")
        ),
        dir_id=as_int(params.get("dir_id")),
        date_from=params.get("date_from") or None,
        date_to=params.get("date_to") or None,
        analysis_state=params.get("analysis_state") or None,
        hidden=bool(params.get("hidden", False)),
    )


def _enhance(state: AppState, query: str, chat: ChatClient | None) -> dict[str, Any]:
    """LLM 查询增强（失败自动回退原词，绝不阻塞检索）。"""
    if not state.settings.get_bool("query_enhance", False) or chat is None:
        return {"keywords": [query] if query else [], "category": None}
    categories = [str(row["name"]) for row in state.catalog.list_categories()]
    try:
        output = chat.complete(
            [
                {"role": "user", "content": build_chat_parse_prompt(query, categories)},
            ]
        )
    except Exception:  # noqa: BLE001 — 增强是可选增强，失败回退
        return {"keywords": [query] if query else [], "category": None}
    parsed = parse_chat_json(output.content) or {}
    keywords = [str(k) for k in parsed.get("keywords") or [] if str(k).strip()]
    state.images.add_token_usage(None, "enhance", output.model, output.tokens_in, output.tokens_out)
    return {
        "keywords": keywords or ([query] if query else []),
        "category": parsed.get("category"),
    }


def _terms(state: AppState, query: str, chat: ChatClient | None) -> list[str]:
    enhanced = _enhance(state, query, chat)
    base: list[str] = [t for t in enhanced["keywords"] if t]
    if not base and query:
        base = [query]
    if state.settings.get_bool("synonyms_enabled", True):
        expanded = expand_query(" ".join(base), state.search.synonym_map())
    else:
        expanded = base
    if state.settings.get_bool("term_weight_enabled", True):
        expanded = weighted_terms(expanded, state.search.term_weights())
    return expanded


def search(
    state: AppState,
    params: dict[str, Any],
    *,
    restrict_ids: list[int] | None = None,
) -> dict[str, Any]:
    """hybrid | keyword | vector；返回 items/next_cursor/分路耗时/降级标记。"""
    started = time.perf_counter()
    query = str(params.get("q") or "").strip()
    mode = str(params.get("mode") or state.settings.get("search_mode", "hybrid"))
    if mode not in ("hybrid", "keyword", "vector"):
        mode = "hybrid"
    limit = min(max(int(params.get("limit") or 60), 1), int(params.get("_cap") or 200))
    filters = _filters_from(params)
    sort = str(params.get("sort") or "mtime")
    order = str(params.get("order") or "desc")
    cursor = params.get("cursor") or None
    chat = state.get_chat()

    terms = _terms(state, query, chat) if query else []
    if query and state.settings.get_bool("search_history_enabled", True):
        state.search.add_history(query)

    keyword_ids: list[int] = []
    vector_ranked: list[tuple[int, float]] = []
    degraded = False
    kw_ms = vec_ms = 0.0

    if mode in ("hybrid", "keyword") and terms:
        t0 = time.perf_counter()
        keyword_ids = state.search.fts_search(terms)
        kw_ms = (time.perf_counter() - t0) * 1000

    if mode in ("hybrid", "vector") and query:
        embed = state.get_embed()
        if embed is None:
            degraded = True
        else:
            t0 = time.perf_counter()
            try:
                matrix = embed.embed([query])
                if matrix.size:
                    vector_ranked = state.search.vector_search(matrix[0], 200, filters)
            except Exception:  # noqa: BLE001 — 嵌入失败降级为关键词
                degraded = True
            vec_ms = (time.perf_counter() - t0) * 1000

    rrf_k = int(state.settings.get("rrf_k", 60))
    threshold = float(state.settings.get("similarity_threshold", 0.0))
    ordered_ids: list[int] = []
    scores: dict[int, float] = {}
    if mode == "keyword":
        ordered_ids = keyword_ids
    elif mode == "vector":
        ordered_ids = [image_id for image_id, score in vector_ranked if score >= threshold]
        scores = dict(vector_ranked)
    else:
        merged = rrf_merge([keyword_ids, [i for i, _ in vector_ranked]], [1.0, 1.0], k=rrf_k)
        ordered_ids = [image_id for image_id, _ in merged]
        scores = dict(merged)
        if not keyword_ids and not vector_ranked and query:
            degraded = True

    rows, next_cursor = state.search.list_images(
        filters,
        sort=sort,
        order=order,
        cursor=cursor,
        limit=limit,
        restrict_ids=ordered_ids if query else None,
    )
    items = []
    for row in rows:
        item = dict(row)
        item["score"] = scores.get(int(row["id"]))
        item["thumb"] = f"/api/thumbs/{row['id']}"
        items.append(item)
    total_ms = (time.perf_counter() - started) * 1000
    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
        "mode": mode,
        "degraded": degraded,
        "total": len(items),
        "timings": {
            "total_ms": round(total_ms, 2),
            "keyword_ms": round(kw_ms, 2),
            "vector_ms": round(vec_ms, 2),
        },
    }


def similar(state: AppState, image_id: int, limit: int = 20) -> dict[str, Any]:
    image = state.images.get(image_id)
    if image is None:
        from app.domain.errors import NotFoundError

        raise NotFoundError(f"图片不存在：{image_id}")
    vector = state.images.get_vector(image_id)
    if vector is None:
        embed = state.get_embed()
        if embed is None:
            return {"items": [], "degraded": True}
        description = str(image.get("description_manual") or image.get("description_ai") or "")
        matrix = embed.embed([description or str(image["filename"])])
        if not matrix.size:
            return {"items": [], "degraded": True}
        vector = matrix[0]
    ranked = state.search.vector_search(vector, limit + 1, Filters())
    ids = [i for i, _ in ranked if i != image_id][:limit]
    rows, _ = state.search.list_images(Filters(), limit=limit, restrict_ids=ids)
    return {
        "items": [dict(row) for row in rows],
        "degraded": False,
    }


def history(state: AppState) -> list[str]:
    if not state.settings.get_bool("search_history_enabled", True):
        return []
    return state.search.list_history()


def clear_history(state: AppState) -> None:
    state.search.clear_history()


def count(state: AppState, params: dict[str, Any]) -> int:
    """分页累计总数（智能相册计数用）。"""
    total = 0
    cursor: str | None = None
    for _ in range(100):
        result = search(state, {**params, "limit": 500, "_cap": 500, "cursor": cursor})
        total += result["total"]
        cursor = result["next_cursor"]
        if not cursor:
            break
    return total
