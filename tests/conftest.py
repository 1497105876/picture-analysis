"""共享夹具：FakeAI 注入、可拨时钟、临时图库、图片工厂、任务排水。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.ai.fake import FakeAI
from app.main import create_app
from app.services.state import AppDeps, AppState


class FakeClock:
    """可拨号的单调时钟（限速器注入用）。"""

    def __init__(self) -> None:
        self.t = 1_000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def fake_ai() -> FakeAI:
    return FakeAI()


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


def build_deps(root: Path, fake: FakeAI, clock: FakeClock, **overrides: Any) -> AppDeps:
    deps = AppDeps(
        data_dir=root / "data",
        root_dir=root,
        vision=fake,
        embed=fake,
        chat=fake,
        clock=clock,
        start_workers=False,
    )
    for key, value in overrides.items():
        setattr(deps, key, value)
    return deps


@pytest.fixture
def state(tmp_path: Path, fake_ai: FakeAI, fake_clock: FakeClock) -> Iterator[AppState]:
    deps = build_deps(tmp_path, fake_ai, fake_clock)
    app_state = AppState(deps)
    app_state.start()
    try:
        yield app_state
    finally:
        app_state.stop()


@pytest.fixture
def client(tmp_path: Path, fake_ai: FakeAI, fake_clock: FakeClock) -> Iterator[TestClient]:
    deps = build_deps(tmp_path, fake_ai, fake_clock)
    app = create_app(deps)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_nokey(tmp_path: Path, fake_ai: FakeAI, fake_clock: FakeClock) -> Iterator[TestClient]:
    """不注入任何 AI 客户端：验证缺密钥零外发与暂停恢复。"""
    deps = build_deps(tmp_path, None, fake_clock)  # type: ignore[arg-type]
    deps.vision = None
    deps.embed = None
    deps.chat = None
    app = create_app(deps)
    with TestClient(app) as test_client:
        yield test_client


def get_state(test_client: TestClient) -> AppState:
    return test_client.app.state.pa  # type: ignore[no-any-return]


@pytest.fixture
def image_factory() -> Callable[..., Path]:
    """生成真实可解析的小图片（不同颜色 → 不同 md5）。"""

    def factory(
        path: Path,
        color: tuple[int, int, int] = (200, 40, 40),
        size: tuple[int, int] = (64, 48),
        with_text: bool = False,
    ) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", size, color)
        if with_text:
            draw = ImageDraw.Draw(image)
            draw.text((4, 4), "Invoice 2024 No.88", fill=(255, 255, 255))
        image.save(path)
        return path

    return factory


@pytest.fixture
def library(tmp_path: Path, image_factory: Callable[..., Path]) -> Path:
    lib = tmp_path / "library"
    image_factory(lib / "beach_sunset.jpg", (10, 120, 220))
    image_factory(lib / "cat_portrait.png", (240, 200, 60))
    image_factory(lib / "receipt_march.jpg", (250, 250, 250), with_text=True)
    return lib


def drain(state: AppState, clock: FakeClock | None = None, limit: int = 80) -> int:
    """把队列跑到空（限速等待自动拨表）。返回执行的任务数。"""
    done = 0
    for _ in range(limit):
        wait = state.runner.step()
        if wait > 0 and clock is not None:
            clock.advance(wait)
            continue
        counts = state.jobs.counts()
        if wait == 0 and not counts.get("pending") and not counts.get("running"):
            break
        done += 1
    return done
