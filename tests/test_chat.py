"""对话 AC：问题解析→检索→回答、软失败引导语、400 字截断、提案批准前零变化。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.ai.fake import FakeAI
from app.services.chat_svc import ANSWER_GUIDANCE, GUIDANCE, QUESTION_LIMIT
from tests.conftest import FakeClock, drain, get_state


def _seed(client: TestClient, library: Path, clock: FakeClock) -> None:
    client.post("/api/directories?confirm=1", json={"path": str(library)})
    drain(get_state(client), clock)


def test_chat_full_flow_with_answer(
    client: TestClient, library: Path, fake_clock: FakeClock, fake_ai: FakeAI
) -> None:
    _seed(client, library, fake_clock)

    def handler(messages: list[dict[str, str]]) -> str:
        if messages[0]["role"] == "system":  # 第二段：生成回答
            return "找到 3 张测试图片。"
        return json.dumps(
            {"keywords": ["测试"], "category": None, "need_answer": True},
            ensure_ascii=False,
        )

    fake_ai.chat_handler = handler
    result = client.post("/api/chat", json={"question": "有哪些测试图片？"}).json()
    assert result["degraded"] is False
    assert result["answer"] == "找到 3 张测试图片。"
    assert len(result["items"]) == 3
    assert result["parsed"]["keywords"] == ["测试"]
    assert len(fake_ai.chat_calls) == 2


def test_chat_soft_failure_returns_guidance(
    client: TestClient, library: Path, fake_clock: FakeClock, fake_ai: FakeAI
) -> None:
    _seed(client, library, fake_clock)
    fake_ai.chat_failures = 1
    result = client.post("/api/chat", json={"question": "测试"}).json()
    assert result["degraded"] is True
    assert result["answer"] == GUIDANCE
    assert result["items"] == []  # 解析失败 → 不带结果

    # 第二次成功恢复
    result2 = client.post("/api/chat", json={"question": "测试"}).json()
    assert result2["degraded"] is False


def test_chat_need_answer_false_uses_search_answer(
    client: TestClient, library: Path, fake_clock: FakeClock, fake_ai: FakeAI
) -> None:
    _seed(client, library, fake_clock)
    fake_ai.chat_handler = lambda msgs: json.dumps(
        {"keywords": ["测试"], "need_answer": False}, ensure_ascii=False
    )
    result = client.post("/api/chat", json={"question": "测试在哪"}).json()
    assert result["answer"] == ANSWER_GUIDANCE
    assert len(result["items"]) == 3
    assert len(fake_ai.chat_calls) == 1  # 只解析，不生成回答


def test_chat_empty_and_long_question(client: TestClient, fake_ai: FakeAI) -> None:
    empty = client.post("/api/chat", json={"question": "   "}).json()
    assert "请输入" in empty["answer"]

    long = client.post("/api/chat", json={"question": "字" * 500}).json()
    assert len(str(long.get("question", ""))) == QUESTION_LIMIT  # 400 字截断
    assert long["degraded"] is False  # 默认解析不需回答 → 正常返回
    assert long["items"] == []

    via_get = client.get("/api/chat", params={"q": "测试", "limit": 100}).json()
    assert "question" in via_get
    assert via_get["question"] == "测试"


def test_chat_second_segment_failure_degrades_answer(
    client: TestClient, library: Path, fake_clock: FakeClock, fake_ai: FakeAI
) -> None:
    _seed(client, library, fake_clock)
    calls = {"n": 0}

    def handler(messages: list[dict[str, str]]) -> str:
        if messages[0]["role"] == "system":
            calls["n"] += 1
            raise RuntimeError("网络中断")
        return json.dumps({"keywords": ["测试"], "need_answer": True}, ensure_ascii=False)

    fake_ai.chat_handler = handler
    result = client.post("/api/chat", json={"question": "测试"}).json()
    assert result["answer"] == ANSWER_GUIDANCE
    assert len(result["items"]) == 3  # 检索结果仍然可用
    assert calls["n"] == 1


def test_chat_proposal_approve_creates_entity(
    client: TestClient, library: Path, fake_clock: FakeClock, fake_ai: FakeAI
) -> None:
    _seed(client, library, fake_clock)
    fake_ai.chat_handler = lambda msgs: json.dumps(
        {
            "keywords": ["测试"],
            "need_answer": False,
            "suggest_entity": {
                "name": "小白",
                "category": "宠物",
                "description": "白色小狗",
                "aliases": ["小白狗"],
            },
            "suggest_tag": "爱宠",
        },
        ensure_ascii=False,
    )
    client.post("/api/chat", json={"question": "测试"})
    proposals = client.get("/api/proposals").json()["items"]
    assert len(proposals) == 2
    assert {p["type"] for p in proposals} == {"entity", "tag"}

    # 批准前：库零变化
    assert client.get("/api/entities").json()["items"] == []

    entity_proposal = next(p for p in proposals if p["type"] == "entity")
    approved = client.post(f"/api/proposals/{entity_proposal['id']}/approve").json()
    assert approved["status"] == "approved"
    entities = client.get("/api/entities").json()["items"]
    assert entities[0]["name"] == "小白"
    assert "小白狗" in entities[0]["aliases"]

    tag_proposal = next(p for p in proposals if p["type"] == "tag")
    client.post(f"/api/proposals/{tag_proposal['id']}/approve")
    row = get_state(client).db.query_one("SELECT 1 FROM tags WHERE name='爱宠'")
    assert row is not None

    rejected = client.post(f"/api/proposals/{entity_proposal['id']}/reject")
    assert rejected.status_code == 200  # 重复决定也返回当前状态
    missing = client.post("/api/proposals/99999/approve")
    assert missing.status_code == 404
