"""检索 AC：混合/关键词/向量模式、筛选、cursor、同义词、历史、降级、以图搜图。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.ai.fake import FakeAI
from app.services.state import AppState
from tests.conftest import FakeClock, drain, get_state


def _seed(client: TestClient, library: Path, clock: FakeClock) -> AppState:
    client.post("/api/directories?confirm=1", json={"path": str(library)})
    state = get_state(client)
    drain(state, clock)
    return state


def test_keyword_search_and_filters(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    _seed(client, library, fake_clock)
    found = client.get("/api/search", params={"q": "测试", "mode": "keyword"}).json()
    assert found["total"] == 3
    assert found["mode"] == "keyword"
    assert found["timings"]["keyword_ms"] >= 0

    # 分类筛选（FakeAI 全部落在「其他」内置分类）
    by_cat = client.get("/api/images", params={"category": "其他"}).json()
    assert by_cat["total"] == 3
    miss = client.get("/api/images", params={"category": "风景"}).json()
    assert miss["total"] == 0

    # 排序字段校验
    bad = client.get("/api/images", params={"sort": "evil"})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"


def test_vector_and_hybrid_modes(client: TestClient, library: Path, fake_clock: FakeClock) -> None:
    _seed(client, library, fake_clock)
    # 与嵌入文本完全一致 → 余弦必为 1.0（FakeAI 按文本确定性生成向量）
    vector = client.get(
        "/api/search", params={"q": "一张测试图片\n测试\n图片", "mode": "vector"}
    ).json()
    assert vector["mode"] == "vector"
    assert vector["total"] == 3
    assert vector["timings"]["vector_ms"] >= 0

    hybrid = client.get("/api/search", params={"q": "测试", "mode": "hybrid"}).json()
    assert hybrid["total"] == 3
    assert all(item.get("score") is not None for item in hybrid["items"])


def test_embedding_failure_degrades_to_keyword(
    client: TestClient, library: Path, fake_clock: FakeClock, fake_ai: FakeAI
) -> None:
    _seed(client, library, fake_clock)
    fake_ai.embed_failures = 99
    result = client.get("/api/search", params={"q": "测试"}).json()
    assert result["degraded"] is True
    assert result["total"] == 3  # 关键词链路不受影响


def test_cursor_pagination_no_skip_no_repeat(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    _seed(client, library, fake_clock)
    first = client.get("/api/images", params={"limit": 2, "sort": "id", "order": "asc"}).json()
    assert len(first["items"]) == 2
    assert first["has_more"] is True
    second = client.get(
        "/api/images",
        params={"limit": 2, "sort": "id", "order": "asc", "cursor": first["next_cursor"]},
    ).json()
    ids = [item["id"] for item in first["items"]] + [item["id"] for item in second["items"]]
    assert ids == sorted(ids)
    assert len(set(ids)) == 3


def test_synonyms_and_term_weights(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    _seed(client, library, fake_clock)
    # 人工打标：一张图打「海岸」，同义词组把「海边」映射过来
    target = client.get("/api/images").json()["items"][0]
    client.patch(f"/api/images/{target['id']}", json={"tags": ["海岸"]})
    put = client.put("/api/synonyms", json={"group": "水域", "terms": ["海边", "海岸"]})
    assert put.status_code == 200
    hit = client.get("/api/search", params={"q": "海边", "mode": "keyword"}).json()
    assert hit["total"] == 1
    assert hit["items"][0]["id"] == target["id"]

    weight = client.put("/api/term-weights", json={"term": "测试", "weight": 3.0})
    assert weight.status_code == 200
    assert client.get("/api/term-weights").json()["weights"]["测试"] == 3.0

    # 只进不出等于写错一次就永久留在检索里，这里守住「能删」
    assert client.delete("/api/synonyms", params={"group": "水域"}).status_code == 200
    assert client.get("/api/synonyms").json()["groups"] == {}
    gone = client.get("/api/search", params={"q": "海边", "mode": "keyword"}).json()
    assert gone["total"] == 0, "同义词组删掉后不该再互相展开"

    assert client.delete("/api/term-weights", params={"term": "测试"}).status_code == 200
    assert client.get("/api/term-weights").json()["weights"] == {}

    assert client.delete("/api/synonyms", params={"group": "不存在"}).status_code >= 400
    assert client.delete("/api/term-weights", params={"term": "没设过"}).status_code >= 400
    assert client.delete("/api/synonyms").status_code >= 400


def test_search_history_on_off_clear(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    _seed(client, library, fake_clock)
    client.get("/api/search", params={"q": "测试"})
    client.get("/api/search", params={"q": "海边"})
    history = client.get("/api/search/history").json()["items"]
    assert "测试" in history and "海边" in history

    client.put("/api/settings", json={"values": {"search_history_enabled": False}})
    client.get("/api/search", params={"q": "新词"})
    assert "新词" not in client.get("/api/search/history").json()["items"]

    client.request("DELETE", "/api/search/history")
    assert client.get("/api/search/history").json()["items"] == []


def test_similar_by_image(client: TestClient, library: Path, fake_clock: FakeClock) -> None:
    state = _seed(client, library, fake_clock)
    # 独立计算目标图向量后请求相似图
    image_id = client.get("/api/images").json()["items"][0]["id"]
    state.images.set_vector(
        image_id,
        "fake",
        state.deps.embed.embed(["测试图片"]),  # type: ignore[union-attr]
    )
    result = client.get(f"/api/images/{image_id}/similar").json()
    assert "items" in result
    assert all(item["id"] != image_id for item in result["items"])


def test_hidden_bypass_params_rejected(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    _seed(client, library, fake_clock)
    for key in ("hidden", "include_hidden", "with_hidden", "show_hidden"):
        response = client.get("/api/images", params={key: "true"})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "HIDDEN_NOT_BYPASSABLE"
        found = client.get("/api/search", params={"q": "测试", key: "1"})
        assert found.status_code == 400
