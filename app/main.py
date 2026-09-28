"""应用装配：路由注册、静态托管、生命周期钩子在此集中。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

__version__ = "0.1.0"

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(
        title="picture-analysis",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        """存活探测：CI 与监控的冒烟端点。"""
        return {"status": "ok", "version": __version__}

    if STATIC_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str) -> FileResponse:
            """SPA 回退：非 /api 路径一律返回 index.html。"""
            index = STATIC_DIR / "index.html"
            return FileResponse(index if index.exists() else STATIC_DIR)

    return app
