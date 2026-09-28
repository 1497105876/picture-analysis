# 本地一键 CI：与 GitHub Actions 同序执行
# 用法：python scripts/ci.py [--skip-package]
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(title: str, cmd: list[str]) -> None:
    print(f"\n=== {title} ===", flush=True)
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print(f"\n[FAIL] {title}", file=sys.stderr)
        sys.exit(result.returncode)


def main() -> None:
    py = sys.executable
    run("ruff check", [py, "-m", "ruff", "check", "."])
    run("ruff format --check", [py, "-m", "ruff", "format", "--check", "."])
    run("mypy", [py, "-m", "mypy", "app", "server.py"])
    run("pytest", [py, "-m", "pytest", "--cov=app", "--cov-report=term-missing"])

    package_json = ROOT / "frontend" / "package.json"
    if package_json.exists() and shutil.which("npm"):
        run("frontend build", ["npm", "run", "build"])

    if "--skip-package" not in sys.argv:
        run("package", [py, "scripts/package.py"])
    print("\n[OK] 本地 CI 全绿")


if __name__ == "__main__":
    main()
