"""目录与图片路由：登记/扫描/浏览/修正/隐藏/打回/删除/导出。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query, Request

from app.api.deps import get_state
from app.domain.errors import HiddenNotBypassable, ValidationAppError
from app.services import ingest, manage_svc, search_svc

router = APIRouter()

FORBIDDEN_HIDDEN_KEYS = ("hidden", "include_hidden", "with_hidden", "show_hidden")


def _reject_hidden(params: dict[str, Any]) -> None:
    for key in FORBIDDEN_HIDDEN_KEYS:
        if key in params and str(params[key]).lower() in ("1", "true", "yes"):
            raise HiddenNotBypassable("隐藏区不可通过查询参数绕过，请使用 /api/hidden")


# ---------- 目录 ----------


@router.get("/api/directories")
def list_directories(request: Request) -> dict[str, Any]:
    return {"items": ingest.list_directories(get_state(request))}


@router.post("/api/directories")
def create_directory(
    request: Request,
    payload: dict[str, Any] = Body(default={}),
    confirm: int = Query(default=0),
) -> dict[str, Any]:
    """登记目录：先返回预估，`?confirm=1` 才落库并扫描（导入向导两阶段）。"""
    state = get_state(request)
    if confirm != 1:
        return {"confirmed": False, "estimate": ingest.estimate_directory(state, payload)}
    dir_row = ingest.register_directory(state, payload)
    scan = ingest.scan_directory(state, int(dir_row["id"]))
    return {"confirmed": True, "directory": dir_row, "scan": scan}


@router.patch("/api/directories/{dir_id}")
def update_directory(
    dir_id: int, request: Request, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    state = get_state(request)
    dir_row = ingest.get_directory(state, dir_id)
    allowed = ("recursive", "enabled", "offline", "privacy", "frozen", "watcher", "ocr_policy")
    fields = {k: v for k, v in payload.items() if k in allowed}
    if "recursive" in fields:
        fields["recursive"] = int(bool(fields["recursive"]))
    for flag in ("enabled", "offline", "privacy", "frozen", "watcher"):
        if flag in fields:
            fields[flag] = int(bool(fields[flag]))
    state.dirs.update(dir_id, **fields)
    return ingest.get_directory(state, dir_id) if dir_row else {}


@router.delete("/api/directories/{dir_id}")
def delete_directory(dir_id: int, request: Request) -> dict[str, Any]:
    """注销目录：索引移除，源文件一律不动。注销前先给索引留一份快照。"""
    state = get_state(request)
    snapshot = manage_svc.snapshot_index(state)
    result = ingest.unregister_directory(state, dir_id)
    result["backup"] = snapshot["path"]
    result["backed_up"] = snapshot["count"]
    return result


@router.post("/api/scan/{dir_id}")
def scan(dir_id: int, request: Request) -> dict[str, Any]:
    state = get_state(request)
    return ingest.scan_directory(state, dir_id)


# ---------- 图片 ----------


def _query_params(request: Request) -> dict[str, Any]:
    params = dict(request.query_params)
    _reject_hidden(params)
    return params


@router.get("/api/images")
def list_images(request: Request) -> dict[str, Any]:
    state = get_state(request)
    params = _query_params(request)
    search_svc.validate_sort(params)
    return search_svc.search(state, params)


@router.get("/api/hidden")
def list_hidden(request: Request) -> dict[str, Any]:
    """隐藏区浏览（唯一的隐藏区入口；不透传任何 include_hidden 语义）。"""
    state = get_state(request)
    params: dict[str, Any] = dict(request.query_params)
    params["hidden"] = True
    return search_svc.search(state, params)


@router.get("/api/images/{image_id}")
def image_detail(image_id: int, request: Request) -> dict[str, Any]:
    return manage_svc.detail(get_state(request), image_id)


@router.patch("/api/images/{image_id}")
def patch_image(
    image_id: int, request: Request, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    return manage_svc.patch(get_state(request), image_id, payload)


@router.post("/api/images/{image_id}/hide")
def hide_image(image_id: int, request: Request) -> dict[str, Any]:
    return manage_svc.hide(get_state(request), [image_id])


@router.post("/api/images/{image_id}/unhide")
def unhide_image(image_id: int, request: Request) -> dict[str, Any]:
    return manage_svc.unhide(get_state(request), [image_id])


@router.post("/api/images/{image_id}/redo")
def redo_image(
    image_id: int, request: Request, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    return manage_svc.redo(get_state(request), image_id, str(payload.get("feedback", "")))


@router.post("/api/images/{image_id}/rename")
def rename_image(
    image_id: int, request: Request, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    return manage_svc.rename(get_state(request), image_id, str(payload.get("name", "")))


@router.post("/api/images/{image_id}/move")
def move_image(
    image_id: int, request: Request, payload: dict[str, Any] = Body(default={})
) -> dict[str, Any]:
    try:
        target = int(payload.get("dir_id", 0))
    except (TypeError, ValueError) as exc:
        raise ValidationAppError("dir_id 必须是整数") from exc
    return manage_svc.move_to(get_state(request), image_id, target)


@router.delete("/api/images/{image_id}")
def delete_image(
    image_id: int,
    request: Request,
    mode: str = Query(default="index"),
    confirm: str = Query(default=""),
) -> dict[str, Any]:
    return manage_svc.delete(get_state(request), image_id, mode, confirm)


@router.post("/api/images/batch")
def batch_images(
    request: Request,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    op = str(payload.get("op", ""))
    ids = [int(i) for i in payload.get("ids", [])]
    return manage_svc.batch_op(get_state(request), op, ids, payload.get("payload") or {})


@router.get("/api/images/{image_id}/similar")
def similar(
    image_id: int, request: Request, limit: int = Query(default=20, ge=1, le=100)
) -> dict[str, Any]:
    return search_svc.similar(get_state(request), image_id, limit)


@router.post("/api/export")
def export_images(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    state = get_state(request)
    ids = [int(i) for i in payload.get("ids", [])]
    if not ids:
        raise ValidationAppError("未选择任何图片")
    return manage_svc.export(state, ids, str(payload.get("format", "json")))


# ---------- 检索 ----------


@router.get("/api/search")
def search(request: Request) -> dict[str, Any]:
    state = get_state(request)
    return search_svc.search(state, _query_params(request))


@router.get("/api/search/history")
def search_history(request: Request) -> dict[str, Any]:
    return {"items": search_svc.history(get_state(request))}


@router.delete("/api/search/history")
def clear_search_history(request: Request) -> dict[str, Any]:
    search_svc.clear_history(get_state(request))
    return {"cleared": True}
