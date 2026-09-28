"""组装 Release 目录并打 zip（无部署交付物）。"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"


def version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


def main() -> None:
    name = f"picture-analysis-{version()}"
    stage = RELEASE / name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    keep_files = [
        "server.py",
        "README.md",
        ".env.example",
        "pyproject.toml",
        "start.bat",
        "start.sh",
    ]
    keep_dirs = ["app", "docs"]
    for file_name in keep_files:
        src = ROOT / file_name
        if src.exists():
            shutil.copy2(src, stage / file_name)
    for dir_name in keep_dirs:
        src = ROOT / dir_name
        if src.exists():
            shutil.copytree(
                src,
                stage / dir_name,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
    lock = ROOT / "requirements.lock"
    if lock.exists():
        shutil.copy2(lock, stage / lock.name)

    frontend_dist = ROOT / "frontend" / "dist"
    if frontend_dist.exists():
        shutil.copytree(
            frontend_dist,
            stage / "app" / "static",
            dirs_exist_ok=True,
        )

    zip_path = RELEASE / f"{name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(RELEASE))
    shutil.rmtree(stage)
    print(f"package ok: {zip_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
