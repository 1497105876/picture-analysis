"""入库服务：目录登记校验、增量扫描、md5 认回、消失标记、截图轮询。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.domain.errors import DirAlreadyRegistered, DirNotFoundError, ValidationAppError
from app.files import scanner
from app.files.media import MAX_PIXELS, MediaInfo, extract, is_under, make_thumbnail
from app.files.scanner import ScanOptions
from app.services import rules_svc

if TYPE_CHECKING:
    from app.services.state import AppState

DEFAULT_EXTS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"})
AVG_TOKENS_PER_IMAGE = 900


def _options(state: AppState, dir_row: dict[str, Any]) -> ScanOptions:
    exts = [str(e).lower() for e in state.settings.get_list("default_extensions")]
    profile_excludes = dir_row.get("profile", {}).get("exclude_globs", [])
    excludes = [
        *[str(g) for g in state.settings.get_list("exclude_globs")],
        *[str(g) for g in profile_excludes],
    ]
    return ScanOptions(
        recursive=bool(dir_row["recursive"]),
        extensions=frozenset(exts) if exts else DEFAULT_EXTS,
        exclude_globs=tuple(excludes),
    )


def normalize_path(raw: str) -> Path:
    try:
        return Path(raw).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise ValidationAppError(f"路径不可用：{raw}") from exc


def _validate_no_overlap(state: AppState, path: Path) -> None:
    for existing in state.dirs.list():
        other = Path(str(existing["path"]))
        try:
            path.relative_to(other)
            raise DirAlreadyRegistered(f"与已登记目录重叠（子目录）：{other}")
        except ValueError:
            pass
        try:
            other.relative_to(path)
            raise DirAlreadyRegistered(f"与已登记目录重叠（父目录）：{path}")
        except ValueError:
            pass


def register_directory(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    raw = str(payload.get("path", "")).strip()
    if not raw:
        raise ValidationAppError("目录路径不能为空")
    path = normalize_path(raw)
    if not path.exists() or not path.is_dir():
        raise DirNotFoundError(f"目录不存在或不可访问：{path}")
    existing = next((d for d in state.dirs.list() if str(d["path"]) == str(path)), None)
    if existing is not None:
        raise DirAlreadyRegistered(f"目录已登记：{path}")
    _validate_no_overlap(state, path)
    dir_id = state.dirs.add(
        str(path),
        recursive=bool(payload.get("recursive", True)),
        privacy=bool(payload.get("privacy", False)),
        ocr_policy=str(payload.get("ocr_policy", "auto")),
        watcher=bool(payload.get("watcher", False)),
        source=str(payload.get("source", "manual")),
    )
    return get_directory(state, dir_id)


def unregister_directory(state: AppState, dir_id: int) -> dict[str, Any]:
    dir_row = get_directory(state, dir_id)
    removed = state.images.delete_by_dir(dir_id)
    state.dirs.remove(dir_id)
    return {"dir_id": dir_id, "path": dir_row["path"], "removed_index": removed}


def get_directory(state: AppState, dir_id: int) -> dict[str, Any]:
    row = state.dirs.get(dir_id)
    if row is None:
        raise DirNotFoundError(f"目录不存在：{dir_id}")
    return row


def list_directories(state: AppState) -> list[dict[str, Any]]:
    result = []
    for row in state.dirs.list():
        counts = state.images.ids_by_dir(int(row["id"]))
        item = dict(row)
        item["image_count"] = len(counts[0])
        item["hidden_count"] = len(counts[1])
        result.append(item)
    return result


def estimate_directory(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """导入向导：登记前先给张数 / 耗时 / token 预算预估（不落库不入索引）。"""
    raw = str(payload.get("path", "")).strip()
    if not raw:
        raise ValidationAppError("目录路径不能为空")
    path = normalize_path(raw)
    if not path.exists() or not path.is_dir():
        raise DirNotFoundError(f"目录不存在或不可访问：{path}")
    options = ScanOptions(
        recursive=bool(payload.get("recursive", True)),
        extensions=frozenset(
            {str(e).lower() for e in state.settings.get_list("default_extensions")}
        )
        or DEFAULT_EXTS,
        exclude_globs=tuple(str(g) for g in state.settings.get_list("exclude_globs")),
    )
    stats = scanner.estimate(path, options)
    count = int(stats["count"])
    rate = max(1, int(state.settings.get("rate_limit_per_minute", 20)))
    interval = max(float(state.settings.get("min_interval_seconds", 3.0)), 60.0 / rate)
    est_tokens = count * AVG_TOKENS_PER_IMAGE
    limit = int(state.settings.get("daily_token_limit", 0))
    used = state.images.tokens_today(state.deps.today())
    registered: int | None = None
    overlap: str | None = None
    for existing in state.dirs.list():
        if str(existing["path"]) == str(path):
            registered = int(existing["id"])
            break
    if registered is None:
        try:
            _validate_no_overlap(state, path)
        except DirAlreadyRegistered as exc:
            overlap = str(exc)
    return {
        "path": str(path),
        "count": count,
        "bytes": int(stats["bytes"]),
        "est_tokens": est_tokens,
        "est_minutes": round(count * interval / 60.0, 1),
        "daily_token_limit": limit,
        "tokens_today": used,
        "tokens_left": (limit - used) if limit else None,
        "within_budget": (est_tokens <= (limit - used)) if limit else True,
        "registered_id": registered,
        "overlap": overlap,
        "phases": ["phase-1 扫描入库（不调用 AI）", "phase-2 识别（分批排队，可随时暂停）"],
    }


def _queue_analyze(state: AppState, image_id: int, priority: int = 0) -> int:
    state.images.update_any(image_id, analysis_state="queued")
    return state.jobs.enqueue(
        "analyze", image_id=image_id, priority=priority, payload={"redo": False}
    )


def ingest_file(
    state: AppState, dir_row: dict[str, Any], path: Path, *, seen: set[str]
) -> tuple[int | None, str]:
    """单文件入库：md5 身份（移动认回 / 同内容并存新行）。返回 (id, 动作)。"""
    dir_id = int(dir_row["id"])
    rel = str(path)
    existing = state.images.find_by_path(dir_id, rel)
    if existing is not None:
        seen.add(rel)
        try:
            current_mtime = float(path.stat().st_mtime)
        except OSError:
            return int(existing["id"]), "unchanged"
        if abs(current_mtime - float(existing["mtime"])) > 0.001 or existing["missing"]:
            try:
                info = extract(path)
            except (OSError, ValueError) as exc:
                state.notice("scan-skip", f"无法读取，已跳过：{rel}（{exc}）", "warning")
                return int(existing["id"]), "skipped"
            state.images.update(
                int(existing["id"]),
                mtime=info.mtime,
                bytes=info.bytes,
                dhash=info.dhash,
                width=info.width,
                height=info.height,
                exif_taken_at=info.exif_taken_at,
                dominant_color=info.dominant_color,
                missing=0,
            )
            return int(existing["id"]), "updated"
        return int(existing["id"]), "unchanged"

    from app.files.media import file_md5

    md5 = file_md5(path)
    seen.add(rel)
    candidates = state.images.find_by_md5(md5)
    moved = [c for c in candidates if c["path"] != rel and not Path(str(c["path"])).is_file()]
    same_content = [c for c in candidates if c["path"] != rel and Path(str(c["path"])).is_file()]
    if moved and not same_content:
        target = moved[0]
        try:
            moved_info: MediaInfo | None = extract(path)
        except (OSError, ValueError):
            moved_info = None
        state.images.update(
            int(target["id"]),
            path=rel,
            filename=path.name,
            dir_id=dir_id,
            mtime=float(path.stat().st_mtime),
            bytes=int(path.stat().st_size),
            missing=0,
            **(
                {
                    "dhash": moved_info.dhash,
                    "width": moved_info.width,
                    "height": moved_info.height,
                    "exif_taken_at": moved_info.exif_taken_at,
                    "dominant_color": moved_info.dominant_color,
                }
                if moved_info is not None
                else {}
            ),
        )
        return int(target["id"]), "rebound"

    try:
        info = extract(path)
    except (OSError, ValueError) as exc:
        state.notice("scan-skip", f"无法读取，已跳过：{rel}（{exc}）", "warning")
        return None, "skipped"
    image_id = state.images.insert(
        {
            "dir_id": dir_id,
            "path": rel,
            "filename": path.name,
            "ext": path.suffix.lower(),
            "md5": md5,
            "dhash": info.dhash,
            "width": info.width,
            "height": info.height,
            "bytes": info.bytes,
            "mtime": info.mtime,
            "exif_taken_at": info.exif_taken_at,
            "dominant_color": info.dominant_color,
        }
    )
    try:
        make_thumbnail(path, state.thumbs_dir, str(image_id))
    except (OSError, ValueError) as exc:
        state.notice("thumb-skip", f"缩略图生成失败：{rel}（{exc}）", "warning")
    rules_svc.apply_phase(state, state.images.get(image_id) or {}, "pre")
    # dhash 为空 = 超出防解压炸弹上限、只读了文件头；再兜底一层显式像素数判断
    oversized = (not info.dhash) or bool(
        info.width and info.height and info.width * info.height > MAX_PIXELS
    )
    if oversized:
        state.images.update_any(image_id, analysis_state="skipped")
        state.notice("oversize", f"图片尺寸过大，已入库但跳过 AI 识图：{rel}", "warning")
    elif not dir_row.get("offline") and not dir_row.get("frozen"):
        _queue_analyze(state, image_id, priority=10)
    return image_id, "added"


def scan_directory(state: AppState, dir_id: int) -> dict[str, Any]:
    """增量扫描：只读登记目录。消失文件标 missing 不删，mtime 变更重提取。"""
    dir_row = get_directory(state, dir_id)
    if dir_row["offline"]:
        raise DirNotFoundError(f"目录已离线：{dir_row['path']}")
    path = Path(str(dir_row["path"]))
    if not path.is_dir():
        state.dirs.update(dir_id, offline=1)
        state.notice("offline", f"目录不可达，已标记离线：{path}", "warning")
        raise DirNotFoundError(f"目录不可达：{path}")
    if dir_row["frozen"]:
        return {"dir_id": dir_id, "skipped": "frozen", "added": 0, "updated": 0}

    options = _options(state, dir_row)
    seen: set[str] = set()
    added = updated = rebound = skipped = 0
    for file_path in scanner.iter_files(path, options):
        try:
            _, action = ingest_file(state, dir_row, file_path, seen=seen)
        except Exception as exc:  # 单文件异常绝不阻塞整目录扫描
            seen.add(str(file_path))
            state.notice(
                "scan-skip",
                f"扫描出错，已跳过：{file_path.name}（{type(exc).__name__}: {exc}）",
                "warning",
            )
            skipped += 1
            continue
        if action == "added":
            added += 1
        elif action == "updated":
            updated += 1
        elif action == "rebound":
            rebound += 1
        elif action == "skipped":
            skipped += 1
    missing = state.images.mark_missing(dir_id, seen)
    state.dirs.update(dir_id, last_scanned_at=time.strftime("%Y-%m-%dT%H:%M:%S+00:00"))
    return {
        "dir_id": dir_id,
        "added": added,
        "updated": updated,
        "rebound": rebound,
        "missing": missing,
        "skipped": skipped,
        "scanned": len(seen),
    }


def poll_watchers(state: AppState) -> int:
    """截图自动导入：30 秒轮询 watcher 目录，仅新图入库并排队识别。"""
    if not state.settings.get_bool("watcher_enabled", False):
        return 0
    new_total = 0
    for dir_row in state.dirs.list():
        if not dir_row["watcher"] or dir_row["offline"] or dir_row["frozen"]:
            continue
        try:
            result = scan_directory(state, int(dir_row["id"]))
        except DirNotFoundError:
            continue
        new_total += int(result.get("added", 0))
    if new_total and state.settings.get_bool("notify_watch", False):
        state.notice("watch", f"截图自动导入：新增 {new_total} 张", "info")
    return new_total


def export_upload(state: AppState, filename: str, content: bytes) -> dict[str, Any]:
    """截图/剪贴板导入：复制进 data/uploads 并登记为来源目录。"""
    uploads = state.data_dir / "uploads"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in filename)[:80]
    dest = uploads / stamp / (safe or "image.jpg")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    dir_row = next((d for d in state.dirs.list() if str(d["path"]) == str(dest.parent)), None)
    if dir_row is None:
        dir_row = register_directory(
            state,
            {"path": str(dest.parent), "recursive": False, "source": "upload"},
        )
    scan_directory(state, int(dir_row["id"]))
    return {"path": str(dest), "dir_id": dir_row["id"]}


def is_registered_path(state: AppState, file_path: str) -> bool:
    return any(is_under(Path(file_path), Path(str(d["path"]))) for d in state.dirs.list())
