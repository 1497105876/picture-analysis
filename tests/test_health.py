"""冒烟：应用可装配、健康端点可用。AC 横切-交付。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health() -> None:
    client = TestClient(create_app())
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]


def test_openapi_available() -> None:
    client = TestClient(create_app())
    assert client.get("/api/openapi.json").status_code == 200


def test_spa_fallback_serves_index() -> None:
    """非 /api 路径回退到 index.html（SPA 路由）。"""
    client = TestClient(create_app())
    response = client.get("/some/deep/route")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
