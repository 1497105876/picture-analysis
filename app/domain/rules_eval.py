"""分类规则求值（纯函数）：IF 条件 -> THEN 动作，首条命中即停。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuleContext:
    path: str
    filename: str
    dir_path: str
    ocr_text: str
    category: str | None


@dataclass(frozen=True)
class Rule:
    id: int
    name: str
    priority: int
    enabled: bool
    condition: dict[str, Any]
    action: dict[str, Any]


_TARGETS = {"dir_prefix", "dir_suffix", "filename", "ocr_text", "category"}
_OPS = {"contains", "equals", "startswith", "endswith", "regex"}


def _target_value(target: str, ctx: RuleContext) -> str:
    if target == "dir_prefix":
        return ctx.dir_path
    if target == "dir_suffix":
        return ctx.path
    if target == "filename":
        return ctx.filename
    if target == "ocr_text":
        return ctx.ocr_text
    return ctx.category or ""


def match_condition(condition: dict[str, Any], ctx: RuleContext) -> bool:
    target = str(condition.get("target", ""))
    op = str(condition.get("op", "contains"))
    value = str(condition.get("value", ""))
    if target not in _TARGETS or op not in _OPS:
        return False
    if not value:
        return False
    subject = _target_value(target, ctx)
    if op == "contains":
        return value in subject
    if op == "equals":
        return subject == value
    if op == "startswith":
        return subject.startswith(value)
    if op == "endswith":
        return subject.endswith(value)
    try:
        return re.search(value, subject) is not None
    except re.error:
        return False


def first_match(rules: list[Rule], ctx: RuleContext) -> Rule | None:
    """按 priority 升序遍历启用规则，首条命中即停。"""
    for rule in sorted(rules, key=lambda item: (item.priority, item.id)):
        if not rule.enabled:
            continue
        if match_condition(rule.condition, ctx):
            return rule
    return None


def action_of(rule: Rule) -> dict[str, Any]:
    return rule.action
