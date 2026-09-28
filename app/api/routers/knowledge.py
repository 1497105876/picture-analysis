"""知识路由：分类字典、实体资料库、规则、智能相册、提案、自定义字段、同义词。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from app.api.deps import get_state
from app.domain.errors import ValidationAppError
from app.services import catalog_svc, chat_svc, entities_svc, rules_svc

router = APIRouter()


# ---------- 分类 ----------


@router.get("/api/categories")
def list_categories(request: Request) -> dict[str, Any]:
    return {"items": catalog_svc.list_categories(get_state(request))}


@router.post("/api/categories")
def create_category(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return catalog_svc.add_category(get_state(request), payload)


@router.patch("/api/categories/{name}")
def patch_category(
    name: str, request: Request, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    return catalog_svc.update_category(get_state(request), name, payload)


@router.delete("/api/categories/{name}")
def remove_category(name: str, request: Request) -> dict[str, Any]:
    catalog_svc.delete_category(get_state(request), name)
    return {"deleted": name}


# ---------- 实体 ----------


@router.get("/api/entities")
def list_entities(request: Request, include_inactive: int = 0) -> dict[str, Any]:
    state = get_state(request)
    return {"items": entities_svc.list_entities(state, bool(include_inactive))}


@router.post("/api/entities")
def create_entity(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return entities_svc.create_entity(get_state(request), payload)


@router.get("/api/entities/{entity_id}")
def get_entity(entity_id: int, request: Request) -> dict[str, Any]:
    return entities_svc.get_entity(get_state(request), entity_id)


@router.patch("/api/entities/{entity_id}")
def patch_entity(
    entity_id: int, request: Request, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    return entities_svc.update_entity(get_state(request), entity_id, payload)


@router.delete("/api/entities/{entity_id}")
def remove_entity(entity_id: int, request: Request) -> dict[str, Any]:
    entities_svc.delete_entity(get_state(request), entity_id)
    return {"deleted": entity_id}


@router.post("/api/entities/{entity_id}/references")
def add_reference(
    entity_id: int, request: Request, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    return entities_svc.add_reference(get_state(request), entity_id, str(payload.get("path", "")))


@router.delete("/api/entities/{entity_id}/references/{ref_id}")
def remove_reference(entity_id: int, ref_id: int, request: Request) -> dict[str, Any]:
    return entities_svc.remove_reference(get_state(request), entity_id, ref_id)


@router.post("/api/entities/{entity_id}/link")
def link_entity_image(
    entity_id: int, request: Request, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    try:
        image_id = int(payload.get("image_id", 0))
    except (TypeError, ValueError) as exc:
        raise ValidationAppError("image_id 必须是整数") from exc
    entities_svc.link_image(get_state(request), entity_id, image_id)
    return {"linked": image_id}


@router.delete("/api/entities/{entity_id}/link/{image_id}")
def unlink_entity_image(entity_id: int, image_id: int, request: Request) -> dict[str, Any]:
    entities_svc.unlink_image(get_state(request), entity_id, image_id)
    return {"unlinked": image_id}


# ---------- 规则 ----------


@router.get("/api/rules")
def list_rules(request: Request) -> dict[str, Any]:
    return {"items": get_state(request).catalog.list_rules()}


@router.post("/api/rules")
def create_rule(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    state = get_state(request)
    condition = payload.get("condition")
    action = payload.get("action")
    if not isinstance(condition, dict) or not condition:
        raise ValidationAppError("condition 必须是非空对象")
    if not isinstance(action, dict) or not action:
        raise ValidationAppError("action 必须是非空对象")
    rule_id = state.catalog.add_rule(
        str(payload.get("name", "未命名规则")),
        int(payload.get("priority", 0)),
        condition,
        action,
        bool(payload.get("enabled", True)),
    )
    return {"id": rule_id}


@router.patch("/api/rules/{rule_id}")
def patch_rule(
    rule_id: int, request: Request, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    state = get_state(request)
    state.catalog.update_rule(rule_id, **payload)
    return {"updated": rule_id}


@router.delete("/api/rules/{rule_id}")
def remove_rule(rule_id: int, request: Request) -> dict[str, Any]:
    get_state(request).catalog.delete_rule(rule_id)
    return {"deleted": rule_id}


@router.post("/api/rules/try")
def try_rule(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    state = get_state(request)
    condition = payload.get("condition")
    if not isinstance(condition, dict):
        raise ValidationAppError("condition 必须是对象")
    return rules_svc.dry_run(state, condition, int(payload.get("limit", 50)))


@router.post("/api/rules/recompute")
def recompute_rules(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    state = get_state(request)
    phase = str(payload.get("phase", "pre"))
    if phase not in ("pre", "ocr"):
        raise ValidationAppError("phase 只能是 pre 或 ocr")
    return {"phase": phase, "applied": rules_svc.recompute(state, phase)}


# ---------- 智能相册 ----------


@router.get("/api/albums")
def list_albums(request: Request) -> dict[str, Any]:
    return {"items": catalog_svc.list_albums(get_state(request))}


@router.post("/api/albums")
def create_album(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return catalog_svc.add_album(get_state(request), payload)


@router.patch("/api/albums/{album_id}")
def patch_album(
    album_id: int, request: Request, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    return catalog_svc.update_album(get_state(request), album_id, payload)


@router.delete("/api/albums/{album_id}")
def remove_album(album_id: int, request: Request) -> dict[str, Any]:
    catalog_svc.delete_album(get_state(request), album_id)
    return {"deleted": album_id}


@router.get("/api/albums/{album_id}/images")
def album_images(album_id: int, request: Request) -> dict[str, Any]:
    params = dict(request.query_params)
    return catalog_svc.album_images(get_state(request), album_id, params)


# ---------- 提案 ----------


@router.get("/api/proposals")
def list_proposals(request: Request, status: str | None = None) -> dict[str, Any]:
    return {"items": chat_svc.list_proposals(get_state(request), status)}


@router.post("/api/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: int, request: Request) -> dict[str, Any]:
    return chat_svc.decide_proposal(get_state(request), proposal_id, "approved")


@router.post("/api/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int, request: Request) -> dict[str, Any]:
    return chat_svc.decide_proposal(get_state(request), proposal_id, "rejected")


# ---------- 自定义字段 ----------


@router.get("/api/custom-fields")
def list_custom_fields(request: Request) -> dict[str, Any]:
    return {"items": get_state(request).catalog.list_custom_fields()}


@router.post("/api/custom-fields")
def create_custom_field(
    request: Request, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    state = get_state(request)
    name = str(payload.get("name", "")).strip()
    ftype = str(payload.get("type", "text"))
    if not name:
        raise ValidationAppError("字段名称不能为空")
    if ftype not in ("text", "number", "date", "select"):
        raise ValidationAppError("字段类型只能是 text/number/date/select")
    options = [str(o) for o in payload.get("options", [])]
    field_id = state.catalog.add_custom_field(name, ftype, options)
    return {"id": field_id}


@router.delete("/api/custom-fields/{field_id}")
def remove_custom_field(field_id: int, request: Request) -> dict[str, Any]:
    get_state(request).catalog.delete_custom_field(field_id)
    return {"deleted": field_id}


# ---------- 同义词 / 术语权重 ----------


@router.get("/api/synonyms")
def list_synonyms(request: Request) -> dict[str, Any]:
    return {"groups": get_state(request).catalog.list_synonym_groups()}


@router.put("/api/synonyms")
def put_synonyms(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    state = get_state(request)
    group = str(payload.get("group", "")).strip()
    terms = [str(t) for t in payload.get("terms", []) if str(t).strip()]
    if not group or not terms:
        raise ValidationAppError("同义词组名与词条不能为空")
    state.catalog.add_synonym_group(group, terms)
    return {"group": group, "terms": terms}


@router.get("/api/term-weights")
def list_term_weights(request: Request) -> dict[str, Any]:
    return {"weights": get_state(request).search.term_weights()}


@router.put("/api/term-weights")
def put_term_weight(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    state = get_state(request)
    term = str(payload.get("term", "")).strip()
    if not term:
        raise ValidationAppError("术语不能为空")
    try:
        weight = float(payload.get("weight", 1.0))
    except (TypeError, ValueError) as exc:
        raise ValidationAppError("权重必须是数字") from exc
    state.catalog.set_term_weight(term, weight)
    return {"term": term, "weight": weight}
