"""检索仓储：筛选、FTS、向量、cursor 分页、历史与同义词。"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt

from app.storage.db import Database, now_iso
from app.storage.helpers import rows_to_dicts

SORT_COLUMNS: dict[str, str] = {
    "id": "id",
    "mtime": "mtime",
    "rating": "rating",
    "taken": "COALESCE(exif_taken_at, '')",
    "created": "created_at",
    "filename": "filename",
}


@dataclass
class Filters:
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    rating_min: int | None = None
    favorite: bool | None = None
    dir_id: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    analysis_state: str | None = None
    hidden: bool = False


def encode_cursor(sort_value: Any, row_id: int) -> str:
    raw = json.dumps({"v": sort_value, "id": row_id}, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[Any, int]:
    data = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    return data["v"], int(data["id"])


class SearchRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def build_where(self, filters: Filters) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        table = "hidden_images" if filters.hidden else "images"
        if filters.category:
            clauses.append(f"COALESCE({table}.category_manual, {table}.category_ai) = ?")
            params.append(filters.category)
        if filters.dir_id is not None:
            clauses.append(f"{table}.dir_id = ?")
            params.append(filters.dir_id)
        if filters.rating_min is not None:
            clauses.append(f"{table}.rating >= ?")
            params.append(filters.rating_min)
        if filters.favorite is not None:
            clauses.append(f"{table}.favorite = ?")
            params.append(int(filters.favorite))
        if filters.date_from:
            clauses.append(
                f"COALESCE({table}.exif_taken_at, {table}.created_at) >= ?"
            )
            params.append(filters.date_from)
        if filters.date_to:
            clauses.append(
                f"COALESCE({table}.exif_taken_at, {table}.created_at) <= ?"
            )
            params.append(filters.date_to)
        if filters.analysis_state:
            clauses.append(f"{table}.analysis_state = ?")
            params.append(filters.analysis_state)
        for tag in filters.tags:
            if filters.hidden:
                clauses.append(
                    "EXISTS (SELECT 1 FROM ai_tags t WHERE t.image_id = "
                    f"{table}.id AND t.tag = ?)"
                )
            else:
                clauses.append(
                    "EXISTS (SELECT 1 FROM image_tags jt JOIN tags tg ON tg.id = jt.tag_id "
                    f"WHERE jt.image_id = {table}.id AND tg.name = ?)"
                    f" OR EXISTS (SELECT 1 FROM ai_tags t WHERE t.image_id = {table}.id AND t.tag = ?)"
                )
                params.append(tag)
            params.append(tag)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    # ---------- 列表 + cursor ----------

    def list_images(
        self,
        filters: Filters,
        *,
        sort: str = "mtime",
        order: str = "desc",
        cursor: str | None = None,
        limit: int = 100,
        restrict_ids: list[int] | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        table = "hidden_images" if filters.hidden else "images"
        column = SORT_COLUMNS.get(sort, SORT_COLUMNS["mtime"])
        direction = "ASC" if order.lower() == "asc" else "DESC"
        where, params = self.build_where(filters)
        clauses: list[str] = []
        if where:
            clauses.append(where[6:])
        if restrict_ids is not None:
            if not restrict_ids:
                return [], None
            clauses.append(f"{table}.id IN ({', '.join('?' for _ in restrict_ids)})")
            params = [*params, *restrict_ids]
        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM {table} {where_sql}"
        page_params = list(params)
        if cursor:
            try:
                cursor_value, cursor_id = decode_cursor(cursor)
            except (ValueError, KeyError, json.JSONDecodeError, TypeError):
                cursor_value, cursor_id = None, 0
            op = "<" if direction == "DESC" else ">"
            joiner = " AND " if where_sql else " WHERE "
            sql += (
                f"{joiner}({column} {op} ? OR ({column} = ? AND {table}.id {op} ?))"
            )
            page_params = [*page_params, cursor_value, cursor_value, cursor_id]
        sql += f" ORDER BY {column} {direction}, {table}.id {direction} LIMIT ?"
        page_params.append(limit + 1)
        rows = rows_to_dicts(self._db.query(sql, page_params))
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            sort_key = {
                "id": last["id"],
                "mtime": last["mtime"],
                "rating": last["rating"],
                "taken": last["exif_taken_at"] or "",
                "created": last["created_at"],
                "filename": last["filename"],
            }.get(sort, last["mtime"])
            next_cursor = encode_cursor(sort_key, int(last["id"]))
        return rows, next_cursor

    # ---------- FTS ----------

    def fts_search(self, tokens: list[str], limit: int = 200) -> list[int]:
        if not tokens:
            return []
        from app.storage.helpers import cut

        flat: list[str] = []
        for token in tokens:
            pieces = cut(token) if any("一" <= ch <= "鿿" for ch in token) else [token]
            flat.extend(piece for piece in pieces if piece)
        if not flat:
            return []
        match = " OR ".join(f'"{token}"' for token in flat)
        rows = self._db.query(
            "SELECT f.image_id FROM image_fts f JOIN images i ON i.id = f.image_id "
            "WHERE image_fts MATCH ? ORDER BY rank LIMIT ?",
            (match, limit),
        )
        return [int(row["image_id"]) for row in rows]

    # ---------- 向量 ----------

    def vector_search(
        self,
        query: npt.NDArray[np.float32],
        limit: int,
        filters: Filters,
    ) -> list[tuple[int, float]]:
        if filters.hidden or query.size == 0:
            return []
        where, params = self.build_where(filters)
        rows = self._db.query(
            f"SELECT v.image_id, v.vector FROM image_vectors v "
            f"JOIN images ON images.id = v.image_id {where}",
            params,
        )
        if not rows:
            return []
        ids = [int(row["image_id"]) for row in rows]
        matrix = np.vstack(
            [np.frombuffer(bytes(row["vector"]), dtype=np.float32) for row in rows]
        )
        if matrix.shape[1] != query.size:
            return []
        norms = np.linalg.norm(matrix, axis=1)
        norms[norms == 0] = 1.0
        q = query.astype(np.float32)
        q_norm = float(np.linalg.norm(q)) or 1.0
        scores = (matrix @ q) / (norms * q_norm)
        ranked = sorted(zip(ids, scores.tolist(), strict=True), key=lambda p: (-p[1], p[0]))
        return ranked[:limit]

    # ---------- 历史 / 同义词 / 权重 ----------

    def add_history(self, query: str) -> None:
        self._db.execute(
            "INSERT INTO search_history(query, created_at) VALUES(?,?)", (query, now_iso())
        )

    def list_history(self, limit: int = 50) -> list[str]:
        rows = self._db.query(
            "SELECT query FROM search_history ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [str(row["query"]) for row in rows]

    def clear_history(self) -> None:
        self._db.execute("DELETE FROM search_history")

    def synonym_map(self) -> dict[str, list[str]]:
        rows = self._db.query("SELECT group_name, term FROM synonyms ORDER BY id")
        result: dict[str, list[str]] = {}
        for row in rows:
            result.setdefault(str(row["group_name"]), []).append(str(row["term"]))
        return result

    def term_weights(self) -> dict[str, float]:
        rows = self._db.query("SELECT term, weight FROM term_weights")
        return {str(row["term"]): float(row["weight"]) for row in rows}
