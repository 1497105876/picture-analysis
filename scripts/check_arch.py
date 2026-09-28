"""架构守护（CI 门禁）：依赖方向 + 直读契约存在性。

规则来源：docs/architecture.md 第 3.1/6 章、docs/design.md 第 2 章。
用法：python scripts/check_arch.py   （违规退出码 1）
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"

# 领域层（app/domain）禁止的外部依赖：必须保持纯逻辑、零 I/O
DOMAIN_FORBIDDEN_MODULES = {
    "sqlite3",
    "httpx",
    "fastapi",
    "uvicorn",
    "numpy",
    "PIL",
    "requests",
    "socket",
}
# 领域层禁止依赖的本项目内层（只能被上层依赖，不能反向）
DOMAIN_FORBIDDEN_APP_PREFIXES = ("app.api", "app.services", "app.storage", "app.ai", "app.files")
# API 层禁止直连基础设施，必须经 services
API_FORBIDDEN_APP_PREFIXES = ("app.storage", "app.ai", "app.files")

# 直读契约必须出现在 design.md 中的对象（破坏性变更必须同步文档）
REQUIRED_CONTRACT_MARKERS = (
    "SQLite 直读契约",
    "CREATE VIEW v_images",
    "CREATE VIEW v_analysis",
    "CREATE VIEW v_tags",
    "mode=ro",
)


def iter_py_files(package: str) -> list[Path]:
    target = APP / package
    if not target.is_dir():
        return []
    return sorted(target.rglob("*.py"))


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def check_layer(
    package: str,
    forbidden_modules: set[str],
    forbidden_app_prefixes: tuple[str, ...],
    label: str,
    errors: list[str],
) -> None:
    for path in iter_py_files(package):
        for name in sorted(imports_of(path)):
            if name in forbidden_modules:
                errors.append(f"{label} {path.relative_to(ROOT)} 禁止 import 模块 `{name}`")
            if name.startswith(forbidden_app_prefixes):
                errors.append(f"{label} {path.relative_to(ROOT)} 禁止依赖内层 `{name}`")


def check_contract(errors: list[str]) -> None:
    design = ROOT / "docs" / "design.md"
    if not design.is_file():
        errors.append("缺少 docs/design.md（直读契约文档）")
        return
    text = design.read_text(encoding="utf-8")
    for marker in REQUIRED_CONTRACT_MARKERS:
        if marker not in text:
            errors.append(f"docs/design.md 缺少直读契约要素：`{marker}`")
    if not (ROOT / "docs" / "examples" / "direct_read.sql").is_file():
        errors.append("缺少 docs/examples/direct_read.sql（随库直读示例）")


def main() -> int:
    errors: list[str] = []
    check_layer(
        "domain", DOMAIN_FORBIDDEN_MODULES, DOMAIN_FORBIDDEN_APP_PREFIXES, "[领域纯净]", errors
    )
    check_layer("api", set(), API_FORBIDDEN_APP_PREFIXES, "[分层]", errors)
    check_contract(errors)

    if errors:
        print("架构检查未通过：", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("架构检查通过：依赖方向 + 直读契约完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
