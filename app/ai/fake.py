"""FakeAI：测试与离线演示用，零网络，可注入行为与故障。"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

import numpy as np
import numpy.typing as npt

from app.ai.protocol import ChatOutput, OcrOutput, VisionOutput, VisionRequest
from app.domain.errors import AiUnavailable

DEFAULT_VISION = VisionOutput(
    category="其他",
    description="一张测试图片",
    ai_tags=["测试"],
    elements=["图片"],
    has_text=False,
)


class FakeAI:
    """同时实现 Vision/Embed/Chat 三个协议，记录全部调用。"""

    def __init__(self, dim: int = 8) -> None:
        self.model = "fake-model"
        self.dim = dim
        self.vision_calls: list[VisionRequest] = []
        self.ocr_calls: list[VisionRequest] = []
        self.embed_calls: list[list[str]] = []
        self.chat_calls: list[list[dict[str, str]]] = []
        self.vision_failures = 0
        self.chat_failures = 0
        self.embed_failures = 0
        self.vision_handler: Callable[[VisionRequest], VisionOutput] | None = None
        self.ocr_handler: Callable[[VisionRequest], OcrOutput] | None = None
        self.chat_handler: Callable[[list[dict[str, str]]], str] | None = None

    # ---------- VisionClient ----------

    def analyze(self, request: VisionRequest) -> VisionOutput:
        self.vision_calls.append(request)
        if self.vision_failures > 0:
            self.vision_failures -= 1
            raise AiUnavailable("模拟识图服务不可用")
        if self.vision_handler is not None:
            return self.vision_handler(request)
        return DEFAULT_VISION

    def ocr(self, request: VisionRequest) -> OcrOutput:
        self.ocr_calls.append(request)
        if self.vision_failures > 0:
            self.vision_failures -= 1
            raise AiUnavailable("模拟 OCR 服务不可用")
        if self.ocr_handler is not None:
            return self.ocr_handler(request)
        return OcrOutput(text="示例文字 OCR-1234", tokens_out=10, model=self.model)

    # ---------- EmbedClient ----------

    def embed(self, texts: list[str]) -> npt.NDArray[np.float32]:
        self.embed_calls.append(list(texts))
        if self.embed_failures > 0:
            self.embed_failures -= 1
            raise AiUnavailable("模拟嵌入服务不可用")
        rows = []
        for text in texts:
            seed = int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)
            rng = np.random.default_rng(seed)
            vector = rng.standard_normal(self.dim).astype(np.float32)
            norm = float(np.linalg.norm(vector)) or 1.0
            rows.append(vector / norm)
        return np.vstack(rows) if rows else np.zeros((0, self.dim), dtype=np.float32)

    # ---------- ChatClient ----------

    def complete(self, messages: list[dict[str, str]]) -> ChatOutput:
        self.chat_calls.append(messages)
        if self.chat_failures > 0:
            self.chat_failures -= 1
            raise AiUnavailable("模拟对话服务不可用")
        if self.chat_handler is not None:
            content = self.chat_handler(messages)
        else:
            content = '{"keywords":[],"category":null,"need_answer":false}'
        return ChatOutput(content=content, tokens_in=5, tokens_out=5, model=self.model)
