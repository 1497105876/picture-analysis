"""仓储公共工具。"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from sqlite3 import Row

_CUTTER: Callable[[str], list[str]] | None = None


def _cutter() -> Callable[[str], list[str]]:
    global _CUTTER
    if _CUTTER is None:
        import jieba

        jieba.setLogLevel(logging.ERROR)
        _CUTTER = jieba.lcut
    return _CUTTER


def cut(text: str) -> list[str]:
    """jieba 分词（查询侧）：剔除空白与单字中文停用噪声。"""
    if not text or not text.strip():
        return []
    tokens = [token.strip() for token in _cutter()(text.strip())]
    result = []
    for token in tokens:
        if not token:
            continue
        if len(token) == 1 and "一" <= token <= "鿿":
            continue
        result.append(token)
    return result


def tokenize(text: str) -> str:
    """写入 FTS 前的中文预分词（unicode61 只能按空白切分）。"""
    if not text:
        return ""
    return " ".join(token.strip() for token in _cutter()(str(text)) if token.strip())


def to_dict(row: Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_to_dicts(rows: list[Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return default
