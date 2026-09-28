"""OpenAI 兼容 HTTP 客户端（识图 / OCR / 嵌入 / 对话）。"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import numpy.typing as npt

from app.ai.prompts import parse_chat_json
from app.ai.protocol import ChatOutput, OcrOutput, VisionOutput, VisionRequest
from app.domain.errors import AiUnavailable


def _data_uri(path: str) -> str:
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    data = Path(path).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


class _BaseClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 90.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        normalized = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=normalized,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise AiUnavailable(f"AI 服务连接失败：{exc.__class__.__name__}") from exc
        if response.status_code >= 500 or response.status_code == 429:
            raise AiUnavailable(f"AI 服务返回 {response.status_code}，稍后自动重试")
        if response.status_code >= 400:
            raise AiUnavailable(f"AI 服务拒绝请求（{response.status_code}）：{response.text[:200]}")
        try:
            data = response.json()
        except ValueError as exc:
            raise AiUnavailable("AI 服务返回了非 JSON 内容") from exc
        if not isinstance(data, dict):
            raise AiUnavailable("AI 服务返回结构异常")
        return data

    @staticmethod
    def _usage(data: dict[str, Any]) -> tuple[int, int]:
        usage = data.get("usage") or {}
        return int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))

    @staticmethod
    def _content(data: dict[str, Any]) -> str:
        try:
            return str(data["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError) as exc:
            raise AiUnavailable("AI 服务返回缺少 choices") from exc


class OpenAIVisionClient(_BaseClient):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 90.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(base_url, api_key, timeout, transport)
        self.model = model

    def _message_payload(self, request: VisionRequest, prompt: str) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        if request.context_text:
            content.insert(0, {"type": "text", "text": request.context_text})
        for reference in request.reference_paths[:6]:
            try:
                content.append({"type": "image_url", "image_url": {"url": _data_uri(reference)}})
            except OSError:
                continue
        content.append({"type": "image_url", "image_url": {"url": _data_uri(request.image_path)}})
        return [
            {"role": "system", "content": "你是图片分析助手，只输出要求的 JSON 或文本。"},
            {"role": "user", "content": content},
        ]

    def analyze(self, request: VisionRequest) -> VisionOutput:
        payload: dict[str, Any] = {
            "model": request.model or self.model,
            "messages": self._message_payload(request, request.prompt),
            "temperature": 0.1,
        }
        data = self._post_json("/chat/completions", payload)
        content = self._content(data)
        parsed = parse_chat_json(content) or {}
        tags = [str(t) for t in parsed.get("ai_tags", []) if t]
        elements = [str(e) for e in parsed.get("elements", []) if e]
        tokens_in, tokens_out = self._usage(data)
        category = parsed.get("category")
        return VisionOutput(
            category=str(category) if category else None,
            description=str(parsed.get("description", "")),
            ai_tags=tags[:5],
            elements=elements,
            has_text=bool(parsed.get("has_text", False)),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=payload["model"],
        )

    def ocr(self, request: VisionRequest) -> OcrOutput:
        payload: dict[str, Any] = {
            "model": request.model or self.model,
            "messages": self._message_payload(request, request.prompt),
            "temperature": 0.0,
        }
        data = self._post_json("/chat/completions", payload)
        tokens_in, tokens_out = self._usage(data)
        return OcrOutput(
            text=self._content(data).strip(),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=payload["model"],
        )


class OpenAIEmbedClient(_BaseClient):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(base_url, api_key, timeout, transport)
        self.model = model

    def embed(self, texts: list[str]) -> npt.NDArray[np.float32]:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        data = self._post_json("/embeddings", {"model": self.model, "input": texts})
        try:
            items = sorted(data["data"], key=lambda item: int(item["index"]))
            matrix = np.array([item["embedding"] for item in items], dtype=np.float32)
        except (KeyError, TypeError, ValueError) as exc:
            raise AiUnavailable("嵌入服务返回结构异常") from exc
        return matrix


class OpenAIChatClient(_BaseClient):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(base_url, api_key, timeout, transport)
        self.model = model

    def complete(self, messages: list[dict[str, str]]) -> ChatOutput:
        data = self._post_json(
            "/chat/completions",
            {"model": self.model, "messages": messages, "temperature": 0.2},
        )
        tokens_in, tokens_out = self._usage(data)
        return ChatOutput(
            content=self._content(data),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=self.model,
        )
