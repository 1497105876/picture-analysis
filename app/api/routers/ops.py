"""运维路由：任务队列、仪表盘、重复聚类、清理建议、回收站。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query, Request

from app.api.deps import get_state
from app.domain.errors import ValidationAppError
from app.services import manage_svc, stats_svc

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


# ---------- 排除表（只删索引留下的墓碑） ----------
# 「只删索引」原本是单向的：删了就再也回不来，界面上也看不到它存在。
# 这一组接口把它变成可逆操作。


@router.get("/api/excluded")
def list_excluded(request: Request) -> dict[str, Any]:
    """列出被「只删索引」排除的文件（墓碑），含文件是否还在、原目录是否仍登记。"""
    return manage_svc.list_excluded(get_state(request))


@router.post("/api/excluded/{exclusion_id}/restore")
def restore_excluded(exclusion_id: int, request: Request) -> dict[str, Any]:
    """解除排除并立刻重新入库——不用再让用户去点「增量扫描」。"""
    return manage_svc.restore_excluded(get_state(request), exclusion_id)


@router.delete("/api/excluded/{exclusion_id}")
def forget_excluded(exclusion_id: int, request: Request) -> dict[str, Any]:
    """只解除排除（不立刻入库）：下次增量扫描会重新收录它。"""
    return manage_svc.forget_excluded(get_state(request), exclusion_id)


@router.delete("/api/excluded")
def clear_excluded(request: Request, confirm: str = Query(default="")) -> dict[str, Any]:
    """清空排除表：清除所有墓碑，重新扫描会把这些文件全部收录回来。"""
    return manage_svc.clear_excluded(get_state(request), confirm)


# ---------- 断链体检 ----------
# 源文件在磁盘上被改名/移动/删除后，索引里那条记录就成了打不开的死链。
# 以前只有仪表盘一个 missing_files 数字，看不到是哪几张、也清理不掉。


@router.get("/api/health/broken")
def list_broken(request: Request, limit: int = Query(default=500)) -> dict[str, Any]:
    """逐条比对磁盘，列出「索引里有、文件没了」的条目（含隐藏区）。"""
    return manage_svc.list_broken(get_state(request), limit)


@router.post("/api/health/prune")
def prune_broken(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """把断链条目从索引摘掉。exclude=true 时额外登记排除（确认词「清理并排除」）。"""
    raw_ids = payload.get("ids") or []
    try:
        ids = [int(i) for i in raw_ids]
    except (TypeError, ValueError) as exc:
        raise ValidationAppError("ids 必须是整数数组") from exc
    return manage_svc.prune_broken(
        get_state(request),
        ids,
        exclude=bool(payload.get("exclude", False)),
        confirm=str(payload.get("confirm", "")),
    )


@router.post("/api/health/rescan/{dir_id}")
def rescan_dir(dir_id: int, request: Request) -> dict[str, Any]:
    """重扫目录：文件还在的会自动去掉 missing 标记。"""
    return manage_svc.refresh_broken(get_state(request), dir_id)


# ---------- 危险操作 ----------


@router.post("/api/danger/clear-index")
def clear_index(request: Request, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """清空索引（不删源文件）：必须携带确认词。"""
    state = get_state(request)
    if str(payload.get("confirm", "")) != "清空索引":
        from app.domain.errors import ConfirmWordMismatch

        raise ConfirmWordMismatch("确认词不匹配：请输入「清空索引」")
    # 人工标注跟着索引一起走，先自动留一份快照再动手
    snapshot = manage_svc.snapshot_index(state)
    count = 0
    for dir_row in state.dirs.list():
        count += state.images.delete_by_dir(int(dir_row["id"]))
    state.jobs.clear_finished()
    return {
        "removed": count,
        "backup": snapshot["path"],
        "backed_up": snapshot["count"],
    }
