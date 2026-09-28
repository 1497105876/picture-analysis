"""服务层装配：依赖注入容器（数据库、仓储、限速器、工作线程）。"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai.openai_client import OpenAIChatClient, OpenAIEmbedClient, OpenAIVisionClient
from app.ai.protocol import ChatClient, EmbedClient, VisionClient
from app.domain.rate_limit import RateConfig, SlidingWindowLimiter
from app.services.runner import JobRunner
from app.services.settings_svc import ProfileStore, SettingsService
from app.storage.catalog_repo import CatalogRepo
from app.storage.db import Database
from app.storage.dirs_repo import DirectoriesRepo
from app.storage.entities_repo import EntitiesRepo
from app.storage.images_repo import ImagesRepo
from app.storage.jobs_repo import JobsRepo
from app.storage.search_repo import SearchRepo
from app.storage.stats_repo import SettingsRepo, StatsRepo

DEFAULT_MODELS: dict[str, str] = {
    "vision": "gpt-4o-mini",
    "embed": "text-embedding-3-small",
    "chat": "gpt-4o-mini",
}
_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1", "[::1]")


def _today() -> str:
    # 与 now_iso()（UTC）保持同一时区，否则日预算统计恒为 0
    return time.strftime("%Y-%m-%d", time.gmtime())


@dataclass
class AppDeps:
    data_dir: Path
    root_dir: Path
    vision: VisionClient | None = None
    embed: EmbedClient | None = None
    chat: ChatClient | None = None
    clock: Callable[[], float] = time.monotonic
    start_workers: bool = True
    today: Callable[[], str] = _today


class AppState:
    def __init__(self, deps: AppDeps) -> None:
        self.deps = deps
        self.data_dir = deps.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.thumbs_dir = self.data_dir / "thumbs"
        self.trash_dir = self.data_dir / "trash"
        self.exports_dir = self.data_dir / "exports"
        self.db = Database(self.data_dir / "library.db")
        self.dirs = DirectoriesRepo(self.db)
        self.images = ImagesRepo(self.db)
        self.search = SearchRepo(self.db)
        self.catalog = CatalogRepo(self.db)
        self.entities = EntitiesRepo(self.db)
        self.jobs = JobsRepo(self.db)
        self.settings_repo = SettingsRepo(self.db)
        self.stats = StatsRepo(self.db)
        self.catalog.seed_categories()
        self.profiles = ProfileStore(deps.root_dir / ".env")
        self.settings = SettingsService(self, self.settings_repo, self.profiles)
        rate = RateConfig(
            per_minute=int(self.settings.get("rate_limit_per_minute", 20)),
            min_interval=float(self.settings.get("min_interval_seconds", 3.0)),
        )
        self.limiter = SlidingWindowLimiter(rate, deps.clock)
        self.runner = JobRunner(self)
        self._vision_client: OpenAIVisionClient | None = None
        self._embed_client: OpenAIEmbedClient | None = None
        self._chat_client: OpenAIChatClient | None = None
        self._vision_sig: tuple[str, str, str] | None = None
        self._embed_sig: tuple[str, str, str] | None = None
        self._chat_sig: tuple[str, str, str] | None = None
        self._started = False

    # ---------- 生命周期 ----------

    def start(self) -> None:
        if self._started:
            return
        self.jobs.reset_running()
        if self.deps.start_workers:
            self.runner.start()
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self.runner.stop()
        for client in (self._vision_client, self._embed_client, self._chat_client):
            if client is not None:
                client.close()
        self.db.close()
        self._started = False

    # ---------- AI 客户端解析（档案绑定 + 无密钥零外发） ----------

    def _resolve_profile(self, usage: str) -> tuple[str, str, str] | None:
        profile = self.settings.resolved_profile(usage)
        if profile is None:
            return None
        base_url = str(profile.get("base_url", "")).strip()
        if not base_url:
            return None
        api_key = str(profile.get("api_key", "") or "")
        host = base_url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        if not api_key and host not in _LOCAL_HOSTS:
            return None  # 远程端点无密钥：零外发，识图队列暂停并提示
        model = self.settings.model_for(usage) or DEFAULT_MODELS.get(usage, "")
        return base_url, api_key, model

    def get_vision(self) -> VisionClient | None:
        if self.deps.vision is not None:
            return self.deps.vision
        sig = self._resolve_profile("vision")
        if sig is None:
            self._vision_client = None
            self._vision_sig = None
            return None
        if sig != self._vision_sig:
            if self._vision_client is not None:
                self._vision_client.close()
            self._vision_client = OpenAIVisionClient(sig[0], sig[1], sig[2])
            self._vision_sig = sig
        return self._vision_client

    def get_embed(self) -> EmbedClient | None:
        if self.deps.embed is not None:
            return self.deps.embed
        sig = self._resolve_profile("embed")
        if sig is None:
            self._embed_client = None
            self._embed_sig = None
            return None
        if sig != self._embed_sig:
            if self._embed_client is not None:
                self._embed_client.close()
            self._embed_client = OpenAIEmbedClient(sig[0], sig[1], sig[2])
            self._embed_sig = sig
        return self._embed_client

    def get_chat(self) -> ChatClient | None:
        if self.deps.chat is not None:
            return self.deps.chat
        sig = self._resolve_profile("chat")
        if sig is None:
            self._chat_client = None
            self._chat_sig = None
            return None
        if sig != self._chat_sig:
            if self._chat_client is not None:
                self._chat_client.close()
            self._chat_client = OpenAIChatClient(sig[0], sig[1], sig[2])
            self._chat_sig = sig
        return self._chat_client

    # ---------- 便捷访问 ----------

    def setting(self, key: str, default: Any = None) -> Any:
        return self.settings.get(key, default)

    def notice(self, kind: str, message: str, level: str = "info") -> None:
        self.settings_repo.notice(kind, message, level)
