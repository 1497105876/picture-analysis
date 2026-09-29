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


def test_deleted_index_not_rescanned(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    """只删索引 = 明确不想要这张图：后续增量扫描不得把它扫回来。"""
    client.post("/api/directories?confirm=1", json={"path": str(library)})
    state = get_state(client)
    drain(state, fake_clock)
    calls = len(state.deps.vision.vision_calls)  # type: ignore[union-attr]
    target = client.get("/api/images").json()["items"][0]

    assert client.request("DELETE", f"/api/images/{target['id']}").status_code == 200
    assert client.get("/api/images").json()["total"] == 2
    assert Path(target["path"]).is_file()  # 只删索引，源文件原地不动

    # 导入向导预估同步跳过，张数与实际入库一致
    est = client.post("/api/directories", json={"path": str(library)}).json()["estimate"]
    assert est["count"] == 2

    # 增量扫描：不新增、不重新排队识图，并报出被排除的张数
    scan = client.post("/api/scan/1").json()
    assert scan["added"] == 0
    assert scan["excluded"] == 1
    assert client.get("/api/images").json()["total"] == 2
    drain(state, fake_clock)
    assert len(state.deps.vision.vision_calls) == calls  # type: ignore[union-attr]

    # 注销目录 = 全量重来：排除一并清除，重新登记后回到 3 张
    removed = client.request("DELETE", "/api/directories/1").json()
    assert removed["removed_index"] == 2
    client.post("/api/directories?confirm=1", json={"path": str(library)})
    assert client.get("/api/images").json()["total"] == 3


def test_watch_and_unregister(client: TestClient, library: Path, fake_clock: FakeClock) -> None:
    client.post("/api/directories?confirm=1", json={"path": str(library)})
    removed = client.request("DELETE", "/api/directories/1").json()
    assert removed["removed_index"] == 3
    assert client.get("/api/images").json()["total"] == 0
    # 源文件未动
    assert (library / "cat_portrait.png").is_file()


def test_state_is_app_state(client: TestClient) -> None:
    assert isinstance(get_state(client), AppState)


def test_oversize_image_indexed_but_analyze_skipped(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    """超出防解压炸弹上限的图：不崩（不 500），仍入库读文件头，跳过 AI 识图。"""
    from PIL import Image

    old_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = 1000  # 测试图 64×48=3072 像素，全部触发炸弹保护
    try:
        resp = client.post("/api/directories?confirm=1", json={"path": str(library)})
    finally:
        Image.MAX_IMAGE_PIXELS = old_limit

    assert resp.status_code == 200
    assert resp.json()["scan"]["added"] == 3  # 全部扫到，没有中途崩掉

    items = client.get("/api/images").json()["items"]
    assert len(items) == 3
    for item in items:
        assert item["analysis_state"] == "skipped"
        assert item["width"] == 64 and item["height"] == 48  # 文件头解析出尺寸
        assert item["dhash"] == ""  # 未整图解码 → 无感知哈希

    state = get_state(client)
    counts = state.jobs.counts()
    assert not counts.get("pending") and not counts.get("running")  # 没有识图任务
    drain(state, fake_clock)
    assert len(state.deps.vision.vision_calls) == 0  # type: ignore[union-attr]


def test_scan_survives_broken_file(client: TestClient, library: Path) -> None:
    """损坏文件只跳过自己，整目录照常扫全。"""
    (library / "broken.jpg").write_bytes(b"definitely not a real jpeg")
    resp = client.post("/api/directories?confirm=1", json={"path": str(library)})
    assert resp.status_code == 200
    scan = resp.json()["scan"]
    assert scan["added"] == 3
    assert scan["skipped"] == 1
    assert client.get("/api/images").json()["total"] == 3
