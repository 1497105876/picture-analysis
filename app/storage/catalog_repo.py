"""分类字典 / 规则 / 智能相册 / 提案 / 自定义字段 / 同义词 仓储。"""

from __future__ import annotations

from typing import Any

from app.domain.categories import BUILTIN_CATEGORIES
from app.storage.db import Database, now_iso
from app.storage.helpers import dumps, loads, rows_to_dicts


class CatalogRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def seed_categories(self) -> None:
        for sort, seed in enumerate(BUILTIN_CATEGORIES, start=1):
            self._db.execute(
                "INSERT OR IGNORE INTO categories(name, color, emoji, builtin, active, sort) "
                "VALUES(?,?,?,1,1,?)",
                (seed.name, seed.color, seed.emoji, sort),
            )

    # ---------- 分类 ----------

    def list_categories(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        # usage = 当前打上这个分类的图片数，删除/停用前先让人看到影响面
        sql = (
            "SELECT c.*, "
            "(SELECT COUNT(*) FROM images i "
            " WHERE COALESCE(i.category_manual, i.category_ai) = c.name) AS usage "
            "FROM categories c"
        )
        if not include_inactive:
            sql += " WHERE c.active=1"
        return rows_to_dicts(self._db.query(sql + " ORDER BY c.sort, c.id"))

    def add_category(self, name: str, color: str, emoji: str) -> int:
        cursor = self._db.execute(
            "INSERT INTO categories(name, color, emoji, builtin, active, sort) VALUES(?,?,?,0,1,?)",
            (name, color, emoji, 100),
        )
        return int(cursor.lastrowid or 0)

    def get_category(self, name: str) -> dict[str, Any] | None:
        row = self._db.query_one("SELECT * FROM categories WHERE name=?", (name,))
        return dict(row) if row else None

    def update_category(self, where: str, **fields: Any) -> None:
        allowed = {"name", "color", "emoji", "active", "sort"}
        pairs = [(k, v) for k, v in fields.items() if k in allowed]
        if not pairs:
            return
        columns = ", ".join(f"{k}=?" for k, _ in pairs)
        self._db.execute(
            f"UPDATE categories SET {columns} WHERE name=?",
            tuple([v for _, v in pairs] + [where]),
        )

    def reassign_category(self, old: str, new: str) -> None:
        """重命名/合并：级联全部图片（人工位 + AI 位）与规则/相册。"""
        with self._db.tx():
            for table in ("images", "hidden_images"):
                self._db.execute(
                    f"UPDATE {table} SET category_manual=? WHERE category_manual=?",
                    (new, old),
                )
                self._db.execute(
                    f"UPDATE {table} SET category_ai=? WHERE category_ai=?",
                    (new, old),
                )

    # ---------- 规则 ----------

    def list_rules(self) -> list[dict[str, Any]]:
        rows = rows_to_dicts(self._db.query("SELECT * FROM rules ORDER BY priority, id"))
        for row in rows:
            row["condition"] = loads(row.pop("condition_json"), {})
            row["action"] = loads(row.pop("action_json"), {})
        return rows

    def add_rule(
        self,
        name: str,
        priority: int,
        condition: dict[str, Any],
        action: dict[str, Any],
        enabled: bool = True,
    ) -> int:
        cursor = self._db.execute(
            "INSERT INTO rules(name, priority, enabled, condition_json, action_json, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (name, priority, int(enabled), dumps(condition), dumps(action), now_iso()),
        )
        return int(cursor.lastrowid or 0)

    def update_rule(self, rule_id: int, **fields: Any) -> None:
        mapping = {
            "name": "name",
            "priority": "priority",
            "enabled": "enabled",
            "condition": "condition_json",
            "action": "action_json",
        }
        pairs: list[tuple[str, Any]] = []
        for key, value in fields.items():
            column = mapping.get(key)
            if column is None:
                continue
            pairs.append((column, dumps(value) if column.endswith("_json") else value))
        if not pairs:
            return
        columns = ", ".join(f"{c}=?" for c, _ in pairs)
        self._db.execute(
            f"UPDATE rules SET {columns} WHERE id=?",
            tuple(v for _, v in pairs) + (rule_id,),
        )

    def delete_rule(self, rule_id: int) -> None:
        self._db.execute("DELETE FROM rules WHERE id=?", (rule_id,))

    # ---------- 智能相册 ----------

    def list_albums(self) -> list[dict[str, Any]]:
        rows = rows_to_dicts(self._db.query("SELECT * FROM smart_albums ORDER BY id"))
        for row in rows:
            row["query"] = loads(row.pop("query_json"), {})
            row["sort"] = loads(row.pop("sort_json"), {})
        return rows

    def add_album(self, name: str, query: dict[str, Any], sort: dict[str, Any]) -> int:
        cursor = self._db.execute(
            "INSERT INTO smart_albums(name, query_json, sort_json, created_at) VALUES(?,?,?,?)",
            (name, dumps(query), dumps(sort), now_iso()),
        )
        return int(cursor.lastrowid or 0)

    def delete_album(self, album_id: int) -> None:
        self._db.execute("DELETE FROM smart_albums WHERE id=?", (album_id,))

    def get_album(self, album_id: int) -> dict[str, Any] | None:
        row = self._db.query_one("SELECT * FROM smart_albums WHERE id=?", (album_id,))
        if row is None:
            return None
        data = dict(row)
        data["query"] = loads(data.pop("query_json"), {})
        data["sort"] = loads(data.pop("sort_json"), {})
        return data

    # ---------- 提案队列 ----------

    def add_proposal(
        self, ptype: str, payload: dict[str, Any], source: str, image_id: int | None = None
    ) -> int:
        cursor = self._db.execute(
            "INSERT INTO proposals(type, payload_json, source, image_id, created_at) "
            "VALUES(?,?,?,?,?)",
            (ptype, dumps(payload), source, image_id, now_iso()),
        )
        return int(cursor.lastrowid or 0)

    def list_proposals(self, status: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM proposals"
        params: tuple[Any, ...] = ()
        if status:
            sql += " WHERE status=?"
            params = (status,)
        rows = rows_to_dicts(self._db.query(sql + " ORDER BY id DESC", params))
        for row in rows:
            row["payload"] = loads(row.pop("payload_json"), {})
        return rows

    def decide_proposal(self, proposal_id: int, status: str) -> dict[str, Any] | None:
        self._db.execute(
            "UPDATE proposals SET status=?, decided_at=? WHERE id=?",
            (status, now_iso(), proposal_id),
        )
        row = self._db.query_one("SELECT * FROM proposals WHERE id=?", (proposal_id,))
        if row is None:
            return None
        data = dict(row)
        data["payload"] = loads(data.pop("payload_json"), {})
        return data

    # ---------- 自定义字段定义 ----------

    def list_custom_fields(self) -> list[dict[str, Any]]:
        rows = rows_to_dicts(
            self._db.query(
                "SELECT f.*, "
                "(SELECT COUNT(*) FROM custom_field_values v WHERE v.field_id=f.id) AS usage "
                "FROM custom_fields f ORDER BY f.sort, f.id"
            )
        )
        for row in rows:
            row["options"] = loads(row.pop("options_json"), [])
        return rows

    def add_custom_field(self, name: str, ftype: str, options: list[str]) -> int:
        cursor = self._db.execute(
            "INSERT INTO custom_fields(name, type, options_json, sort) VALUES(?,?,?,?)",
            (name, ftype, dumps(options), 100),
        )
        return int(cursor.lastrowid or 0)

    def delete_custom_field(self, field_id: int) -> None:
        self._db.execute("DELETE FROM custom_fields WHERE id=?", (field_id,))

    def get_custom_field(self, field_id: int) -> dict[str, Any] | None:
        row = self._db.query_one("SELECT * FROM custom_fields WHERE id=?", (field_id,))
        if row is None:
            return None
        data = dict(row)
        data["options"] = loads(data.pop("options_json"), [])
        return data

    # ---------- 同义词 / 术语权重 ----------

    def add_synonym_group(self, group_name: str, terms: list[str]) -> None:
        with self._db.tx():
            self._db.execute("DELETE FROM synonyms WHERE group_name=?", (group_name,))
            for term in terms:
                self._db.execute(
                    "INSERT INTO synonyms(group_name, term) VALUES(?,?)", (group_name, term)
                )

    def list_synonym_groups(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for row in self._db.query("SELECT group_name, term FROM synonyms ORDER BY id"):
            result.setdefault(str(row["group_name"]), []).append(str(row["term"]))
        return result

    def delete_synonym_group(self, group_name: str) -> bool:
        cursor = self._db.execute("DELETE FROM synonyms WHERE group_name=?", (group_name,))
        return int(cursor.rowcount or 0) > 0

    def set_term_weight(self, term: str, weight: float) -> None:
        self._db.execute(
            "INSERT INTO term_weights(term, weight) VALUES(?,?) "
            "ON CONFLICT(term) DO UPDATE SET weight=excluded.weight",
            (term, weight),
        )

    def delete_term_weight(self, term: str) -> bool:
        cursor = self._db.execute("DELETE FROM term_weights WHERE term=?", (term,))
        return int(cursor.rowcount or 0) > 0
