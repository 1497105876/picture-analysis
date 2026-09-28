"""设置 AC：schema 驱动、类型收敛、审计回滚、档案密钥 .env、探测、备份、限速热更。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.services.state import AppState
from tests.conftest import FakeClock, get_state


def test_schema_payload_has_groups_and_values(client: TestClient) -> None:
    payload = client.get("/api/settings").json()
    group_ids = {group["id"] for group in payload["groups"]}
    assert {"G1", "G3", "G6", "G7", "G10", "G18"} <= group_ids
    assert payload["values"]["rate_limit_per_minute"] == 20
    assert payload["values"]["min_interval_seconds"] == 3.0
    assert payload["danger_groups"] == ["G10"]
    g3 = next(g for g in payload["groups"] if g["id"] == "G3")
    rate_item = next(i for i in g3["items"] if i["key"] == "rate_limit_per_minute")
    assert rate_item["min"] == 1 and rate_item["max"] == 60


def test_put_coerces_types_and_clamps_range(client: TestClient, fake_clock: FakeClock) -> None:
    applied = client.put(
        "/api/settings",
        json={
            "values": {
                "rate_limit_per_minute": 999,  # 超上限 → 收敛到 60
                "min_interval_seconds": "1.5",  # 字符串 → float
                "theme": "purple",  # 非法选项 → 回落默认
                "style_confidence": "yes",  # 字符串布尔
                "exclude_globs": "node_modules, .git",  # csv → 列表
            }
        },
    ).json()["applied"]
    assert applied["rate_limit_per_minute"] == 60
    assert applied["min_interval_seconds"] == 1.5
    assert applied["theme"] == "system"
    assert applied["style_confidence"] is True
    assert applied["exclude_globs"] == ["node_modules", ".git"]

    # 限速热更新同步到限速器
    state = get_state(client)
    assert state.limiter.config.per_minute == 60
    assert state.limiter.config.min_interval == 1.5


def test_unknown_key_rejected(client: TestClient) -> None:
    response = client.put("/api/settings", json={"values": {"no_such_key": 1}})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_audit_and_rollback(client: TestClient) -> None:
    client.put("/api/settings", json={"values": {"accent": "#ff0000"}})
    items = client.get("/api/settings/audit").json()["items"]
    row = next(r for r in items if r["key"] == "accent")
    assert row["after"] == "#ff0000" or row["after"] is not None

    rolled = client.post(f"/api/settings/audit/{row['id']}/rollback")
    assert rolled.status_code == 200
    assert client.get("/api/settings").json()["values"]["accent"] == "#2563eb"

    missing = client.post("/api/settings/audit/99999/rollback")
    assert missing.status_code == 404


def test_profiles_key_lives_only_in_env(client: TestClient, tmp_path: Path) -> None:
    saved = client.post(
        "/api/settings/profiles",
        json={
            "name": "default",
            "base_url": "http://127.0.0.1:11434/v1",
            "type": "openai",
            "api_key": "sk-secret-42",
        },
    ).json()
    assert saved["api_key_set"] is True
    assert saved["api_key"] == "sk-secret-42"

    env_file = tmp_path / ".env"
    assert env_file.is_file()
    assert "PA_KEY_DEFAULT=sk-secret-42" in env_file.read_text(encoding="utf-8")

    # 密钥不落数据库
    state = get_state(client)
    assert all("sk-secret-42" not in str(v) for v in state.settings_repo.all().values())
    # 界面按口径可读回明文
    listed = client.get("/api/settings/profiles").json()
    assert listed["profiles"][0]["api_key"] == "sk-secret-42"
    assert listed["bindings"]["profile_vision"] == "default"

    # 解析出可用客户端（远程端点带密钥）
    assert state.get_vision() is not None

    client.request("DELETE", "/api/settings/profiles/default")
    assert "PA_KEY_DEFAULT" not in env_file.read_text(encoding="utf-8")
    gone = client.request("DELETE", "/api/settings/profiles/default")
    assert gone.status_code == 404


def test_profile_validation(client: TestClient) -> None:
    bad_url = client.post("/api/settings/profiles", json={"name": "x", "base_url": "ftp://a"})
    assert bad_url.status_code == 422
    bad_type = client.post(
        "/api/settings/profiles",
        json={"name": "x", "base_url": "http://a/v1", "type": "weird"},
    )
    assert bad_type.status_code == 422
    no_name = client.post("/api/settings/profiles", json={"base_url": "http://a/v1"})
    assert no_name.status_code == 422


def test_probe_connection_fail_is_soft(client: TestClient) -> None:
    result = client.post(
        "/api/settings/test",
        json={"base_url": "http://127.0.0.1:9/v1", "api_key": ""},
    ).json()
    assert result["ok"] is False
    assert "连接失败" in result["error"]

    bad = client.post("/api/settings/test", json={"base_url": "ftp://x"})
    assert bad.status_code == 422

    nothing = client.post("/api/settings/test", json={})
    assert nothing.status_code == 404  # 无档案可用


def test_backup_creates_file(client: TestClient) -> None:
    path = Path(client.post("/api/settings/backup").json()["path"])
    assert path.is_file()
    assert path.suffix == ".db"


def test_values_merged_in_get(client: TestClient) -> None:
    client.put("/api/settings", json={"values": {"thumb_size": 300}})
    payload = client.get("/api/settings").json()
    assert payload["values"]["thumb_size"] == 300
    assert isinstance(get_state(client), AppState)
