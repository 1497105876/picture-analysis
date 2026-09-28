"""Prompt 构造（识图 / OCR / 对话解析），参数全部来自配置。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PromptStyle:
    language: str = "中文"
    style: str = "简洁"
    with_confidence: bool = False
    sensitive_words: tuple[str, ...] = ()


VISION_SYSTEM = """你是图片分析引擎。只输出 JSON，不要任何解释文字。
字段：
- category：从给定分类列表中选一个（没有合适的输出 null）
- description：一句话描述图片内容（{language}，{style}）
- ai_tags：3~5 个标签
- elements：元素清单，尽量多、尽量全，包含几乎所有可识别的东西
- has_text：图片中是否含有可读文字（布尔）
{confidence_line}"""


def build_vision_prompt(style: PromptStyle, categories: list[str]) -> str:
    confidence_line = "- confidence：0~100 整数置信度\n" if style.with_confidence else ""
    system = VISION_SYSTEM.format(
        language=style.language, style=style.style, confidence_line=confidence_line
    )
    return (
        f"{system}\n分类列表：{json.dumps(categories, ensure_ascii=False)}\n"
        '输出 JSON 示例：{"category":"风景","description":"...","ai_tags":["..."],'
        '"elements":["..."],"has_text":false}'
    )


def build_ocr_prompt(style: PromptStyle) -> str:
    return f"提取图片中的全部文字，只输出原文（{style.language}），不要解释。"


def build_entity_context(entities: list[dict[str, Any]], image_filename: str) -> str:
    """三路命中的实体注入文本（参考图由客户端附带）。"""
    if not entities:
        return ""
    lines = ["以下是已知标准人物/实体资料，识别时请对照参考图："]
    for entity in entities:
        aliases = "/".join(entity.get("aliases", []))
        lines.append(
            f"- {entity['name']}（{aliases}）类别:{entity.get('category', '')} "
            f"特征:{entity.get('description', '')}"
        )
    lines.append(f"待识别文件名：{image_filename}")
    return "\n".join(lines)


def build_chat_parse_prompt(question: str, categories: list[str]) -> str:
    system = (
        "你是图片库查询解析器。把用户问题解析为 JSON，字段："
        "keywords(字符串数组)、category(可空)、date_from(YYYY-MM-DD 可空)、"
        "date_to(可空)、rating_min(整数可空)、need_answer(布尔)。"
        "只输出 JSON。"
    )
    return json.dumps(
        {"system": system, "categories": categories, "question": question},
        ensure_ascii=False,
    )


def parse_chat_json(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None
