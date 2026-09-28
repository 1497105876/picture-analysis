"""任务队列 AC：限速暂停恢复、预算、缺密钥零外发、OCR 按需、隐私/敏感守门、退避与死亡。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.ai.fake import FakeAI
from app.ai.protocol import VisionOutput
from tests.conftest import FakeClock, get_state


def _register(client: TestClient, library: Path, **payload: object) -> dict:
    body = {"path": str(library), **payload}
    response = client.post("/api/directories?confirm=1", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _run_until_idle(state, clock: FakeClock, limit: int = 120) -> None:
    for _ in range(limit):
        wait = state.runner.step()
        if wait > 0:
            clock.advance(wait)
            continue
        counts = state.jobs.counts()
        if not counts.get("pending") and not counts.get("running"):
            break


def test_rate_limit_pauses_then_resumes(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    _register(client, library)
    state = get_state(client)

    # 第一条占用名额，第二条撞最小间隔（3 秒）→ 暂停并返回等待
    first = state.runner.step()
    assert first == 0.0
    wait = state.runner.step()
    assert wait > 0
    paused = state.jobs.rows(state="paused")
    assert paused, "应当出现限速暂停的任务"
    assert (paused[0]["payload"] or {}).get("pause") == "rate"

    # 拨动时钟后自动恢复，直至队列清空
    _run_until_idle(state, fake_clock)
    counts = state.jobs.counts()
    assert counts.get("pending", 0) == 0
    assert counts.get("paused", 0) == 0
    assert counts.get("succeeded", 0) >= 4  # 3 analyze + 3 embed - 已合并统计
    images = state.db.query("SELECT analysis_state FROM images")
    assert all(row["analysis_state"] == "done" for row in images)


def test_daily_budget_pauses_and_next_day_recovers(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    _register(client, library)
    state = get_state(client)
    client.put("/api/settings", json={"values": {"daily_token_limit": 10}})
    state.images.add_token_usage(1, "vision", "fake-model", 100, 0)

    wait = state.runner.step()
    assert wait == 0.0
    paused = state.jobs.rows(state="paused")
    assert paused and (paused[0]["payload"] or {}).get("pause") == "budget"
    assert "100/10" in str(paused[0]["error"])
    assert state.runner.resume_paused() == 0  # 额度未恢复则持续暂停

    # 次日（用量清零）→ 自动恢复并跑完
    state.db.execute("DELETE FROM token_usage")
    assert state.runner.resume_paused() >= 1
    _run_until_idle(state, fake_clock)
    assert state.jobs.counts().get("paused", 0) == 0
    assert state.jobs.counts().get("succeeded", 0) >= 4


def test_missing_api_key_pauses_zero_external_then_recovers(
    client_nokey: TestClient, library: Path, fake_clock: FakeClock, fake_ai: FakeAI
) -> None:
    state = get_state(client_nokey)
    assert state.get_vision() is None  # 未注入、无档案 → 零外发
    _register(client_nokey, library)

    state.runner.step()
    paused = state.jobs.rows(state="paused")
    assert paused and (paused[0]["payload"] or {}).get("pause") == "no_key"
    assert fake_ai.vision_calls == []  # 确实零调用
    notices = client_nokey.get("/api/notices").json()["items"]
    assert any(
        "密钥" in str(n.get("message", "")) or "Key" in str(n.get("message", "")) for n in notices
    )

    # 补上服务后恢复
    state.deps.vision = fake_ai
    state.deps.embed = fake_ai
    _run_until_idle(state, fake_clock)
    assert state.jobs.counts().get("paused", 0) == 0
    assert len(fake_ai.vision_calls) == 3


def test_ocr_on_demand_single_pass(
    client: TestClient, library: Path, fake_clock: FakeClock, fake_ai: FakeAI
) -> None:
    fake_ai.vision_handler = lambda req: VisionOutput(
        category="文档", description="发票", ai_tags=["发票"], elements=["文字"], has_text=True
    )
    _register(client, library)
    state = get_state(client)
    _run_until_idle(state, fake_clock)

    assert len(fake_ai.vision_calls) == 3  # 每图仅一次识图
    assert len(fake_ai.ocr_calls) == 3  # has_text → 追加 OCR
    assert state.images.get_ocr_text(1) == "示例文字 OCR-1234"
    row = state.db.query_one("SELECT has_text FROM images WHERE id=1")
    assert row is not None and row["has_text"] == 1


def test_ocr_policy_off_skips_even_with_text(
    client: TestClient, library: Path, fake_clock: FakeClock, fake_ai: FakeAI
) -> None:
    fake_ai.vision_handler = lambda req: VisionOutput(
        category="文档", description="票据", ai_tags=["票据"], elements=[], has_text=True
    )
    _register(client, library, ocr_policy="off")
    state = get_state(client)
    _run_until_idle(state, fake_clock)
    assert fake_ai.ocr_calls == []
    assert state.jobs.counts().get("succeeded", 0) >= 4


def test_privacy_directory_never_sent(
    client: TestClient, library: Path, fake_clock: FakeClock, fake_ai: FakeAI
) -> None:
    _register(client, library, privacy=True)
    state = get_state(client)
    _run_until_idle(state, fake_clock)
    assert fake_ai.vision_calls == []
    states = {row["analysis_state"] for row in state.db.query("SELECT analysis_state FROM images")}
    assert states == {"skipped"}


def test_sensitive_word_blocks_external(
    client: TestClient,
    library: Path,
    fake_clock: FakeClock,
    fake_ai: FakeAI,
    image_factory,
) -> None:
    secret = library / "绝密报告.jpg"
    image_factory(secret, (9, 9, 9))
    client.put("/api/settings", json={"values": {"sensitive_words": "绝密"}})
    _register(client, library)
    state = get_state(client)
    _run_until_idle(state, fake_clock)
    # 仅敏感词命中的文件被跳过，其余正常识图
    assert len(fake_ai.vision_calls) == 3
    skipped = state.db.query("SELECT filename FROM images WHERE analysis_state='skipped'")
    assert [row["filename"] for row in skipped] == ["绝密报告.jpg"]


def test_frozen_directory_skipped(
    client: TestClient, library: Path, fake_clock: FakeClock, fake_ai: FakeAI
) -> None:
    _register(client, library)
    state = get_state(client)
    state.dirs.update(1, frozen=1)
    _run_until_idle(state, fake_clock)
    assert fake_ai.vision_calls == []
    states = {row["analysis_state"] for row in state.db.query("SELECT analysis_state FROM images")}
    assert states == {"skipped"}


def test_ai_unavailable_backoff_then_dead(
    client: TestClient, library: Path, fake_clock: FakeClock, fake_ai: FakeAI
) -> None:
    fake_ai.vision_failures = 99
    _register(client, library)
    state = get_state(client)
    job_id = int(next(r for r in state.jobs.rows() if r.get("image_id") == 1)["id"])

    for attempt in range(1, 4):
        fake_clock.advance(5.0)  # 越过最小间隔，确保撞到的是退避而非限速
        wait = state.runner.step()
        job = state.jobs.get(job_id)
        assert job is not None
        if attempt < 3:
            assert job["state"] == "pending" and wait > 0  # 退避重排
            assert int(job["attempts"]) == attempt
            state.jobs.transition(job_id, "pending", retry_at=0.0)  # 模拟退避到期
        else:
            assert job["state"] == "dead"
    assert (
        state.db.query_one("SELECT analysis_state FROM images WHERE id=1")["analysis_state"]
        == "failed"
    )
    notices = client.get("/api/notices").json()["items"]
    assert any(n.get("kind") == "job-dead" for n in notices)


def test_non_ai_error_dead_immediately(
    client: TestClient, library: Path, fake_clock: FakeClock, fake_ai: FakeAI
) -> None:
    def boom(req):  # noqa: ANN001, ANN202
        raise ValueError("数据坏了")

    fake_ai.vision_handler = boom  # type: ignore[assignment]
    _register(client, library)
    state = get_state(client)
    wait = state.runner.step()
    assert wait == 0.0
    dead = state.jobs.rows(state="dead")
    assert dead and "数据坏了" in str(dead[0]["error"])


def test_embed_service_missing_degrades(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    _register(client, library)
    state = get_state(client)
    state.deps.embed = None  # 模拟未配置嵌入档案
    state.jobs.enqueue("embed", image_id=1, payload={})
    _run_until_idle(state, fake_clock)
    assert state.images.get_vector(1) is None  # 无嵌入服务 → 无向量但不报错
    embed_jobs = [j for j in state.jobs.rows() if j["type"] == "embed"]
    events = state.jobs.events(int(embed_jobs[-1]["id"]))
    assert any("语义检索降级" in str(e["message"]) for e in events)


def test_cancel_and_retry(client: TestClient, library: Path, fake_clock: FakeClock) -> None:
    _register(client, library)
    job_id = int(get_state(client).jobs.rows()[0]["id"])

    cancelled = client.post(f"/api/jobs/{job_id}/cancel").json()
    assert cancelled["state"] == "failed"
    retried = client.post(f"/api/jobs/{job_id}/retry").json()
    assert retried["state"] == "pending"

    missing = client.post("/api/jobs/99999/cancel")
    assert missing.status_code == 404


def test_scan_job_type(client: TestClient, library: Path, fake_clock: FakeClock) -> None:
    state = get_state(client)
    state.jobs.enqueue("scan", dir_id=1, payload={}, priority=100)  # 高优先级最先调度
    _register(client, library)
    assert state.runner.step() == 0.0
    row = state.db.query_one("SELECT state FROM jobs WHERE type='scan' ORDER BY id DESC")
    assert row is not None and row["state"] == "succeeded"


def test_image_deleted_mid_queue_succeeds(
    client: TestClient, library: Path, fake_clock: FakeClock
) -> None:
    _register(client, library)
    state = get_state(client)
    state.images.delete(1)
    _run_until_idle(state, fake_clock)
    counts = state.jobs.counts()
    assert counts.get("dead", 0) == 0
