"""OpenAI 兼容客户端：MockTransport 注入，零网络验证协议解析与错误映射。"""

from __future__ import annotations

import json

import httpx
import numpy as np
import pytest

from app.ai.openai_client import (
    OpenAIChatClient,
    OpenAIEmbedClient,
    OpenAIVisionClient,
)
from app.ai.protocol import VisionRequest
from app.domain.errors import AiUnavailable


def _transport(handler) -> httpx.MockTransport:  # noqa: ANN001
    return httpx.MockTransport(handler)


def _vision_request(tmp_path) -> VisionRequest:  # noqa: ANN001
    image = tmp_path / "pic.jpg"
    image.write_bytes(b"\xff\xd8\xff\xe0fakejpg")
    return VisionRequest(image_path=str(image), prompt="描述这张图", model="", reference_paths=[])


def test_analyze_parses_json_content(tmp_path) -> None:
    body = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "category": "风景",
                            "description": "海边日落",
                            "ai_tags": ["海", "落日"],
                            "elements": ["太阳"],
                            "has_text": False,
                        },
                        ensure_ascii=False,
                    )
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        payload = json.loads(request.content)
        assert payload["temperature"] == 0.1
        return httpx.Response(200, json=body)

    client = OpenAIVisionClient(
        "https://api.test/v1", "sk-x", "model-a", transport=_transport(handler)
    )
    try:
        out = client.analyze(_vision_request(tmp_path))
    finally:
        client.close()
    assert out.category == "风景"
    assert out.description == "海边日落"
    assert out.ai_tags == ["海", "落日"]
    assert out.has_text is False
    assert out.tokens_in == 10 and out.tokens_out == 5
    assert out.model == "model-a"


def test_ocr_returns_text(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "  发票号码 888  \n"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4},
            },
        )

    client = OpenAIVisionClient(
        "https://api.test/v1", "sk-x", "model-a", transport=_transport(handler)
    )
    try:
        out = client.ocr(_vision_request(tmp_path))
    finally:
        client.close()
    assert out.text == "发票号码 888"
    assert out.tokens_out == 4


def test_embed_orders_by_index() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["input"] == ["a", "b"]
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ]
            },
        )

    client = OpenAIEmbedClient("https://api.test/v1", "sk-x", "emb", transport=_transport(handler))
    try:
        matrix = client.embed(["a", "b"])
    finally:
        client.close()
    assert matrix.shape == (2, 2)
    np.testing.assert_allclose(matrix[0], [1.0, 0.0])

    empty_client = OpenAIEmbedClient("https://api.test/v1", "sk-x", "emb")
    try:
        assert empty_client.embed([]).shape[0] == 0
    finally:
        empty_client.close()


def test_chat_complete() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"keywords":[]}'}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2},
            },
        )

    client = OpenAIChatClient("https://api.test/v1", "sk-x", "chat", transport=_transport(handler))
    try:
        out = client.complete([{"role": "user", "content": "hi"}])
    finally:
        client.close()
    assert out.content == '{"keywords":[]}'
    assert out.model == "chat"


@pytest.mark.parametrize(
    ("status", "fragment"),
    [
        (500, "稍后自动重试"),
        (429, "稍后自动重试"),
        (400, "拒绝请求"),
    ],
)
def test_error_status_mapping(tmp_path, status: int, fragment: str) -> None:
    handler = lambda request: httpx.Response(status, text="boom")  # noqa: E731
    client = OpenAIVisionClient("https://api.test/v1", "k", "m", transport=_transport(handler))
    with pytest.raises(AiUnavailable) as excinfo:
        try:
            client.analyze(_vision_request(tmp_path))
        finally:
            client.close()
    assert fragment in str(excinfo.value)


def test_non_json_and_structural_errors(tmp_path) -> None:
    text_handler = lambda request: httpx.Response(200, text="<html>err</html>")  # noqa: E731
    client = OpenAIVisionClient("https://api.test/v1", "k", "m", transport=_transport(text_handler))
    with pytest.raises(AiUnavailable, match="非 JSON"):
        try:
            client.analyze(_vision_request(tmp_path))
        finally:
            client.close()

    def missing_choices(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client2 = OpenAIChatClient(
        "https://api.test/v1", "k", "m", transport=_transport(missing_choices)
    )
    with pytest.raises(AiUnavailable, match="choices"):
        try:
            client2.complete([{"role": "user", "content": "x"}])
        finally:
            client2.close()


def test_connection_error_maps_to_ai_unavailable(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    client = OpenAIVisionClient("https://api.test/v1", "k", "m", transport=_transport(handler))
    with pytest.raises(AiUnavailable, match="连接失败"):
        try:
            client.analyze(_vision_request(tmp_path))
        finally:
            client.close()


def test_embed_structural_error() -> None:
    handler = lambda request: httpx.Response(200, json={"data": "nope"})  # noqa: E731
    client = OpenAIEmbedClient("https://api.test/v1", "k", "m", transport=_transport(handler))
    with pytest.raises(AiUnavailable, match="结构异常"):
        try:
            client.embed(["x"])
        finally:
            client.close()
