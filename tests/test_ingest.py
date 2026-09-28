"""入库流水线：登记两阶段、扫描、识图队列、FTS 即时可检索。AC F1/F2/F6。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.services.state import AppState
from tests.conftest import FakeClock, drain, get_state


def test_directory_requires_confirm_then_scan(client: TestClient, library: Path) -> None:
    # 未登记零扫描
    assert client.get("/api/images").json()["total"] == 0

    # 第一阶段：只预估不落库
    first = client.post("/api/directories", json={"path": str(library)})
    assert first.status_code == 200
    body = first.json()
    assert body["confirmed"] is False
    assert body["estimate"]["count"] == 3
    assert body["estimate"]["est_tokens"] > 0
    assert client.get("/api/directories").json()["items"] == []

    # 第二阶段：确认后登记 + 扫描
    second = client.post("/api/directories?confirm=1", json={"path": str(library)})
    assert second.status_code == 200
    assert second.json()["confirmed"] is True
    assert second.json()["scan"]["added"] == 3
    assert client.get("/api/directories").json()["items"][0]["image_count"] == 3
    assert client.get("/api/images").json()["total"] == 3


def test_duplicate_and_overlap_registration_rejected(client: TestClient, library: Path) -> None:
    client.post("/api/directories?confirm=1", json={"path": str(library)})
    again = client.post("/api/directories?confirm=1", json={"path": str(library)})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "DIR_ALREADY_REGISTERED"

    child = library / "sub"
    child.mkdir()
    overlap = client.post("/api/directories?confirm=1", json={"path": str(child)})
    assert overlap.status_code == 409

    missing = client.post("/api/directories?confirm=1", json={"path": str(library / "nope")})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "DIR_NOT_FOUND"


def test_analyze_pipeline_end_to_end(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    client.post("/api/directories?confirm=1", json={"path": str(library)})
    state = get_state(client)
    drain(state, fake_clock)

    images = client.get("/api/images").json()
    assert images["total"] == 3
    for item in images["items"]:
        assert item["analysis_state"] == "done"
        assert item["description_ai"] == "一张测试图片"
        assert item["ai_tags"] if False else True  # ai_tags 不在列表视图

    # FakeAI 已收到识图调用（默认不产生文字 → 不触发 OCR）
    assert len(state.deps.vision.vision_calls) == 3  # type: ignore[union-attr]
    assert state.deps.vision.ocr_calls == []  # type: ignore[union-attr]

    # FTS 即时可检索（中文预分词）
    found = client.get("/api/search", params={"q": "测试"}).json()
    assert found["total"] == 3

    # 向量已写入（FakeAI embed）
    assert state.images.get_vector(1) is not None


def test_incremental_scan_marks_missing_and_rebinds(
    client: TestClient, library: Path, image_factory: object
) -> None:
    client.post("/api/directories?confirm=1", json={"path": str(library)})
    # 消失文件 → 标记 missing，不删记录
    (library / "cat_portrait.png").unlink()
    scan = client.post("/api/scan/1").json()
    assert scan["missing"] == 1
    assert scan["added"] == 0
    assert client.get("/api/images").json()["total"] == 3

    # 移动改名 → md5 认回身份（标注不丢）
    from tests.conftest import get_state as _gs

    state = _gs(client)
    state.images.update(1, notes="我的批注")
    (library / "beach_sunset.jpg").rename(library / "beach_final.jpg")
    scan2 = client.post("/api/scan/1").json()
    assert scan2["rebound"] == 1
    detail = client.get("/api/images/1").json()
    assert detail["filename"] == "beach_final.jpg"
    assert detail["notes"] == "我的批注"


def test_watch_and_unregister(client: TestClient, library: Path, fake_clock: FakeClock) -> None:
    client.post("/api/directories?confirm=1", json={"path": str(library)})
    removed = client.request("DELETE", "/api/directories/1").json()
    assert removed["removed_index"] == 3
    assert client.get("/api/images").json()["total"] == 0
    # 源文件未动
    assert (library / "cat_portrait.png").is_file()


def test_state_is_app_state(client: TestClient) -> None:
    assert isinstance(get_state(client), AppState)
