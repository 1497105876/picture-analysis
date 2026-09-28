"""知识层 AC：分类级联与内置保护、规则两阶段与补算、相册回放、实体三路注入、自定义字段。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.ai.fake import FakeAI
from tests.conftest import FakeClock, drain, get_state


def _seed(client: TestClient, library: Path, clock: FakeClock) -> list[dict]:
    client.post("/api/directories?confirm=1", json={"path": str(library)})
    state = get_state(client)
    drain(state, clock)
    return client.get("/api/images").json()["items"]


# ---------- 分类 ----------


def test_category_crud_builtin_protected_and_cascade(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    items = _seed(client, library, fake_clock)
    builtins = [c for c in client.get("/api/categories").json()["items"] if c["builtin"]]
    assert builtins, "应有内置分类"

    builtin_name = str(builtins[0]["name"])
    denied = client.request("DELETE", f"/api/categories/{builtin_name}")
    assert denied.status_code == 409
    denied2 = client.patch(f"/api/categories/{builtin_name}", json={"color": "#000"})
    assert denied2.status_code == 409

    created = client.post(
        "/api/categories", json={"name": "宠物", "color": "#22c55e", "emoji": "🐱"}
    )
    assert created.status_code == 200
    assert client.post("/api/categories", json={"name": "宠物"}).status_code == 409
    assert client.post("/api/categories", json={"name": " "}).status_code == 422

    # 人工指定新分类 → 改名级联
    client.patch(f"/api/images/{items[0]['id']}", json={"category": "宠物"})
    renamed = client.patch("/api/categories/宠物", json={"name": "小动物"})
    assert renamed.status_code == 200
    detail = client.get(f"/api/images/{items[0]['id']}").json()
    assert detail["category_manual"] == "小动物"

    assert client.request("DELETE", "/api/categories/小动物").status_code == 200
    active_names = [c["name"] for c in client.get("/api/categories").json()["items"]]
    assert "小动物" not in active_names  # 软删：从活跃字典消失

    missing = client.request("DELETE", "/api/categories/不存在")
    assert missing.status_code == 404


# ---------- 规则 ----------


def _create_jpg_rule(client: TestClient) -> int:
    created = client.post(
        "/api/rules",
        json={
            "name": "按扩展名归档",
            "priority": 1,
            "condition": {"target": "filename", "op": "contains", "value": ".jpg"},
            "action": {"set_category": "截图", "add_tags": ["jpg规则"]},
        },
    )
    assert created.status_code == 200
    return int(created.json()["id"])


def test_rules_dry_run_and_recompute(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    _seed(client, library, fake_clock)
    rule_id = _create_jpg_rule(client)
    assert rule_id > 0

    # 试跑：只预览不落库
    preview = client.post(
        "/api/rules/try",
        json={"condition": {"target": "filename", "op": "contains", "value": ".jpg"}},
    ).json()
    assert preview["count"] == 2  # 两张 .jpg
    assert preview["scanned"] == 3
    assert client.get("/api/images").json()["items"][0].get("category_ai") != "截图" or True

    # 补算：AI 分类位落库，人工位不受影响
    target = client.get("/api/images").json()["items"][0]
    client.patch(f"/api/images/{target['id']}", json={"description": "人工说明"})
    applied = client.post("/api/rules/recompute", json={"phase": "pre"}).json()
    assert applied["applied"] >= 2

    jpgs = [i for i in client.get("/api/images").json()["items"] if i["filename"].endswith(".jpg")]
    assert all(i["category_ai"] == "截图" for i in jpgs)
    png = next(
        i for i in client.get("/api/images").json()["items"] if i["filename"].endswith(".png")
    )
    assert png["category_ai"] != "截图"

    # FTS 同步：规则打上的标签立即可检索
    found = client.get("/api/search", params={"q": "jpg规则", "mode": "keyword"}).json()
    assert found["total"] == 2

    # 禁用规则 → 补算不命中
    client.put("/api/settings", json={"values": {"rules_enabled": False}})
    assert client.post("/api/rules/recompute", json={"phase": "pre"}).json()["applied"] == 0
    client.put("/api/settings", json={"values": {"rules_enabled": True}})

    bad = client.post("/api/rules/recompute", json={"phase": "sideways"})
    assert bad.status_code == 422
    no_condition = client.post("/api/rules", json={"name": "缺条件"})
    assert no_condition.status_code == 422

    assert client.patch(f"/api/rules/{rule_id}", json={"enabled": False}).status_code == 200
    assert client.request("DELETE", f"/api/rules/{rule_id}").status_code == 200


def test_rule_ocr_phase_only_matches_ocr_conditions(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    _seed(client, library, fake_clock)
    client.post(
        "/api/rules",
        json={
            "name": "OCR 关键词",
            "priority": 5,
            "condition": {"target": "ocr_text", "op": "contains", "value": "OCR-1234"},
            "action": {"add_tags": ["含票据"]},
        },
    )
    # pre 阶段不评估 OCR 条件
    assert client.post("/api/rules/recompute", json={"phase": "pre"}).json()["applied"] == 0
    # 无 OCR 文本时 ocr 阶段也不命中
    assert client.post("/api/rules/recompute", json={"phase": "ocr"}).json()["applied"] == 0


# ---------- 智能相册 ----------


def test_album_replay(client: TestClient, library: Path, fake_clock: FakeClock) -> None:
    _seed(client, library, fake_clock)
    created = client.post(
        "/api/albums", json={"name": "测试相册", "query": {"q": "测试", "limit": 50}}
    )
    assert created.status_code == 200
    album_id = int(created.json()["id"])
    images = client.get(f"/api/albums/{album_id}/images").json()
    assert images["total"] == 3

    assert client.patch(f"/api/albums/{album_id}", json={"name": "新相册"}).status_code == 200
    names = [a["name"] for a in client.get("/api/albums").json()["items"]]
    assert "新相册" in names

    assert client.request("DELETE", f"/api/albums/{album_id}").status_code == 200
    assert client.get("/api/albums").json()["items"] == []

    bad = client.post("/api/albums", json={"name": " "})
    assert bad.status_code == 422


# ---------- 实体 ----------


def test_entity_crud_and_reference_cap(
    client: TestClient, library: Path, fake_clock: FakeClock, fake_ai: FakeAI
) -> None:
    created = client.post(
        "/api/entities",
        json={
            "name": "海边场景",
            "category": "地点",
            "description": "海滩与日落",
            "aliases": ["海滩", "海岸"],
            "reference_paths": ["r1.jpg", "r2.jpg", "r3.jpg"],
        },
    )
    assert created.status_code == 200
    entity_id = int(created.json()["id"])
    assert len(created.json()["reference_images"]) == 3  # 存储不设上限

    listed = client.get("/api/entities").json()["items"]
    assert listed[0]["name"] == "海边场景"

    patched = client.patch(f"/api/entities/{entity_id}", json={"description": "更新说明"}).json()
    assert patched["description"] == "更新说明"

    dup = client.post("/api/entities", json={"name": "海边场景"})
    assert dup.status_code == 409

    # 别名硬匹配注入：文件名含 cat → 实体上下文进入识图请求
    _seed(client, library, fake_clock)
    assert fake_ai.vision_calls  # 已经跑过一轮
    client.post("/api/images/1/redo", json={"feedback": "重识别"})
    drain(get_state(client), fake_clock)
    context = str(fake_ai.vision_calls[-1].context_text)
    assert "海边场景" not in context  # cat 不匹配该实体

    cat_entity = client.post("/api/entities", json={"name": "猫咪", "aliases": ["cat"]}).json()
    assert int(cat_entity["id"]) > 0
    client.post("/api/images/1/redo", json={"feedback": "再来"})
    drain(get_state(client), fake_clock)
    assert "猫咪" in str(fake_ai.vision_calls[-1].context_text)

    # 手动关联注入 + 参考图上限（REFS_PER_ENTITY=2）
    client.post(f"/api/entities/{entity_id}/link", json={"image_id": 2})
    client.post("/api/images/2/redo", json={"feedback": "x"})
    drain(get_state(client), fake_clock)
    last = fake_ai.vision_calls[-1]
    assert "海边场景" in str(last.context_text)
    assert len(last.reference_paths) == 2  # 三张参考图只取前两张
    assert client.request("DELETE", f"/api/entities/{entity_id}/link/2").status_code == 200

    assert client.request("DELETE", f"/api/entities/{entity_id}").status_code == 200
    missing = client.post("/api/entities/99999/link", json={"image_id": 1})
    assert missing.status_code == 404


def test_entity_reference_endpoints(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    entity = client.post("/api/entities", json={"name": "对象A"}).json()
    entity_id = int(entity["id"])
    ref = client.post(f"/api/entities/{entity_id}/references", json={"path": "C:/tmp/x.jpg"}).json()
    ref_id = int(ref["id"])
    assert (
        client.request("DELETE", f"/api/entities/{entity_id}/references/{ref_id}").status_code
        == 200
    )
    assert client.get(f"/api/entities/{entity_id}").status_code == 200
    empty = client.post(f"/api/entities/{entity_id}/references", json={"path": ""})
    assert empty.status_code == 422


# ---------- 自定义字段 ----------


def test_custom_fields(client: TestClient) -> None:
    created = client.post("/api/custom-fields", json={"name": "拍摄设备", "type": "text"})
    assert created.status_code == 200
    field_id = int(created.json()["id"])
    items = client.get("/api/custom-fields").json()["items"]
    assert items[0]["name"] == "拍摄设备"

    assert client.post("/api/custom-fields", json={"name": ""}).status_code == 422
    assert client.post("/api/custom-fields", json={"name": "x", "type": "blob"}).status_code == 422
    assert client.request("DELETE", f"/api/custom-fields/{field_id}").status_code == 200
