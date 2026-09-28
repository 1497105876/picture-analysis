"""内置分类字典（6 类，不可删改）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategorySeed:
    name: str
    color: str
    emoji: str


BUILTIN_CATEGORIES: tuple[CategorySeed, ...] = (
    CategorySeed("风景", "#0ea5e9", "🏞️"),
    CategorySeed("人物", "#f43f5e", "👤"),
    CategorySeed("动物", "#f59e0b", "🐾"),
    CategorySeed("物品", "#8b5cf6", "📦"),
    CategorySeed("截图", "#10b981", "🖼️"),
    CategorySeed("其他", "#64748b", "📎"),
)


def builtin_names() -> list[str]:
    return [seed.name for seed in BUILTIN_CATEGORIES]
