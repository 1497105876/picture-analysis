# 本地一键 CI：与 GitHub Actions 同序执行
# 用法：python scripts/ci.py [--skip-package]
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(title: str, cmd: list[str], *, cwd: Path | None = None) -> None:
    print(f"\n=== {title} ===", flush=True)
    result = subprocess.run(cmd, cwd=cwd or ROOT)
    if result.returncode != 0:
        print(f"\n[FAIL] {title}", file=sys.stderr)
        sys.exit(result.returncode)


def main() -> None:
    py = sys.executable
    run("ruff check", [py, "-m", "ruff", "check", "."])
    run("ruff format --check", [py, "-m", "ruff", "format", "--check", "."])
    run("mypy", [py, "-m", "mypy", "app", "server.py"])
    run("architecture check", [py, "scripts/check_arch.py"])
    run(
        "pytest",
        [
            py,
            "-m",
            "pytest",
            "--cov=app",
            "--cov-report=term-missing",
            "--cov-fail-under=80",
        ],
    )

    package_json = ROOT / "frontend" / "package.json"
    if package_json.exists() and shutil.which("npm"):
        # Windows 下 npm 是 .cmd 脚本，subprocess 不能直接启动，需经 cmd.exe
        shell = ["cmd", "/c"] if sys.platform == "win32" else []
        run("frontend npm ci", [*shell, "npm", "ci"], cwd=ROOT / "frontend")
        run("frontend build", [*shell, "npm", "run", "build"], cwd=ROOT / "frontend")

    if "--skip-package" not in sys.argv:
        run("package", [py, "scripts/package.py"])
    print("\n[OK] 本地 CI 全绿")


if __name__ == "__main__":
    main()
