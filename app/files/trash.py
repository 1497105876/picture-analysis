"""回收站：删源文件必须可找回，绝不直接物理删除。"""

from __future__ import annotations

import time
from pathlib import Path


def move_to_trash(source: Path, trash_dir: Path) -> Path:
    trash_dir.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)
    target = trash_dir / f"{stamp}_{source.name}"
    counter = 1
    while target.exists():
        target = trash_dir / f"{stamp}_{counter}_{source.name}"
        counter += 1
    source.replace(target)
    return target


def restore(trash_path: Path, original_path: Path) -> None:
    original_path.parent.mkdir(parents=True, exist_ok=True)
    trash_path.replace(original_path)
