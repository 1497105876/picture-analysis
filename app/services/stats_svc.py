"""统计与运维服务：仪表盘、重复聚类、清理建议、回收站、通知与日志。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.domain.errors import NotFoundError, ValidationAppError
from app.files.trash import restore

if TYPE_CHECKING:
    from app.services.state import AppState


def dashboard(state: AppState) -> dict[str, Any]:
    data = dict(state.stats.dashboard())
    data["jobs"] = state.jobs.counts()
    data["dirs"] = len(state.dirs.list())
    return data


def _hamming(a: str, b: str) -> int:
    return sum(x != y for x, y in zip(a, b, strict=True)) if len(a) == len(b) else 64


def duplicate_groups(
    state: AppState, *, perceptual: bool = False, threshold: int = 6
) -> list[dict[str, Any]]:
    """md5 完全重复 + dhash 感知近似（默认汉明距离 ≤6）。"""
    if not perceptual:
        return state.stats.md5_duplicate_groups()
    rows = state.stats.all_dhashes()
    groups: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, row in enumerate(rows):
        if int(row["id"]) in seen:
            continue
        members = [row]
        for other in rows[index + 1 :]:
            if int(other["id"]) in seen:
                continue
            if _hamming(str(row["dhash"]), str(other["dhash"])) <= threshold:
                members.append(other)
                seen.add(int(other["id"]))
        if len(members) > 1:
            seen.add(int(row["id"]))
            groups.append({"kind": "perceptual", "images": members})
    return groups


def cleanup_suggestions(state: AppState) -> dict[str, Any]:
    visible, hidden = 0, 0
    missing = 0
    for table in ("images", "hidden_images"):
        rows = state.db.query(f"SELECT missing FROM {table}")
        if table == "images":
            visible = len(rows)
        else:
            hidden = len(rows)
        missing += sum(1 for row in rows if row["missing"])
    trash_rows = state.db.query("SELECT * FROM trash ORDER BY id DESC")
    orphan_thumbs = 0
    if state.thumbs_dir.is_dir():
        ids = {int(r["id"]) for r in state.db.query("SELECT id FROM images")}
        orphan_thumbs = sum(
            1
            for thumb in state.thumbs_dir.glob("*.jpg")
            if thumb.stem.isdigit() and int(thumb.stem) not in ids
        )
    db_bytes = state.db.path.stat().st_size if state.db.path.exists() else 0
    return {
        "missing_files": missing,
        "trash_count": len(trash_rows),
        "trash_items": [dict(row) for row in trash_rows[:50]],
        "orphan_thumbs": orphan_thumbs,
        "visible": visible,
        "hidden": hidden,
        "db_bytes": db_bytes,
        "suggestions": [
            *(["有文件已消失：重新扫描可刷新状态"] if missing else []),
            *(["回收站有记录：可清理以释放空间"] if len(trash_rows) else []),
            *(["存在孤儿缩略图：可重建缩略图"] if orphan_thumbs else []),
        ],
    }


def restore_trash(state: AppState, trash_id: int) -> dict[str, Any]:
    row = state.db.query_one("SELECT * FROM trash WHERE id=?", (trash_id,))
    if row is None:
        raise NotFoundError(f"回收站记录不存在：{trash_id}")
    trash_path = Path(str(row["trash_path"]))
    original = Path(str(row["original_path"]))
    if not trash_path.is_file():
        raise ValidationAppError(f"回收站文件已不存在：{trash_path}")
    restore(trash_path, original)
    state.db.execute("DELETE FROM trash WHERE id=?", (trash_id,))
    # 重新入库（保留原记录的场景由扫描覆盖；此处仅补索引缺失）
    existing = next((d for d in state.dirs.list() if str(original.parent) == str(d["path"])), None)
    if existing is not None:
        from app.services import ingest

        ingest.scan_directory(state, int(existing["id"]))
    return {"restored": str(original)}


def clear_trash(state: AppState, confirm: str) -> dict[str, Any]:
    if confirm != "清空回收站":
        from app.domain.errors import ConfirmWordMismatch

        raise ConfirmWordMismatch("确认词不匹配：请输入「清空回收站」")
    removed = 0
    for row in state.db.query("SELECT * FROM trash"):
        path = Path(str(row["trash_path"]))
        if path.is_file():
            path.unlink()
            removed += 1
    state.db.execute("DELETE FROM trash")
    return {"removed": removed}


def notices(state: AppState, limit: int = 50) -> list[dict[str, Any]]:
    return state.settings_repo.notices(limit)


def clear_notices(state: AppState) -> None:
    state.settings_repo.clear_notices()


def tail_log(state: AppState, lines: int = 200) -> list[str]:
    log_path = state.data_dir / "logs" / "app.log"
    if not log_path.is_file():
        return []
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            content = handle.readlines()
    except OSError:
        return []
    return [line.rstrip("\n") for line in content[-lines:]]


def jobs_status(state: AppState, state_filter: str | None = None) -> dict[str, Any]:
    return {
        "counts": state.jobs.counts(),
        "items": state.jobs.rows(state_filter, limit=200),
    }


def disk_usage(state: AppState) -> dict[str, Any]:
    db_bytes = state.db.path.stat().st_size if state.db.path.exists() else 0
    data: dict[str, Any] = {"db_bytes": db_bytes}
    if hasattr(os, "statvfs"):
        usage = os.statvfs(state.data_dir)
        data["free_bytes"] = usage.f_bavail * usage.f_frsize
        data["total_bytes"] = usage.f_blocks * usage.f_frsize
    else:  # Windows 无 statvfs
        usage_w = shutil.disk_usage(str(state.data_dir))
        data["free_bytes"] = usage_w.free
        data["total_bytes"] = usage_w.total
    return data
