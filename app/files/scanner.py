"""目录扫描：只遍历用户手动登记的目录。"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from app.files.media import IMAGE_EXTS


@dataclass(frozen=True)
class ScanOptions:
    recursive: bool = True
    extensions: frozenset[str] = frozenset(IMAGE_EXTS)
    exclude_globs: tuple[str, ...] = ()


def iter_files(root: Path, options: ScanOptions) -> Iterator[Path]:
    """遍历登记目录；未登记/不可达目录由调用方拒绝，这里只管过滤规则。"""
    if not root.is_dir():
        return
    if options.recursive:
        candidates = (p for p in root.rglob("*") if p.is_file())
    else:
        candidates = (p for p in root.iterdir() if p.is_file())
    for path in candidates:
        if path.suffix.lower() not in options.extensions:
            continue
        relative = str(path.relative_to(root)).replace("\\", "/")
        if any(fnmatch.fnmatch(relative, pattern) for pattern in options.exclude_globs):
            continue
        yield path


def estimate(root: Path, options: ScanOptions) -> dict[str, int]:
    count = 0
    total_bytes = 0
    for path in iter_files(root, options):
        try:
            total_bytes += path.stat().st_size
        except OSError:
            continue
        count += 1
    return {"count": count, "bytes": total_bytes}
