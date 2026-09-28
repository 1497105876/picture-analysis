"""images / hidden_images 及其分析子表仓储。"""
from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt

from app.storage.db import Database, now_iso
from app.storage.helpers import rows_to_dicts


class ImagesRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    # ---------- 基础读写 ----------

    def insert(self, values: dict[str, Any]) -> int:
        now = now_iso()
        payload = dict(values)
        payload.setdefault("analysis_state", "unanalyzed")
        payload.setdefault("created_at", now)
        payload.setdefault("updated_at", now)
        columns = ", ".join(payload)
        marks = ", ".join("?" for _ in payload)
        cursor = self._db.execute(
            f"INSERT INTO images({columns}) VALUES({marks})", tuple(payload.values())
        )
        image_id = int(cursor.lastrowid or 0)
        self.fts_replace(image_id, str(payload.get("filename", "")), "", [], [], "")
        return image_id

    def get(self, image_id: int) -> dict[str, Any] | None:
        row = self._db.query_one("SELECT * FROM images WHERE id=?", (image_id,))
        return dict(row) if row else None

    def get_hidden(self, image_id: int) -> dict[str, Any] | None:
        row = self._db.query_one("SELECT * FROM hidden_images WHERE id=?", (image_id,))
        return dict(row) if row else None

    def find_by_path(self, dir_id: int, path: str) -> dict[str, Any] | None:
        row = self._db.query_one(
            "SELECT * FROM images WHERE dir_id=? AND path=?", (dir_id, path)
        )
        return dict(row) if row else None

    def find_by_md5(self, md5: str) -> list[dict[str, Any]]:
        return rows_to_dicts(
            self._db.query("SELECT * FROM images WHERE md5=? ORDER BY id", (md5,))
        )

    def update(self, image_id: int, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = now_iso()
        columns = ", ".join(f"{key}=?" for key in fields)
        self._db.execute(
            f"UPDATE images SET {columns} WHERE id=?", (*fields.values(), image_id)
        )

    def update_any(self, image_id: int, **fields: Any) -> bool:
        """按当前所在表（可见/隐藏）更新，识别备份照常。"""
        if not fields:
            return False
        fields["updated_at"] = now_iso()
        columns = ", ".join(f"{key}=?" for key in fields)
        cursor = self._db.execute(
            f"UPDATE images SET {columns} WHERE id=?", (*fields.values(), image_id)
        )
        if cursor.rowcount:
            return True
        cursor = self._db.execute(
            f"UPDATE hidden_images SET {columns} WHERE id=?", (*fields.values(), image_id)
        )
        return bool(cursor.rowcount)

    def delete(self, image_id: int) -> None:
        with self._db.tx():
            for table in ("images", "hidden_images"):
                self._db.execute(f"DELETE FROM {table} WHERE id=?", (image_id,))
            for table in ("analyses", "ocr_results", "image_vectors"):
                self._db.execute(f"DELETE FROM {table} WHERE image_id=?", (image_id,))
            for table in ("ai_tags", "image_elements", "image_tags"):
                self._db.execute(f"DELETE FROM {table} WHERE image_id=?", (image_id,))
            self._db.execute("DELETE FROM custom_field_values WHERE image_id=?", (image_id,))
            self._db.execute("DELETE FROM entity_images WHERE image_id=?", (image_id,))
            self.fts_delete(image_id)

    # ---------- 隐藏区（物理分表迁移，子表数据保留） ----------

    def _move_row(self, source: str, target: str, image_id: int) -> bool:
        row = self._db.query_one(f"SELECT * FROM {source} WHERE id=?", (image_id,))
        if row is None:
            return False
        data = dict(row)
        columns = ", ".join(data)
        marks = ", ".join("?" for _ in data)
        with self._db.tx():
            self._db.execute(f"INSERT INTO {target}({columns}) VALUES({marks})", tuple(data.values()))
            self._db.execute(f"DELETE FROM {source} WHERE id=?", (image_id,))
        return True

    def move_to_hidden(self, image_id: int) -> bool:
        return self._move_row("images", "hidden_images", image_id)

    def move_from_hidden(self, image_id: int) -> bool:
        return self._move_row("hidden_images", "images", image_id)

    def hidden_ids(self) -> list[int]:
        rows = self._db.query("SELECT id FROM hidden_images ORDER BY id")
        return [int(row["id"]) for row in rows]

    def ids_by_dir(self, dir_id: int) -> tuple[list[int], list[int]]:
        visible = [int(r["id"]) for r in self._db.query(
            "SELECT id FROM images WHERE dir_id=?", (dir_id,)
        )]
        hidden = [int(r["id"]) for r in self._db.query(
            "SELECT id FROM hidden_images WHERE dir_id=?", (dir_id,)
        )]
        return visible, hidden

    def delete_by_dir(self, dir_id: int) -> int:
        """注销目录：只清索引记录，不碰源文件。"""
        visible, hidden = self.ids_by_dir(dir_id)
        for image_id in [*visible, *hidden]:
            self.delete(image_id)
        return len(visible) + len(hidden)

    def mark_missing(self, dir_id: int, seen_paths: set[str]) -> int:
        """增量扫描：消失的文件标记 missing，不删记录。"""
        count = 0
        for table in ("images", "hidden_images"):
            for row in self._db.query(
                f"SELECT id, path FROM {table} WHERE dir_id=? AND missing=0", (dir_id,)
            ):
                if str(row["path"]) not in seen_paths:
                    self._db.execute(
                        f"UPDATE {table} SET missing=1, updated_at=? WHERE id=?",
                        (now_iso(), int(row["id"])),
                    )
                    count += 1
        return count

    def clear_missing(self, image_id: int) -> None:
        self._db.execute(
            "UPDATE images SET missing=0, updated_at=? WHERE id=?",
            (now_iso(), image_id),
        )

    # ---------- FTS 同步 ----------

    def fts_replace(
        self,
        image_id: int,
        filename: str,
        description: str,
        tags: list[str],
        elements: list[str],
        notes: str,
    ) -> None:
        from app.storage.helpers import tokenize

        self.fts_delete(image_id)
        self._db.execute(
            "INSERT INTO image_fts(image_id, filename, description, tags, elements, notes) "
            "VALUES(?,?,?,?,?,?)",
            (
                image_id,
                tokenize(filename),
                tokenize(description),
                tokenize(" ".join(tags)),
                tokenize(" ".join(elements)),
                tokenize(notes),
            ),
        )

    def fts_delete(self, image_id: int) -> None:
        self._db.execute("DELETE FROM image_fts WHERE image_id=?", (image_id,))

    def sync_fts(self, image_id: int) -> None:
        """从当前可见行重建 FTS（人工/标签/备注变更后调用）。"""
        image = self.get(image_id)
        if image is None:
            self.fts_delete(image_id)
            return
        description = image["description_manual"] or image["description_ai"] or ""
        tags = [row["name"] for row in self._db.query(
            "SELECT t.name FROM image_tags jt JOIN tags t ON t.id=jt.tag_id WHERE jt.image_id=?",
            (image_id,),
        )]
        tags += [row["tag"] for row in self._db.query(
            "SELECT tag FROM ai_tags WHERE image_id=?", (image_id,)
        )]
        elements = [row["element"] for row in self._db.query(
            "SELECT element FROM image_elements WHERE image_id=? ORDER BY rank", (image_id,)
        )]
        self.fts_replace(
            image_id, str(image["filename"]), str(description), tags, elements,
            str(image["notes"] or ""),
        )

    # ---------- 分析产出 ----------

    def add_analysis(
        self,
        image_id: int,
        *,
        category: str | None,
        description: str | None,
        has_text: bool,
        model: str,
        tokens_in: int,
        tokens_out: int,
    ) -> int:
        cursor = self._db.execute(
            "INSERT INTO analyses(image_id, category, description, has_text, model, "
            "tokens_in, tokens_out, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (image_id, category, description, int(has_text), model, tokens_in, tokens_out, now_iso()),
        )
        return int(cursor.lastrowid or 0)

    def replace_ai_tags(self, image_id: int, tags: list[str]) -> None:
        with self._db.tx():
            self._db.execute("DELETE FROM ai_tags WHERE image_id=?", (image_id,))
            for rank, tag in enumerate(tags[:5]):
                self._db.execute(
                    "INSERT OR IGNORE INTO ai_tags(image_id, tag, rank) VALUES(?,?,?)",
                    (image_id, tag, rank),
                )

    def replace_elements(self, image_id: int, elements: list[str]) -> None:
        with self._db.tx():
            self._db.execute("DELETE FROM image_elements WHERE image_id=?", (image_id,))
            for rank, element in enumerate(elements):
                self._db.execute(
                    "INSERT OR IGNORE INTO image_elements(image_id, element, rank) VALUES(?,?,?)",
                    (image_id, element, rank),
                )

    def set_ocr(self, image_id: int, text: str, model: str, tokens_out: int) -> None:
        self._db.execute(
            "INSERT INTO ocr_results(image_id, text, model, tokens_out, created_at) "
            "VALUES(?,?,?,?,?) "
            "ON CONFLICT(image_id) DO UPDATE SET text=excluded.text, model=excluded.model, "
            "tokens_out=excluded.tokens_out, created_at=excluded.created_at",
            (image_id, text, model, tokens_out, now_iso()),
        )

    def get_ocr_text(self, image_id: int) -> str:
        row = self._db.query_one("SELECT text FROM ocr_results WHERE image_id=?", (image_id,))
        return str(row["text"]) if row else ""

    def ai_tags_of(self, image_id: int) -> list[str]:
        return [str(row["tag"]) for row in self._db.query(
            "SELECT tag FROM ai_tags WHERE image_id=? ORDER BY rank", (image_id,)
        )]

    def elements_of(self, image_id: int) -> list[str]:
        return [str(row["element"]) for row in self._db.query(
            "SELECT element FROM image_elements WHERE image_id=? ORDER BY rank", (image_id,)
        )]

    def manual_tags_of(self, image_id: int) -> list[str]:
        return [str(row["name"]) for row in self._db.query(
            "SELECT t.name FROM image_tags jt JOIN tags t ON t.id=jt.tag_id "
            "WHERE jt.image_id=? ORDER BY t.name",
            (image_id,),
        )]

    def add_token_usage(
        self, image_id: int | None, purpose: str, model: str, tokens_in: int, tokens_out: int
    ) -> None:
        self._db.execute(
            "INSERT INTO token_usage(image_id, purpose, model, tokens_in, tokens_out, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (image_id, purpose, model, tokens_in, tokens_out, now_iso()),
        )

    def tokens_today(self, day_prefix: str) -> int:
        row = self._db.query_one(
            "SELECT COALESCE(SUM(tokens_in + tokens_out), 0) AS total FROM token_usage "
            "WHERE created_at LIKE ?",
            (f"{day_prefix}%",),
        )
        return int(row["total"]) if row else 0

    # ---------- 人工标签 ----------

    def set_manual_tags(self, image_id: int, tags: list[str]) -> None:
        with self._db.tx():
            self._db.execute("DELETE FROM image_tags WHERE image_id=?", (image_id,))
            for name in dict.fromkeys(tag.strip() for tag in tags if tag.strip()):
                self._db.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (name,))
                row = self._db.query_one("SELECT id FROM tags WHERE name=?", (name,))
                if row is not None:
                    self._db.execute(
                        "INSERT OR IGNORE INTO image_tags(image_id, tag_id) VALUES(?,?)",
                        (image_id, int(row["id"])),
                    )

    # ---------- 向量 ----------

    def set_vector(self, image_id: int, model: str, vector: npt.NDArray[np.float32]) -> None:
        blob = vector.astype("float32").tobytes()
        self._db.execute(
            "INSERT INTO image_vectors(image_id, model, dim, vector) VALUES(?,?,?,?) "
            "ON CONFLICT(image_id) DO UPDATE SET model=excluded.model, dim=excluded.dim, "
            "vector=excluded.vector",
            (image_id, model, int(vector.size), blob),
        )

    def get_vector(self, image_id: int) -> npt.NDArray[np.float32] | None:
        row = self._db.query_one(
            "SELECT vector, dim FROM image_vectors WHERE image_id=?", (image_id,)
        )
        if row is None:
            return None
        return np.frombuffer(bytes(row["vector"]), dtype=np.float32)

    def all_vectors(self) -> dict[int, npt.NDArray[np.float32]]:
        result: dict[int, npt.NDArray[np.float32]] = {}
        for row in self._db.query("SELECT image_id, vector FROM image_vectors"):
            result[int(row["image_id"])] = np.frombuffer(
                bytes(row["vector"]), dtype=np.float32
            )
        return result

    # ---------- 自定义字段值 ----------

    def set_custom_value(self, field_id: int, image_id: int, value: Any) -> None:
        if value is None or value == "":
            self._db.execute(
                "DELETE FROM custom_field_values WHERE field_id=? AND image_id=?",
                (field_id, image_id),
            )
            return
        value_text = str(value)
        value_num: float | None = None
        value_date: str | None = None
        try:
            value_num = float(value)
        except (TypeError, ValueError):
            value_num = None
        if isinstance(value, str) and len(value) == 10 and value[4] == "-":
            value_date = value
        self._db.execute(
            "INSERT INTO custom_field_values(field_id, image_id, value_text, value_num, value_date) "
            "VALUES(?,?,?,?,?) ON CONFLICT(field_id, image_id) DO UPDATE SET "
            "value_text=excluded.value_text, value_num=excluded.value_num, value_date=excluded.value_date",
            (field_id, image_id, value_text, value_num, value_date),
        )

    def custom_values_of(self, image_id: int) -> dict[str, Any]:
        rows = self._db.query(
            "SELECT f.id, f.name, f.type, v.value_text FROM custom_field_values v "
            "JOIN custom_fields f ON f.id=v.field_id WHERE v.image_id=?",
            (image_id,),
        )
        return {str(row["name"]): row["value_text"] for row in rows}
