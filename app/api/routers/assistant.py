"""对话路由：自然语言问图（软失败返回引导语）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from app.api.deps import get_state
from app.services import chat_svc

router = APIRouter()


@router.post("/api/chat")
def ask_post(request: Request, payload: dict[str, Any]) -> dict[str, Any]:
    return chat_svc.ask(get_state(request), str(payload.get("question", "")))


@router.get("/api/chat")
def ask_get(
    request: Request,
    q: str = Query(default=""),
    limit: int = Query(default=400, ge=1, le=400),
) -> dict[str, Any]:
    return chat_svc.ask(get_state(request), q[:limit])
