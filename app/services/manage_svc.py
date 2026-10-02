"""管理服务：人工修正、隐藏、打回、删除（回收站）、改名移动、导出。"""

from __future__ import annotations

import csv
import io
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.domain.errors import (
    ConfirmWordMismatch,
    NotFoundError,
    PathTraversalError,
    ValidationAppError,
)
from app.files.media import strip_exif
from app.files.trash import move_to_trash
from app.services import ingest
from app.storage.db import now_iso

if TYPE_CHECKING:
    from app.services.state import AppState


def _image_or_404(state: AppState, image_id: int) -> dict[str, Any]:
    image = state.images.get(image_id) or state.images.get_hidden(image_id)
    if image is None:
        raise NotFoundError(f"图片不存在：{image_id}")
    return image


def detail(state: AppState, image_id: int) -> dict[str, Any]:
    image = _image_or_404(state, image_id)
    hidden = state.images.get(image_id) is None
    analyses = [
        dict(row)
        for row in state.db.query(
            "SELECT * FROM analyses WHERE image_id=? ORDER BY id", (image_id,)
        )
    ]
    item = dict(image)
    item.update(
        {
            "hidden": hidden,
            "manual_tags": state.images.manual_tags_of(image_id),
            "ai_tags": state.images.ai_tags_of(image_id),
            "elements": state.images.elements_of(image_id),
            "ocr_text": state.images.get_ocr_text(image_id),
            "analyses": analyses,
            "custom_fields": state.images.custom_values_of(image_id),
            "thumb": f"/api/thumbs/{image_id}",
            "has_thumb": (state.thumbs_dir / f"{image_id}.jpg").exists(),
            "last_jobs": _recent_jobs(state, image_id),
        }
    )
    return item


def _recent_jobs(state: AppState, image_id: int, limit: int = 3) -> list[dict[str, Any]]:
    """这张图最近的任务，用于在详情里解释「为什么还没识别/为什么失败」。"""
    rows = state.db.query(
        "SELECT id, type, state, attempts, max_attempts, error, retry_at, updated_at "
        "FROM jobs WHERE image_id=? ORDER BY id DESC LIMIT ?",
        (image_id, limit),
    )
    return [
        {
            "id": int(r["id"]),
            "type": r["type"],
            "state": r["state"],
            "attempts": int(r["attempts"] or 0),
            "max_attempts": int(r["max_attempts"] or 0),
            "error": r["error"] or "",
            "retry_at": r["retry_at"] or "",
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def patch(state: AppState, image_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """人工修正：只写人工位，AI 字段永不覆盖；FTS 即时重建。"""
    image = _image_or_404(state, image_id)
    fields: dict[str, Any] = {}
    corrections = 0

    if "category" in payload:
        new_category = payload.get("category") or None
        if new_category != image.get("category_manual"):
            fields["category_manual"] = new_category
            corrections += 1
    if "description" in payload:
        new_desc = payload.get("description") or None
        if new_desc != image.get("description_manual"):
            fields["description_manual"] = new_desc
            corrections += 1
    if "notes" in payload:
        fields["notes"] = payload.get("notes") or None
    if "rating" in payload:
        try:
            rating = int(payload.get("rating") or 0)
        except (TypeError, ValueError) as exc:
            raise ValidationAppError("评分必须是 0~5 的整数") from exc
        if not 0 <= rating <= 5:
            raise ValidationAppError("评分必须是 0~5 的整数")
        fields["rating"] = rating
    if "favorite" in payload:
        fields["favorite"] = int(bool(payload.get("favorite")))

    if corrections:
        fields["correction_count"] = int(image.get("correction_count") or 0) + corrections
    if fields:
        state.images.update_any(image_id, **fields)
    if "tags" in payload:
        tags = payload.get("tags") or []
        if isinstance(tags, str):
            tags = [t for t in tags.split(",") if t.strip()]
        state.images.set_manual_tags(image_id, [str(t) for t in tags])
    for field_def in state.catalog.list_custom_fields():
        name = str(field_def["name"])
        if name in payload:
            state.images.set_custom_value(int(field_def["id"]), image_id, payload[name])
    if fields or "tags" in payload:
        state.images.sync_fts(image_id)
    if corrections:
        state.notice("correction", f"图片 #{image_id} 已人工修正", "info")
    return detail(state, image_id)


def redo(state: AppState, image_id: int, feedback: str = "") -> dict[str, Any]:
    """打回重识别：带纠正说明，计入人工纠错次数。"""
    image = _image_or_404(state, image_id)
    state.images.update_any(
        image_id,
        analysis_state="queued",
        last_feedback=feedback or None,
        correction_count=int(image.get("correction_count") or 0) + 1,
    )
    state.jobs.enqueue(
        "analyze",
        image_id=image_id,
        priority=100,
        payload={"redo": True, "feedback": feedback},
        dedupe=False,
        max_attempts=max(1, int(state.settings.get("max_retries", 3))),
    )
    return detail(state, image_id)


def hide(state: AppState, ids: list[int]) -> dict[str, Any]:
    hidden: list[int] = []
    for image_id in ids:
        if state.images.move_to_hidden(image_id):
            state.images.fts_delete(image_id)
            hidden.append(image_id)
    return {"hidden": hidden, "count": len(hidden)}


def unhide(state: AppState, ids: list[int]) -> dict[str, Any]:
    restored: list[int] = []
    for image_id in ids:
        if state.images.move_from_hidden(image_id):
            state.images.sync_fts(image_id)
            restored.append(image_id)
    return {"restored": restored, "count": len(restored)}


def delete(
    state: AppState, image_id: int, mode: str = "index", confirm: str = ""
) -> dict[str, Any]:
    """删除：mode=index 只删索引（登记排除，增量扫描不再收录）；
    mode=source 源文件进回收站（可找回，恢复后照常重新入库）。"""
    image = _image_or_404(state, image_id)
    if mode not in ("index", "source"):
        raise ValidationAppError("mode 只能是 index 或 source")
    if mode == "source":
        expected = str(Path(str(image["path"])).name)
        if confirm != expected:
            raise ConfirmWordMismatch(f"确认词不匹配：请输入文件名 {expected}")
        source = Path(str(image["path"]))
        if not ingest.is_registered_path(state, str(source)):
            raise PathTraversalError("文件不在任何已登记目录内，拒绝操作")
        if source.is_file():
            trash_path = move_to_trash(source, state.trash_dir)
            state.db.execute(
                "INSERT INTO trash(image_id, original_path, trash_path, deleted_at) "
                "VALUES(?,?,?,?)",
                (image_id, str(source), str(trash_path), now_iso()),
            )
    state.images.delete(image_id)
    if mode == "index":
        state.images.exclude_path(int(image["dir_id"]), str(image["path"]))
    return {"image_id": image_id, "mode": mode}


# ---------- 排除表（只删索引留下的墓碑） ----------
# 之前这条路是单向的：删了索引就再也回不来，界面上也看不到它存在。
# 这一组接口把「删索引」变成可逆操作。


def list_excluded(state: AppState, limit: int = 200) -> dict[str, Any]:
    rows = state.images.list_exclusions(limit)
    for row in rows:
        p = Path(str(row["path"]))
        row["filename"] = p.name
        row["exists"] = p.is_file()
        row["registered"] = bool(state.dirs.get(int(row["dir_id"])))
    return {"items": rows, "count": state.images.exclusion_count()}


def restore_excluded(state: AppState, exclusion_id: int) -> dict[str, Any]:
    """解除排除并立刻重新入库（不需要用户再去点扫描）。"""
    row = state.images.exclusion_row(exclusion_id)
    if row is None:
        raise NotFoundError(f"排除记录不存在：{exclusion_id}")
    path = Path(str(row["path"]))
    if not path.is_file():
        raise ValidationAppError(
            f"文件已不在原位置：{path}（可能是被你手动移动或删除了，"
            f"可以用「移除记录」清掉这条墓碑）"
        )
    dir_row = state.dirs.get(int(row["dir_id"]))
    if dir_row is None:
        raise ValidationAppError("这张图原来的目录已经注销了，请重新登记该目录后再试")
    if not bool(dir_row["enabled"]):
        raise ValidationAppError("原目录当前是停用状态，先启用再恢复")
    state.images.delete_exclusion(exclusion_id)
    image_id, action = ingest.ingest_file(state, dir_row, path, seen=set())
    return {"restored": str(path), "image_id": image_id, "action": action}


def forget_excluded(state: AppState, exclusion_id: int) -> dict[str, Any]:
    """只解除排除，不立刻入库——下次增量扫描会重新收录它。"""
    if not state.images.delete_exclusion(exclusion_id):
        raise NotFoundError(f"排除记录不存在：{exclusion_id}")
    return {"forgotten": exclusion_id, "hint": "已解除排除，下次增量扫描会重新收录"}


def clear_excluded(state: AppState, confirm: str) -> dict[str, Any]:
    if confirm != "清空排除表":
        raise ConfirmWordMismatch("确认词不匹配：请输入「清空排除表」")
    removed = state.images.clear_all_exclusions()
    return {"removed": removed, "hint": "墓碑已清除，重新扫描会把这些文件重新收录回来"}


# ---------- 断链体检 ----------
# 用户在资源管理器里改了名、挪了位置、或者直接删了文件，索引里那条记录还在：
# 列表缩略图裂、点开详情取不到原图、重跑识别必失败。以前项目只统计了一个
# missing_files 数字，没有任何地方看得到是哪几张、也没法清理。这里补上。


def list_broken(state: AppState, limit: int = 500) -> dict[str, Any]:
    dirs = {int(d["id"]): d for d in state.dirs.list()}
    broken: list[dict[str, Any]] = []
    scanned = 0
    for row in state.images.link_rows():
        scanned += 1
        path = Path(str(row["path"]))
        if path.is_file():
            continue
        dir_row = dirs.get(int(row["dir_id"]))
        broken.append(
            {
                "id": int(row["id"]),
                "path": str(row["path"]),
                "filename": str(row["filename"] or path.name),
                "dir_id": int(row["dir_id"]),
                "dir_path": str(dir_row["path"]) if dir_row is not None else None,
                "dir_registered": dir_row is not None,
                "hidden": bool(row["hidden"]),
                "flagged": bool(row["missing"]),
                "mtime": row["mtime"],
            }
        )
        if len(broken) >= limit:
            break
    return {"items": broken, "count": len(broken), "scanned": scanned}


def prune_broken(
    state: AppState, ids: list[int], exclude: bool = False, confirm: str = ""
) -> dict[str, Any]:
    """把断链条目从索引里摘掉。

    默认只删索引、不留墓碑——文件要是哪天挪回来，增量扫描会重新收录它。
    exclude=True 才登记排除（等于「以后都别再收录这张」）。
    """
    if not ids:
        raise ValidationAppError("未选择任何条目")
    if exclude and confirm != "清理并排除":
        raise ConfirmWordMismatch("确认词不匹配：请输入「清理并排除」")
    pruned: list[int] = []
    skipped: list[int] = []
    for image_id in ids:
        row = state.images.get(image_id) or state.images.get_hidden(image_id)
        if row is None:
            skipped.append(image_id)
            continue
        path = Path(str(row["path"]))
        if path.is_file():
            skipped.append(image_id)  # 文件回来了就别删，交给扫描刷新
            continue
        if exclude:
            state.images.exclude_path(int(row["dir_id"]), str(row["path"]))
        state.images.delete(image_id)
        pruned.append(image_id)
    if pruned:
        state.notice(
            "prune",
            f"清理断链条目 {len(pruned)} 条" + ("（并登记排除）" if exclude else ""),
            "info",
        )
    return {"pruned": pruned, "skipped": skipped, "count": len(pruned)}


def refresh_broken(state: AppState, dir_id: int) -> dict[str, Any]:
    """重新扫一遍目录：文件还在的会自动把 missing 标记抹掉。"""
    dir_row = state.dirs.get(dir_id)
    if dir_row is None:
        raise NotFoundError(f"目录不存在：{dir_id}")
    result = ingest.scan_directory(state, dir_id)
    result["dir_id"] = dir_id
    return result


def rename(state: AppState, image_id: int, new_name: str) -> dict[str, Any]:
    image = _image_or_404(state, image_id)
    new_name = str(new_name).strip()
    if not new_name or "/" in new_name or "\\" in new_name:
        raise ValidationAppError("文件名不合法")
    source = Path(str(image["path"]))
    target = source.with_name(new_name)
    if target.exists() and target != source:
        raise ValidationAppError(f"目标文件已存在：{new_name}")
    if not ingest.is_registered_path(state, str(source)):
        raise PathTraversalError("文件不在任何已登记目录内，拒绝操作")
    source.rename(target)
    state.images.update_any(
        image_id, path=str(target), filename=target.name, ext=target.suffix.lower()
    )
    state.images.sync_fts(image_id)
    return detail(state, image_id)


def move_to(state: AppState, image_id: int, target_dir_id: int) -> dict[str, Any]:
    image = _image_or_404(state, image_id)
    target = state.dirs.get(target_dir_id)
    if target is None:
        raise NotFoundError(f"目录不存在：{target_dir_id}")
    source = Path(str(image["path"]))
    if not ingest.is_registered_path(state, str(source)):
        raise PathTraversalError("文件不在任何已登记目录内，拒绝操作")
    dest = Path(str(target["path"])) / source.name
    if dest.exists():
        raise ValidationAppError(f"目标目录已存在同名文件：{source.name}")
    source.rename(dest)
    state.images.update_any(image_id, path=str(dest), dir_id=target_dir_id, filename=dest.name)
    state.images.sync_fts(image_id)
    return detail(state, image_id)


def snapshot_index(state: AppState) -> dict[str, Any]:
    """清空索引 / 注销目录之前先落一份完整快照到 data/backups/。

    这两个操作会把人工打的分类、描述、标签、评分、备注一起带走——AI 结果重跑还能
    回来，人一行行标的东西回不来。所以不留选择余地，直接先备份。
    """
    rows: list[dict[str, Any]] = []
    for row in state.images.link_rows():
        try:
            rows.append(detail(state, int(row["id"])))
        except NotFoundError:
            continue
    state.backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = state.backups_dir / f"index-{stamp}.json"
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(target), "count": len(rows)}


def export(state: AppState, ids: list[int], fmt: str = "json") -> dict[str, Any]:
    """导出元数据（json/csv）；可选按配置剥离 EXIF 后复制原图。"""
    if fmt not in ("json", "csv"):
        raise ValidationAppError("导出格式只支持 json / csv")
    rows = []
    for image_id in ids:
        try:
            rows.append(detail(state, image_id))
        except NotFoundError:
            continue
    state.exports_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if fmt == "json":
        target = state.exports_dir / f"export-{stamp}.json"
        target.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        target = state.exports_dir / f"export-{stamp}.csv"
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "path", "category", "description", "rating", "tags"])
        for row in rows:
            writer.writerow(
                [
                    row.get("id"),
                    row.get("path"),
                    row.get("category_manual") or row.get("category_ai") or "",
                    row.get("description_manual") or row.get("description_ai") or "",
                    row.get("rating", 0),
                    "|".join(row.get("manual_tags", [])),
                ]
            )
        target.write_text(buffer.getvalue(), encoding="utf-8-sig")

    if state.settings.get_bool("export_strip_exif", True):
        images_out = state.exports_dir / f"images-{stamp}"
        images_out.mkdir(parents=True, exist_ok=True)
        for row in rows:
            source = Path(str(row.get("path", "")))
            if source.is_file():
                try:
                    strip_exif(source, images_out / source.name)
                except (OSError, ValueError):
                    continue
    return {"path": str(target), "count": len(rows), "format": fmt}


def similar_images(state: AppState, image_id: int, limit: int) -> dict[str, Any]:
    from app.services import search_svc

    return search_svc.similar(state, image_id, limit)


def batch_op(
    state: AppState, op: str, ids: list[int], payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    if not ids:
        raise ValidationAppError("未选择任何图片")
    if op == "hide":
        return hide(state, ids)
    if op == "unhide":
        return unhide(state, ids)
    if op == "delete":
        results = []
        for image_id in ids:
            results.append(delete(state, image_id, "index"))
        return {"deleted": results}
    if op == "patch":
        done = [patch(state, image_id, payload or {})["id"] for image_id in ids]
        return {"patched": done}
    raise ValidationAppError(f"未知批量操作：{op}")
