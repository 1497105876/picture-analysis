"""管理 AC：人工优先不被覆盖、FTS 即时、隐藏物理分表、打回纠错、删除回收站、改名移动导出。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import FakeClock, drain, get_state


def _seed(client: TestClient, library: Path, clock: FakeClock) -> list[dict]:
    client.post("/api/directories?confirm=1", json={"path": str(library)})
    state = get_state(client)
    drain(state, clock)
    return client.get("/api/images").json()["items"]


def test_manual_overrides_never_clobbered(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    items = _seed(client, library, fake_clock)
    image_id = items[0]["id"]

    patched = client.patch(
        f"/api/images/{image_id}",
        json={
            "category": "风景",
            "description": "人工描述",
            "tags": ["我的标签"],
            "rating": 4,
            "favorite": True,
            "notes": "笔记",
        },
    ).json()
    assert patched["category_manual"] == "风景"
    assert patched["description_manual"] == "人工描述"
    assert patched["rating"] == 4
    assert "我的标签" in patched["manual_tags"]
    assert patched["correction_count"] >= 1

    # 再次打回重识别：AI 输出不得覆盖人工位
    client.post(f"/api/images/{image_id}/redo", json={"feedback": "这是风景照"})
    state = get_state(client)
    drain(state, fake_clock)
    detail = client.get(f"/api/images/{image_id}").json()
    assert detail["category_manual"] == "风景"
    assert detail["description_manual"] == "人工描述"
    assert detail["category_ai"] == "其他"  # AI 位照常更新但显示 COALESCE 人工优先
    assert detail["last_feedback"] == "这是风景照"
    assert detail["correction_count"] >= 2

    # FTS 即时更新：人工描述立即可检索
    found = client.get("/api/search", params={"q": "人工描述", "mode": "keyword"}).json()
    assert found["total"] == 1


def test_rating_validation(client: TestClient, library: Path, fake_clock: FakeClock) -> None:
    items = _seed(client, library, fake_clock)
    bad = client.patch(f"/api/images/{items[0]['id']}", json={"rating": 9})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"


def test_hide_moves_row_out_of_contract(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    items = _seed(client, library, fake_clock)
    image_id = items[0]["id"]
    assert client.post(f"/api/images/{image_id}/hide").json()["count"] == 1

    # 可见列表与 FTS 都不可见
    assert client.get("/api/images").json()["total"] == 2
    assert client.get("/api/search", params={"q": "测试"}).json()["total"] == 2

    # 隐藏区是唯一入口
    hidden = client.get("/api/hidden").json()
    assert hidden["total"] == 1
    assert hidden["items"][0]["id"] == image_id

    # 直读契约：v_images 不含隐藏行
    state = get_state(client)
    visible_ids = {int(r["id"]) for r in state.db.query("SELECT id FROM v_images")}
    assert image_id not in visible_ids

    # 识别备份照常（隐藏后仍可重识别）
    client.post(f"/api/images/{image_id}/redo", json={"feedback": "继续识别"})
    drain(state, fake_clock)
    detail = client.get(f"/api/images/{image_id}").json()
    assert detail["hidden"] is True
    assert detail["analysis_state"] == "done"

    # 恢复
    assert client.post(f"/api/images/{image_id}/unhide").json()["count"] == 1
    assert client.get("/api/images").json()["total"] == 3
    assert client.get("/api/hidden").json()["total"] == 0


def test_delete_index_and_source_with_confirm(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    items = _seed(client, library, fake_clock)
    target = items[0]
    path = Path(target["path"])

    # 源删除必须确认词正确
    wrong = client.request(
        "DELETE", f"/api/images/{target['id']}", params={"mode": "source", "confirm": "x"}
    )
    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "CONFIRM_WORD_MISMATCH"
    assert path.is_file()

    ok = client.request(
        "DELETE",
        f"/api/images/{target['id']}",
        params={"mode": "source", "confirm": path.name},
    )
    assert ok.status_code == 200
    assert not path.exists()
    assert path.parent.is_dir()  # 目录还在
    trash = client.get("/api/trash").json()["items"]
    assert len(trash) == 1

    # 索引删除（默认）
    second = items[1]
    gone = client.request("DELETE", f"/api/images/{second['id']}")
    assert gone.status_code == 200
    assert client.get(f"/api/images/{second['id']}").status_code == 404


def test_rename_move_and_batch(
    client: TestClient,
    library: Path,
    fake_clock: FakeClock,
    tmp_path: Path,
    image_factory: object,
) -> None:
    items = _seed(client, library, fake_clock)
    image_id = items[0]["id"]
    old_name = Path(items[0]["path"]).name

    renamed = client.post(f"/api/images/{image_id}/rename", json={"name": "重命名.jpg"}).json()
    assert renamed["filename"] == "重命名.jpg"
    assert not (library / old_name).exists()
    assert (library / "重命名.jpg").is_file()

    bad = client.post(f"/api/images/{image_id}/rename", json={"name": "../x.jpg"})
    assert bad.status_code == 422

    # 移动到另一个已登记目录
    other = tmp_path / "other"
    image_factory(other / "keep.jpg", (1, 2, 3))
    client.post("/api/directories?confirm=1", json={"path": str(other)})
    dirs = client.get("/api/directories").json()["items"]
    other_id = next(d["id"] for d in dirs if d["path"] == str(other.resolve()))
    moved = client.post(f"/api/images/{image_id}/move", json={"dir_id": other_id}).json()
    assert moved["dir_id"] == other_id

    # 批量隐藏
    batch = client.post(
        "/api/images/batch",
        json={"op": "hide", "ids": [items[1]["id"], items[2]["id"]]},
    ).json()
    assert batch["count"] == 2
    assert client.get("/api/hidden").json()["total"] == 2

    empty = client.post("/api/images/batch", json={"op": "hide", "ids": []})
    assert empty.status_code == 422


def test_export_json_and_csv(client: TestClient, library: Path, fake_clock: FakeClock) -> None:
    items = _seed(client, library, fake_clock)
    ids = [item["id"] for item in items]
    js = client.post("/api/export", json={"ids": ids, "format": "json"}).json()
    assert js["count"] == 3
    assert Path(js["path"]).is_file()
    csv_out = client.post("/api/export", json={"ids": ids, "format": "csv"}).json()
    assert Path(csv_out["path"]).read_text(encoding="utf-8-sig").count("\n") >= 3

    bad = client.post("/api/export", json={"ids": [], "format": "json"})
    assert bad.status_code == 422
    fmt = client.post("/api/export", json={"ids": ids, "format": "xml"})
    assert fmt.status_code == 422


def test_detail_includes_ai_artifacts(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    items = _seed(client, library, fake_clock)
    detail = client.get(f"/api/images/{items[0]['id']}").json()
    assert detail["analyses"]
    assert detail["ai_tags"]
    assert detail["elements"]
    assert detail["has_thumb"] is True
    thumb = client.get(f"/api/thumbs/{items[0]['id']}")
    assert thumb.status_code == 200
    assert thumb.headers["content-type"] == "image/jpeg"
    missing = client.get("/api/thumbs/99999")
    assert missing.status_code == 404
