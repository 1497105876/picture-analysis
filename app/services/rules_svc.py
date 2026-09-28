"""规则引擎服务：两阶段求值、试跑、历史补算（只写 AI 分类位，人工位不动）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.domain.rules_eval import Rule, RuleContext, first_match, match_condition
from app.storage.search_repo import Filters

if TYPE_CHECKING:
    from app.services.state import AppState


def load_rules(state: AppState) -> list[Rule]:
    if not state.settings.get_bool("rules_enabled", True):
        return []
    result: list[Rule] = []
    for row in state.catalog.list_rules():
        result.append(
            Rule(
                id=int(row["id"]),
                name=str(row["name"]),
                priority=int(row["priority"]),
                enabled=bool(row["enabled"]),
                condition=dict(row["condition"]),
                action=dict(row["action"]),
            )
        )
    return result


def build_context(state: AppState, image: dict[str, Any], ocr_text: str = "") -> RuleContext:
    dir_row = state.dirs.get(int(image["dir_id"]))
    dir_path = str(dir_row["path"]) if dir_row else ""
    category = image.get("category_manual") or image.get("category_ai")
    return RuleContext(
        path=str(image["path"]),
        filename=str(image["filename"]),
        dir_path=dir_path,
        ocr_text=ocr_text,
        category=str(category) if category else None,
    )


def _apply_action(state: AppState, image_id: int, action: dict[str, Any]) -> dict[str, Any]:
    applied: dict[str, Any] = {}
    category = action.get("set_category")
    if category:
        state.images.update_any(image_id, category_ai=str(category))
        applied["category"] = str(category)
    tags = action.get("add_tags") or []
    album = action.get("add_to_album")
    extra: list[str] = [str(t) for t in tags]
    if album:
        extra.append(f"album:{album}")
    if extra:
        existing = state.images.ai_tags_of(image_id)
        merged = list(dict.fromkeys([*existing, *extra]))[:5]
        state.images.replace_ai_tags(image_id, merged)
        applied["tags"] = merged
        if album:
            applied["album"] = str(album)
    if applied:
        state.images.sync_fts(image_id)
    return applied


def apply_phase(
    state: AppState,
    image: dict[str, Any],
    phase: str,
    *,
    ocr_text: str = "",
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """phase='pre' 评估非 OCR 条件（入库即判）；phase='ocr' 仅评估 OCR 条件。"""
    rules = load_rules(state)
    ctx = build_context(state, image, ocr_text)
    if phase == "pre":
        candidates = [r for r in rules if r.condition.get("target") != "ocr_text"]
    else:
        candidates = [r for r in rules if r.condition.get("target") == "ocr_text"]
    hit = first_match(candidates, ctx)
    if hit is None:
        return None
    if dry_run:
        return {"rule_id": hit.id, "rule": hit.name, "action": dict(hit.action)}
    applied = _apply_action(state, int(image["id"]), hit.action)
    return {"rule_id": hit.id, "rule": hit.name, "action": applied}


def dry_run(state: AppState, condition: dict[str, Any], limit: int = 50) -> dict[str, Any]:
    """试跑：只预览命中，不落库。"""
    matches: list[dict[str, Any]] = []
    rows, _ = state.search.list_images(Filters(), limit=1000)
    for image in rows:
        ctx = build_context(state, image, state.images.get_ocr_text(int(image["id"])))
        if match_condition(condition, ctx):
            matches.append({"id": image["id"], "path": image["path"]})
            if len(matches) >= limit:
                break
    return {"count": len(matches), "matches": matches, "scanned": len(rows)}


def recompute(state: AppState, phase: str) -> int:
    """历史图一键补算（幂等：AI 分类位可再次覆盖，人工位不参与）。"""
    count = 0
    cursor: str | None = None
    for _ in range(1000):
        rows, cursor = state.search.list_images(Filters(), limit=200, cursor=cursor)
        for image in rows:
            ocr_text = state.images.get_ocr_text(int(image["id"])) if phase == "ocr" else ""
            if apply_phase(state, image, phase, ocr_text=ocr_text) is not None:
                count += 1
        if not cursor or not rows:
            break
    return count


def recompute_one(state: AppState, image_id: int, phase: str) -> dict[str, Any] | None:
    image = state.images.get(image_id)
    if image is None:
        return None
    ocr_text = state.images.get_ocr_text(image_id) if phase == "ocr" else ""
    return apply_phase(state, image, phase, ocr_text=ocr_text)
