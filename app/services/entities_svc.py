"""资料库服务：实体 CRUD、三路命中注入选择、参考图与向量。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import numpy.typing as npt

from app.ai.protocol import EmbedClient
from app.domain.errors import ConflictError, NotFoundError, ValidationAppError

if TYPE_CHECKING:
    from app.services.state import AppState

REFS_PER_ENTITY = 2
MAX_ENTITIES = 6
MAX_REFS_TOTAL = 6


def _entity_text(entity: dict[str, Any]) -> str:
    parts = [str(entity.get("name", "")), str(entity.get("description", ""))]
    aliases = entity.get("aliases") or []
    parts.extend(str(a) for a in aliases)
    return "\n".join(p for p in parts if p)


def embed_entity(state: AppState, entity_id: int, embed: EmbedClient | None) -> None:
    """实体卡变更后尽力重算向量（失败不影响保存，注入退化为前两路）。"""
    if embed is None:
        return
    entity = state.entities.get(entity_id)
    if entity is None:
        return
    try:
        matrix = embed.embed([_entity_text(entity)])
    except Exception:  # noqa: BLE001 — 软失败：实体向量缺失只影响召回
        return
    if matrix.size:
        state.entities.set_vector(entity_id, matrix[0])


def list_entities(state: AppState, include_inactive: bool = False) -> list[dict[str, Any]]:
    return state.entities.entries(include_inactive)


def get_entity(state: AppState, entity_id: int) -> dict[str, Any]:
    entity = state.entities.get(entity_id)
    if entity is None:
        raise NotFoundError(f"实体不存在：{entity_id}")
    return entity


def create_entity(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValidationAppError("实体名称不能为空")
    if state.entities.get_by_name(name):
        raise ConflictError(f"实体已存在：{name}")
    entity_id = state.entities.add(
        name,
        str(payload.get("category", "")),
        str(payload.get("description", "")),
        [str(a) for a in payload.get("aliases", [])],
    )
    for path in payload.get("reference_paths", []):
        state.entities.add_reference(entity_id, str(path))
    embed_entity(state, entity_id, state.get_embed())
    return get_entity(state, entity_id)


def update_entity(state: AppState, entity_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    if state.entities.get(entity_id) is None:
        raise NotFoundError(f"实体不存在：{entity_id}")
    fields: dict[str, Any] = {}
    for key in ("name", "category", "description", "active"):
        if key in payload:
            fields[key] = payload[key]
    if fields:
        state.entities.update(entity_id, **fields)
    if "aliases" in payload:
        state.entities.set_aliases(entity_id, [str(a) for a in payload["aliases"]])
    embed_entity(state, entity_id, state.get_embed())
    return get_entity(state, entity_id)


def delete_entity(state: AppState, entity_id: int) -> None:
    if state.entities.get(entity_id) is None:
        raise NotFoundError(f"实体不存在：{entity_id}")
    state.entities.delete(entity_id)


def add_reference(state: AppState, entity_id: int, path: str) -> dict[str, Any]:
    if state.entities.get(entity_id) is None:
        raise NotFoundError(f"实体不存在：{entity_id}")
    if not path.strip():
        raise ValidationAppError("参考图路径不能为空")
    state.entities.add_reference(entity_id, path)
    return get_entity(state, entity_id)


def remove_reference(state: AppState, entity_id: int, ref_id: int) -> dict[str, Any]:
    if state.entities.get(entity_id) is None:
        raise NotFoundError(f"实体不存在：{entity_id}")
    state.entities.remove_reference(ref_id)
    return get_entity(state, entity_id)


def link_image(state: AppState, entity_id: int, image_id: int) -> None:
    if state.entities.get(entity_id) is None:
        raise NotFoundError(f"实体不存在：{entity_id}")
    state.entities.link_image(entity_id, image_id)


def unlink_image(state: AppState, entity_id: int, image_id: int) -> None:
    state.entities.unlink_image(entity_id, image_id)


def _cosine(a: npt.NDArray[np.float32], b: npt.NDArray[np.float32]) -> float:
    if a.size == 0 or b.size == 0 or a.shape[0] != b.shape[0]:
        return 0.0
    denom = float(np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
    return float(np.dot(a, b) / denom)


def select_injection(
    state: AppState, image: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    """三路注入：①手动关联 ②别名硬匹配 ③向量 Top3；返回 (实体, 参考图路径)。"""
    entities = state.entities.all_active_with_aliases()
    if not entities:
        return [], []
    image_id = int(image["id"])
    path = str(image["path"]).lower()
    filename = str(image["filename"]).lower()

    chosen: dict[int, dict[str, Any]] = {}
    # ① 手动关联
    for entity in entities:
        linked = [int(i) for i in (entity.get("linked_ids") or [])]
        if image_id in linked:
            chosen[int(entity["id"])] = entity
    # ② 别名硬匹配（文件名/路径）
    for entity in entities:
        if int(entity["id"]) in chosen:
            continue
        aliases = [str(a) for a in (entity.get("aliases") or [])]
        for alias in aliases:
            needle = alias.lower()
            if needle and (needle in filename or needle in path):
                chosen[int(entity["id"])] = entity
                break
    # ③ 向量 Top3
    image_vector = state.images.get_vector(image_id)
    if image_vector is not None:
        entity_vectors = state.entities.vectors()
        scored: list[tuple[float, dict[str, Any]]] = []
        for entity in entities:
            if int(entity["id"]) in chosen:
                continue
            vec = entity_vectors.get(int(entity["id"]))
            if vec is None:
                continue
            score = _cosine(image_vector, vec)
            if score > 0.0:
                scored.append((score, entity))
        for _, entity in sorted(scored, key=lambda p: (-p[0], int(p[1]["id"])))[:3]:
            chosen[int(entity["id"])] = entity

    selected = sorted(chosen.values(), key=lambda e: int(e["id"]))[:MAX_ENTITIES]
    refs: list[str] = []
    for entity in selected:
        for ref in (entity.get("reference_paths") or [])[:REFS_PER_ENTITY]:
            if ref not in refs:
                refs.append(ref)
    return selected, refs[:MAX_REFS_TOTAL]
