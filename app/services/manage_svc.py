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
        }
    )
    return item


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
    """删除：mode=index 只删索引；mode=source 源文件进回收站（可找回）。"""
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
                (image_id, str(source), str(trash_path), time.strftime("%Y-%m-%dT%H:%M:%SZ")),
            )
    state.images.delete(image_id)
    return {"image_id": image_id, "mode": mode}


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
