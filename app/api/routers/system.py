"""系统路由：健康、通知、日志、缩略图、上传导入。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import FileResponse

from app import __version__
from app.api.deps import get_state
from app.services import ingest, stats_svc

router = APIRouter()


@router.get("/api/health")
def health() -> dict[str, str]:
    """存活探测：CI 与监控的冒烟端点。"""
    return {"status": "ok", "version": __version__}


@router.get("/api/notices")
def list_notices(request: Request, limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
    return {"items": stats_svc.notices(get_state(request), limit)}


@router.delete("/api/notices")
def clear_notices(request: Request) -> dict[str, Any]:
    stats_svc.clear_notices(get_state(request))
    return {"cleared": True}


@router.get("/api/logs")
def logs(request: Request, lines: int = Query(default=200, ge=1, le=2000)) -> dict[str, Any]:
    state = get_state(request)
    return {
        "lines": stats_svc.tail_log(state, lines),
        "notices": stats_svc.notices(state, 20),
        "level": state.settings.get_str("log_level", "INFO"),
    }


@router.get("/api/thumbs/{image_id}")
def thumb(image_id: int, request: Request) -> FileResponse:
    state = get_state(request)
    path = state.thumbs_dir / f"{image_id}.jpg"
    if not path.is_file():
        from app.domain.errors import NotFoundError

        raise NotFoundError(f"缩略图不存在：{image_id}")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/api/upload")
async def upload(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    """截图/剪贴板导入：复制进 data/uploads 并登记为来源目录。"""
    state = get_state(request)
    content = await file.read()
    if not content:
        from app.domain.errors import ValidationAppError

        raise ValidationAppError("上传内容为空")
    return ingest.export_upload(state, file.filename or "image.jpg", content)
