"""分类字典与智能相册服务（含级联重命名、内置保护、相册回放）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.domain.errors import ConflictError, NotFoundError, ValidationAppError
from app.services import search_svc

if TYPE_CHECKING:
    from app.services.state import AppState


def list_categories(state: AppState) -> list[dict[str, Any]]:
    return state.catalog.list_categories()


def add_category(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValidationAppError("分类名称不能为空")
    if state.catalog.get_category(name) is not None:
        raise ConflictError(f"分类已存在：{name}")
    category_id = state.catalog.add_category(
        name, str(payload.get("color", "#64748b")), str(payload.get("emoji", ""))
    )
    row = state.catalog.get_category(name)
    return {**(row or {}), "id": category_id}


def update_category(state: AppState, name: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = state.catalog.get_category(name)
    if row is None:
        raise NotFoundError(f"分类不存在：{name}")
    if row["builtin"]:
        raise ConflictError("内置分类不可修改")
    fields: dict[str, Any] = {}
    new_name = str(payload.get("name", "")).strip() or None
    if new_name and new_name != name:
        if state.catalog.get_category(new_name) is not None:
            raise ConflictError(f"分类已存在：{new_name}")
        fields["name"] = new_name
    if "color" in payload:
        fields["color"] = str(payload["color"])
    if "emoji" in payload:
        fields["emoji"] = str(payload["emoji"])
    if "active" in payload:
        fields["active"] = int(bool(payload["active"]))
    if "sort" in payload:
        fields["sort"] = int(payload["sort"])
    if fields:
        state.catalog.update_category(name, **fields)
        if "name" in fields:
            state.catalog.reassign_category(name, str(fields["name"]))
    return state.catalog.get_category(str(fields.get("name", name))) or {}


def delete_category(state: AppState, name: str) -> None:
    row = state.catalog.get_category(name)
    if row is None:
        raise NotFoundError(f"分类不存在：{name}")
    if row["builtin"]:
        raise ConflictError("内置分类不可删除")
    state.catalog.update_category(name, active=0)


# ---------- 智能相册 ----------


def list_albums(state: AppState) -> list[dict[str, Any]]:
    result = []
    for album in state.catalog.list_albums():
        item = dict(album)
        item["count"] = search_svc.count(state, album["query"])
        result.append(item)
    return result


def add_album(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValidationAppError("相册名称不能为空")
    query = payload.get("query") or {}
    if not isinstance(query, dict):
        raise ValidationAppError("query 必须是对象")
    sort = payload.get("sort") or {}
    album_id = state.catalog.add_album(name, query, sort)
    return state.catalog.get_album(album_id) or {}


def delete_album(state: AppState, album_id: int) -> None:
    if state.catalog.get_album(album_id) is None:
        raise NotFoundError(f"相册不存在：{album_id}")
    state.catalog.delete_album(album_id)


def album_images(state: AppState, album_id: int, params: dict[str, Any]) -> dict[str, Any]:
    album = state.catalog.get_album(album_id)
    if album is None:
        raise NotFoundError(f"相册不存在：{album_id}")
    merged = {**album["query"], **params}
    return search_svc.search(state, merged)


def update_album(state: AppState, album_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    album = state.catalog.get_album(album_id)
    if album is None:
        raise NotFoundError(f"相册不存在：{album_id}")
    # 相册改名走删除+重建（id 变化对外不可见，查询不变）
    if payload.get("name") or payload.get("query") or payload.get("sort"):
        state.catalog.delete_album(album_id)
        new_id = state.catalog.add_album(
            str(payload.get("name", album["name"])),
            payload.get("query", album["query"]),
            payload.get("sort", album["sort"]),
        )
        return state.catalog.get_album(new_id) or {}
    return album
