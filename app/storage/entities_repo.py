"""资料库实体仓储（实体卡 / 别名 / 关联图 / 参考图 / 向量）。"""
from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt

from app.storage.db import Database, now_iso
from app.storage.helpers import rows_to_dicts


class EntitiesRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, name: str, category: str, description: str,
            aliases: list[str] | None = None) -> int:
        cursor = self._db.execute(
            "INSERT INTO entities(name, category, description, active, created_at) "
            "VALUES(?,?,?,1,?)",
            (name, category, description, now_iso()),
        )
        entity_id = int(cursor.lastrowid or 0)
        for alias in dict.fromkeys([name, *(aliases or [])]):
            self._db.execute(
                "INSERT OR IGNORE INTO entity_aliases(entity_id, alias) VALUES(?,?)",
                (entity_id, alias),
            )
        return entity_id

    def update(self, entity_id: int, **fields: Any) -> None:
        allowed = {"name", "category", "description", "active"}
        pairs = [(k, v) for k, v in fields.items() if k in allowed]
        if pairs:
            columns = ", ".join(f"{k}=?" for k, _ in pairs)
            self._db.execute(
                f"UPDATE entities SET {columns} WHERE id=?",
                tuple(v for _, v in pairs) + (entity_id,),
            )

    def set_aliases(self, entity_id: int, aliases: list[str]) -> None:
        with self._db.tx():
            self._db.execute("DELETE FROM entity_aliases WHERE entity_id=?", (entity_id,))
            row = self._db.query_one("SELECT name FROM entities WHERE id=?", (entity_id,))
            names = [str(row["name"])] if row else []
            for alias in dict.fromkeys([*names, *aliases]):
                self._db.execute(
                    "INSERT OR IGNORE INTO entity_aliases(entity_id, alias) VALUES(?,?)",
                    (entity_id, alias),
                )

    def delete(self, entity_id: int) -> None:
        self._db.execute("DELETE FROM entities WHERE id=?", (entity_id,))

    def get(self, entity_id: int) -> dict[str, Any] | None:
        row = self._db.query_one("SELECT * FROM entities WHERE id=?", (entity_id,))
        if row is None:
            return None
        data = dict(row)
        data.pop("vector", None)
        data.pop("vector_dim", None)
        data["aliases"] = [str(r["alias"]) for r in self._db.query(
            "SELECT alias FROM entity_aliases WHERE entity_id=? ORDER BY alias", (entity_id,)
        )]
        data["reference_images"] = [dict(r) for r in self._db.query(
            "SELECT id, path, sort FROM reference_images WHERE entity_id=? ORDER BY sort, id",
            (entity_id,),
        )]
        data["linked_image_ids"] = [int(r["image_id"]) for r in self._db.query(
            "SELECT image_id FROM entity_images WHERE entity_id=? ORDER BY image_id",
            (entity_id,),
        )]
        return data

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        row = self._db.query_one("SELECT id FROM entities WHERE name=?", (name,))
        if row is None:
            return None
        return self.get(int(row["id"]))

    def entries(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT id, name, category, description, active, created_at FROM entities"
        if not include_inactive:
            sql += " WHERE active=1"
        rows = rows_to_dicts(self._db.query(sql + " ORDER BY id"))
        for row in rows:
            aliases = self._db.query(
                "SELECT alias FROM entity_aliases WHERE entity_id=? ORDER BY alias",
                (row["id"],),
            )
            row["aliases"] = [str(a["alias"]) for a in aliases]
        return rows

    def add_reference(self, entity_id: int, path: str) -> int:
        cursor = self._db.execute(
            "INSERT INTO reference_images(entity_id, path, sort) VALUES(?,?,?)",
            (entity_id, path, 0),
        )
        return int(cursor.lastrowid or 0)

    def remove_reference(self, ref_id: int) -> None:
        self._db.execute("DELETE FROM reference_images WHERE id=?", (ref_id,))

    def link_image(self, entity_id: int, image_id: int) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO entity_images(entity_id, image_id) VALUES(?,?)",
            (entity_id, image_id),
        )

    def unlink_image(self, entity_id: int, image_id: int) -> None:
        self._db.execute(
            "DELETE FROM entity_images WHERE entity_id=? AND image_id=?", (entity_id, image_id)
        )

    def all_active_with_aliases(self) -> list[dict[str, Any]]:
        entities = []
        for row in rows_to_dicts(self._db.query(
            "SELECT * FROM entities WHERE active=1 ORDER BY id"
        )):
            aliases = self._db.query(
                "SELECT alias FROM entity_aliases WHERE entity_id=?", (row["id"],)
            )
            refs = self._db.query(
                "SELECT path FROM reference_images WHERE entity_id=? ORDER BY sort, id LIMIT 2",
                (row["id"],),
            )
            linked = self._db.query(
                "SELECT image_id FROM entity_images WHERE entity_id=?", (row["id"],)
            )
            entity = dict(row)
            entity["aliases"] = [str(a["alias"]) for a in aliases]
            entity["reference_paths"] = [str(r["path"]) for r in refs]
            entity["linked_ids"] = [int(i["image_id"]) for i in linked]
            entities.append(entity)
        return entities

    def set_vector(self, entity_id: int, vector: npt.NDArray[np.float32]) -> None:
        self._db.execute(
            "UPDATE entities SET vector=?, vector_dim=? WHERE id=?",
            (vector.astype("float32").tobytes(), int(vector.size), entity_id),
        )

    def vectors(self) -> dict[int, npt.NDArray[np.float32]]:
        result: dict[int, npt.NDArray[np.float32]] = {}
        for row in self._db.query("SELECT id, vector FROM entities WHERE vector IS NOT NULL"):
            result[int(row["id"])] = np.frombuffer(bytes(row["vector"]), dtype=np.float32)
        return result
