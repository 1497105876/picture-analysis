"""应用装配：路由注册、静态托管、生命周期钩子在此集中。"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app import __version__
from app.api.deps import register_error_handlers
from app.api.routers import assistant, knowledge, library, ops, system
from app.api.routers import settings as settings_router
from app.services.state import AppDeps, AppState

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
DIST_DIR = ROOT / "frontend" / "dist"

ROUTERS = (
    system.router,
    library.router,
    knowledge.router,
    assistant.router,
    ops.router,
    settings_router.router,
)


def _default_deps() -> AppDeps:
    data_dir = Path(os.environ.get("PA_DATA_DIR", str(ROOT / "data")))
    return AppDeps(data_dir=data_dir, root_dir=ROOT)


def create_app(deps: AppDeps | None = None) -> FastAPI:
    resolved = deps if deps is not None else _default_deps()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        state = AppState(resolved)
        app.state.pa = state
        state.start()
        try:
            yield
        finally:
            state.stop()

    app = FastAPI(
        title="picture-analysis",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    register_error_handlers(app)
    for router in ROUTERS:
        app.include_router(router)

    static_dir = DIST_DIR if (DIST_DIR / "index.html").is_file() else STATIC_DIR

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        """SPA 回退：静态文件存在则直出，否则回退 index.html（防目录穿越）。"""
        index = static_dir / "index.html"
        if full_path:
            candidate = (static_dir / full_path).resolve()
            try:
                candidate.relative_to(static_dir.resolve())
            except ValueError:
                return FileResponse(index)
            if candidate.is_file():
                return FileResponse(candidate)
        if index.is_file():
            return FileResponse(index)
        return FileResponse(static_dir)

    return app
