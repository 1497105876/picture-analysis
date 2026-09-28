"""AI 客户端协议与数据结构（OpenAI 兼容）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import numpy.typing as npt


@dataclass
class VisionRequest:
    image_path: str
    prompt: str
    model: str
    reference_paths: list[str] = field(default_factory=list)
    context_text: str = ""
    allow_remote: bool = True


@dataclass
class VisionOutput:
    category: str | None
    description: str
    ai_tags: list[str]
    elements: list[str]
    has_text: bool
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""


@dataclass
class OcrOutput:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""


@dataclass
class ChatOutput:
    content: str
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""


class VisionClient(Protocol):
    def analyze(self, request: VisionRequest) -> VisionOutput: ...

    def ocr(self, request: VisionRequest) -> OcrOutput: ...


class EmbedClient(Protocol):
    model: str

    def embed(self, texts: list[str]) -> npt.NDArray[np.float32]: ...


class ChatClient(Protocol):
    model: str

    def complete(self, messages: list[dict[str, str]]) -> ChatOutput: ...
