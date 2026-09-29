"""设置路由：schema 驱动读写、档案与密钥（.env）、连接探测、审计回滚、备份。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Request

from app.api.deps import get_state
from app.domain.errors import NotFoundError, ValidationAppError

router = APIRouter()


@router.get("/api/settings")
def get_settings(request: Request) -> dict[str, Any]:
    state = get_state(request)
    payload = state.settings.schema_payload()
    payload["profiles"] = state.settings.list_profiles()
    return payload


@router.put("/api/settings")
def put_settings(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    state = get_state(request)
    values = payload.get("values", payload)
    if not isinstance(values, dict):
        raise ValidationAppError("values 必须是对象")
    applied = state.settings.bulk_set(values)
    return {"applied": applied}


@router.post("/api/settings/test")
def test_connection(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    state = get_state(request)
    base_url = str(payload.get("base_url", "")).strip()
    api_key = str(payload.get("api_key", "") or "")
    if not base_url:
        profile = state.settings.resolved_profile(str(payload.get("usage", "vision")))
        if profile is None:
            raise NotFoundError("没有可用的服务档案：请先在设置页「服务档案」里新建一个")
        base_url = str(profile.get("base_url", ""))
        api_key = str(profile.get("api_key", "") or "")
    if not base_url.startswith(("http://", "https://")):
        raise ValidationAppError("base_url 必须以 http(s):// 开头")
    return state.settings.probe(base_url, api_key)


@router.get("/api/settings/audit")
def audit(request: Request, limit: int = 100) -> dict[str, Any]:
    return {"items": get_state(request).settings.audit(limit)}


@router.post("/api/settings/audit/{audit_id}/rollback")
def rollback(audit_id: int, request: Request) -> dict[str, Any]:
    get_state(request).settings.rollback(audit_id)
    return {"rolled_back": audit_id}


@router.get("/api/settings/profiles")
def profiles(request: Request) -> dict[str, Any]:
    return get_state(request).settings.profiles_payload()


@router.post("/api/settings/profiles")
def save_profile(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    return get_state(request).settings.save_profile(payload)


@router.delete("/api/settings/profiles/{name}")
def delete_profile(name: str, request: Request) -> dict[str, Any]:
    get_state(request).settings.delete_profile(name)
    return {"deleted": name}


@router.post("/api/settings/backup")
def backup(request: Request) -> dict[str, Any]:
    path = get_state(request).settings.backup()
    return {"path": str(path)}
