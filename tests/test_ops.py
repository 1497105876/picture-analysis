"""运维 AC：仪表盘、重复聚类、清理建议、回收站还原、任务列表与清理、通知、上传、危险操作。"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import FakeClock, drain, get_state


def _seed(client: TestClient, library: Path, clock: FakeClock) -> list[dict]:
    client.post("/api/directories?confirm=1", json={"path": str(library)})
    drain(get_state(client), clock)
    return client.get("/api/images").json()["items"]


def test_dashboard_and_system_stats(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    _seed(client, library, fake_clock)
    dash = client.get("/api/stats/dashboard").json()
    assert dash["dirs"] == 1
    assert "jobs" in dash and "tokens_total" in dash
    system = client.get("/api/stats/system").json()
    assert "db_bytes" in system and "free_bytes" in system


def test_exact_duplicates_by_md5(client: TestClient, library: Path, fake_clock: FakeClock) -> None:
    # 同字节不同名 → md5 完全重复
    shutil.copy2(library / "beach_sunset.jpg", library / "beach_copy.jpg")
    _seed(client, library, fake_clock)
    groups = client.get("/api/stats/duplicates").json()["groups"]
    assert groups and any(len(g["images"]) >= 2 for g in groups), "应识别出完全重复组"

    perceptual = client.get(
        "/api/stats/duplicates", params={"perceptual": 1, "threshold": 4}
    ).json()["groups"]
    assert perceptual, "相同 dhash 应聚为感知重复"


def test_cleanup_suggestions_after_missing(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    _seed(client, library, fake_clock)
    (library / "cat_portrait.png").unlink()
    client.post("/api/scan/1")
    cleanup = client.get("/api/stats/cleanup").json()
    assert cleanup["missing_files"] == 1
    assert any("消失" in s for s in cleanup["suggestions"])
    assert cleanup["visible"] == 3


def test_trash_restore_and_clear(client: TestClient, library: Path, fake_clock: FakeClock) -> None:
    items = _seed(client, library, fake_clock)
    target = items[0]
    path = Path(target["path"])

    client.request(
        "DELETE",
        f"/api/images/{target['id']}",
        params={"mode": "source", "confirm": path.name},
    )
    trash = client.get("/api/trash").json()["items"]
    assert len(trash) == 1
    assert not path.exists()

    wrong = client.request("DELETE", "/api/trash", params={"confirm": "nope"})
    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "CONFIRM_WORD_MISMATCH"

    restored = client.post(f"/api/trash/{trash[0]['id']}/restore").json()
    assert restored["restored"].endswith(path.name)
    assert path.is_file()
    assert client.get("/api/trash").json()["items"] == []

    # 再删一次 → 清空
    client.request(
        "DELETE",
        f"/api/images/{target['id']}",
        params={"mode": "source", "confirm": path.name},
    )
    cleared = client.request("DELETE", "/api/trash", params={"confirm": "清空回收站"}).json()
    assert cleared["removed"] == 1
    assert client.get("/api/trash").json()["items"] == []


def test_jobs_list_events_clear(client: TestClient, library: Path, fake_clock: FakeClock) -> None:
    _seed(client, library, fake_clock)
    jobs = client.get("/api/jobs").json()
    assert "counts" in jobs or "items" in jobs

    rows = get_state(client).jobs.rows(state="succeeded")
    job_id = int(rows[0]["id"])
    events = client.get(f"/api/jobs/{job_id}/events").json()["items"]
    assert events, "成功任务应有事件记录"

    pending_count = client.get("/api/jobs", params={"state": "succeeded"}).json()
    assert pending_count  # 过滤可用

    cleared = client.request("DELETE", "/api/jobs").json()
    assert cleared["cleared"] >= 1


def test_notices_and_logs(client: TestClient) -> None:
    state = get_state(client)
    state.notice("demo", "测试通知", "warning")
    items = client.get("/api/notices").json()["items"]
    assert any(i["kind"] == "demo" for i in items)
    assert client.request("DELETE", "/api/notices").json()["cleared"] is True
    assert client.get("/api/notices").json()["items"] == []

    logs = client.get("/api/logs").json()
    assert "lines" in logs and "notices" in logs and "level" in logs


def test_upload_import(client: TestClient, tmp_path: Path) -> None:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (32, 32), (5, 6, 7)).save(buffer, format="PNG")
    response = client.post(
        "/api/upload",
        files={"file": ("shot.png", buffer.getvalue(), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert Path(body["path"]).is_file()
    assert body["dir_id"] > 0

    empty = client.post("/api/upload", files={"file": ("x.jpg", b"", "image/jpeg")})
    assert empty.status_code == 422


def test_clear_index_danger_requires_confirm(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    _seed(client, library, fake_clock)
    wrong = client.post("/api/danger/clear-index", json={"confirm": "清"})
    assert wrong.status_code == 400
    assert wrong.json()["error"]["code"] == "CONFIRM_WORD_MISMATCH"
    assert client.get("/api/images").json()["total"] == 3

    ok = client.post("/api/danger/clear-index", json={"confirm": "清空索引"}).json()
    assert ok["removed"] == 3
    assert client.get("/api/images").json()["total"] == 0
    assert (library / "cat_portrait.png").is_file()  # 源文件不动
