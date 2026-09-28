"""运维路由：任务队列、仪表盘、重复聚类、清理建议、回收站。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query, Request

from app.api.deps import get_state
from app.services import stats_svc

router = APIRouter()


# ---------- 任务 ----------


@router.get("/api/jobs")
def list_jobs(request: Request, state: str | None = Query(default=None)) -> dict[str, Any]:
    return stats_svc.jobs_status(get_state(request), state)


@router.get("/api/jobs/{job_id}/events")
def job_events(job_id: int, request: Request) -> dict[str, Any]:
    return {"items": get_state(request).jobs.events(job_id)}


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int, request: Request) -> dict[str, Any]:
    return get_state(request).runner.cancel(job_id)


@router.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int, request: Request) -> dict[str, Any]:
    return get_state(request).runner.retry(job_id)


@router.delete("/api/jobs")
def clear_jobs(request: Request) -> dict[str, Any]:
    return {"cleared": get_state(request).jobs.clear_finished()}


# ---------- 统计 ----------


@router.get("/api/stats/dashboard")
def dashboard(request: Request) -> dict[str, Any]:
    return stats_svc.dashboard(get_state(request))


@router.get("/api/stats/duplicates")
def duplicates(
    request: Request,
    perceptual: int = Query(default=0),
    threshold: int = Query(default=6, ge=0, le=32),
) -> dict[str, Any]:
    return {
        "groups": stats_svc.duplicate_groups(
            get_state(request), perceptual=bool(perceptual), threshold=threshold
        )
    }


@router.get("/api/stats/cleanup")
def cleanup(request: Request) -> dict[str, Any]:
    return stats_svc.cleanup_suggestions(get_state(request))


@router.get("/api/stats/system")
def system_stats(request: Request) -> dict[str, Any]:
    return stats_svc.disk_usage(get_state(request))


# ---------- 回收站 ----------


@router.get("/api/trash")
def list_trash(request: Request) -> dict[str, Any]:
    state = get_state(request)
    return {
        "items": [
            dict(row) for row in state.db.query("SELECT * FROM trash ORDER BY id DESC LIMIT 200")
        ]
    }


@router.post("/api/trash/{trash_id}/restore")
def restore_trash(trash_id: int, request: Request) -> dict[str, Any]:
    return stats_svc.restore_trash(get_state(request), trash_id)


@router.delete("/api/trash")
def clear_trash(
    request: Request,
    confirm: str = Query(default=""),
) -> dict[str, Any]:
    return stats_svc.clear_trash(get_state(request), confirm)


# ---------- 危险操作 ----------


@router.post("/api/danger/clear-index")
def clear_index(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """清空索引（不删源文件）：必须携带确认词。"""
    state = get_state(request)
    if str(payload.get("confirm", "")) != "清空索引":
        from app.domain.errors import ConfirmWordMismatch

        raise ConfirmWordMismatch("确认词不匹配：请输入「清空索引」")
    count = 0
    for dir_row in state.dirs.list():
        count += state.images.delete_by_dir(int(dir_row["id"]))
    state.jobs.clear_finished()
    return {"removed": count}
