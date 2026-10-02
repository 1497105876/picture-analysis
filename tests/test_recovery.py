"""可逆性 AC：删了要能恢复、断链要能看见并清理。

这两条是同一类坑：用户做了一个看起来无害的操作（只删索引 / 在资源管理器里挪文件），
结果数据单向消失、界面上连痕迹都看不到。这里守住「做错了能回头」的底线。
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import FakeClock, drain, get_state


def _seed(client: TestClient, library: Path, clock: FakeClock) -> list[dict]:
    client.post("/api/directories?confirm=1", json={"path": str(library)})
    drain(get_state(client), clock)
    return client.get("/api/images").json()["items"]


def test_delete_index_is_reversible(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    """「只删索引」留下的墓碑必须看得见、能一键恢复，不能是单向操作。"""
    items = _seed(client, library, fake_clock)
    target = items[0]
    image_id = target["id"]
    path = Path(target["path"])

    assert client.delete(f"/api/images/{image_id}?mode=index").json()["mode"] == "index"
    assert path.is_file(), "只删索引不该动磁盘上的源文件"

    # 墓碑可见
    listed = client.get("/api/excluded").json()
    assert listed["count"] == 1, "删完索引必须能在排除表里看到这条墓碑"
    row = listed["items"][0]
    assert row["exists"] is True and row["registered"] is True

    # 增量扫描不得把它收回来（排除表生效）
    state = get_state(client)
    dir_id = int(state.dirs.list()[0]["id"])
    client.post(f"/api/scan/{dir_id}", json={})
    drain(state, fake_clock)
    assert client.get("/api/images").json()["total"] == len(items) - 1
    assert client.get("/api/excluded").json()["count"] == 1, "扫描不该把墓碑吃掉"

    # 一键恢复：解除排除 + 立刻重新入库，不用再让用户去点扫描
    restored = client.post(f"/api/excluded/{row['id']}/restore", json={}).json()
    assert restored["action"] in ("added", "updated")
    assert client.get(f"/api/images/{restored['image_id']}").status_code == 200
    assert client.get("/api/excluded").json()["count"] == 0


def test_forget_exclusion_lets_scan_readopt(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    """只想「下次扫描再收录」时，移除记录即可，不必真的恢复。"""
    items = _seed(client, library, fake_clock)
    client.delete(f"/api/images/{items[0]['id']}?mode=index")
    row = client.get("/api/excluded").json()["items"][0]

    client.delete(f"/api/excluded/{row['id']}")
    assert client.get("/api/excluded").json()["count"] == 0

    state = get_state(client)
    client.post(f"/api/scan/{int(state.dirs.list()[0]['id'])}", json={})
    drain(state, fake_clock)
    paths = {i["path"] for i in client.get("/api/images").json()["items"]}
    assert row["path"] in paths, "解除排除后增量扫描应重新收录"


def test_clear_excluded_needs_confirm_word(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    items = _seed(client, library, fake_clock)
    client.delete(f"/api/images/{items[0]['id']}?mode=index")
    client.delete(f"/api/images/{items[1]['id']}?mode=index")

    assert client.delete("/api/excluded", params={"confirm": "随便写"}).status_code >= 400
    res = client.delete("/api/excluded", params={"confirm": "清空排除表"}).json()
    assert res["removed"] == 2
    assert client.get("/api/excluded").json()["count"] == 0


def test_restore_excluded_rejects_missing_file(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    """文件已经不在原位置时，恢复要给出能懂的解释，而不是静默失败。"""
    items = _seed(client, library, fake_clock)
    client.delete(f"/api/images/{items[0]['id']}?mode=index")
    row = client.get("/api/excluded").json()["items"][0]
    Path(row["path"]).unlink()

    res = client.post(f"/api/excluded/{row['id']}/restore", json={})
    assert res.status_code >= 400
    assert "已不在原位置" in res.json()["error"]["message"]

    # 仍留着墓碑，用户可以自己决定「移除记录」
    assert client.get("/api/excluded").json()["count"] == 1


def test_broken_links_are_visible_and_prunable(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    """在磁盘上删掉文件后，索引里的死链必须看得见、清得掉。"""
    items = _seed(client, library, fake_clock)
    victim = items[0]
    Path(victim["path"]).unlink()

    health = client.get("/api/health/broken").json()
    assert health["scanned"] == len(items)
    assert health["count"] == 1, "磁盘上没了的那张必须被体检抓出来"
    row = health["items"][0]
    assert row["id"] == victim["id"]
    assert row["dir_registered"] is True
    assert row["flagged"] is False, "还没重扫过，不该是 missing 标记，而是本次体检发现的"

    # 默认清理：只删索引，不留墓碑 → 文件挪回来还能被重新收录
    res = client.post("/api/health/prune", json={"ids": [row["id"]]}).json()
    assert res["count"] == 1 and res["skipped"] == []
    assert client.get("/api/excluded").json()["count"] == 0
    assert client.get(f"/api/images/{row['id']}").status_code == 404

    # 文件放回去 → 增量扫描重新收录（没留墓碑才会回来）
    (library / victim["filename"]).write_bytes(b"\xff\xd8\xff\xd9jpg")
    state = get_state(client)
    client.post(f"/api/scan/{int(state.dirs.list()[0]['id'])}", json={})
    drain(state, fake_clock)
    assert client.get("/api/health/broken").json()["count"] == 0


def test_prune_skips_files_that_came_back(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    """体检之后文件又回来了，清理时不能把它删掉。"""
    items = _seed(client, library, fake_clock)
    victim = items[0]
    Path(victim["path"]).unlink()
    row = client.get("/api/health/broken").json()["items"][0]

    Path(victim["path"]).write_bytes(b"\xff\xd8\xff\xd9jpg-back")
    res = client.post("/api/health/prune", json={"ids": [row["id"]]}).json()
    assert res["count"] == 0 and res["skipped"] == [row["id"]]
    assert client.get(f"/api/images/{row['id']}").status_code == 200


def test_prune_with_exclude_needs_confirm_word(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    items = _seed(client, library, fake_clock)
    Path(items[0]["path"]).unlink()
    row = client.get("/api/health/broken").json()["items"][0]

    bad = client.post(
        "/api/health/prune", json={"ids": [row["id"]], "exclude": True, "confirm": "不对"}
    )
    assert bad.status_code >= 400

    ok = client.post(
        "/api/health/prune",
        json={"ids": [row["id"]], "exclude": True, "confirm": "清理并排除"},
    ).json()
    assert ok["count"] == 1
    assert client.get("/api/excluded").json()["count"] == 1
    state = get_state(client)
    client.post(f"/api/scan/{int(state.dirs.list()[0]['id'])}", json={})
    drain(state, fake_clock)
    assert client.get("/api/excluded").json()["count"] == 1, "登记排除后扫描不再收录"


def test_rescan_dir_clears_broken(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    """重扫目录是「文件还在、只是名字对不上」时的正确出路。"""
    items = _seed(client, library, fake_clock)
    state = get_state(client)
    dir_id = state.dirs.list()[0]["id"]

    # 先让扫描把消失的文件标成 missing，再重扫验证能回到干净状态
    Path(items[0]["path"]).unlink()
    client.post(f"/api/scan/{dir_id}", json={})
    drain(state, fake_clock)
    flagged = client.get("/api/health/broken").json()["items"]
    assert flagged and flagged[0]["flagged"] is True

    Path(items[0]["path"]).write_bytes(b"\xff\xd8\xff\xd9jpg")
    client.post(f"/api/health/rescan/{dir_id}", json={})
    assert client.get("/api/health/broken").json()["count"] == 0
