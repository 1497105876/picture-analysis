"""设置 / 审计 / 通知 / 统计 / 重复组 仓储。"""
from __future__ import annotations

import json
from typing import Any

from app.storage.db import Database, now_iso
from app.storage.helpers import loads, rows_to_dicts


class SettingsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def all(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for row in self._db.query("SELECT key, value_json FROM settings"):
            result[str(row["key"])] = loads(row["value_json"], None)
        return result

    def get(self, key: str, default: Any = None) -> Any:
        row = self._db.query_one("SELECT value_json FROM settings WHERE key=?", (key,))
        if row is None:
            return default
        value = loads(row["value_json"], default)
        return default if value is None else value

    def set(self, key: str, value: Any, action: str = "update") -> None:
        before = self.get(key, None)
        self._db.execute(
            "INSERT INTO settings(key, value_json, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, "
            "updated_at=excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), now_iso()),
        )
        self._db.execute(
            "INSERT INTO audit_log(scope, key, before_json, after_json, action, created_at) "
            "VALUES('settings',?,?,?,?,?)",
            (key,
             json.dumps(before, ensure_ascii=False) if before is not None else None,
             json.dumps(value, ensure_ascii=False), action, now_iso()),
        )

    def audit(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = rows_to_dicts(self._db.query(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ))
        for row in rows:
            row["before"] = loads(row.pop("before_json"), None)
            row["after"] = loads(row.pop("after_json"), None)
        return rows

    def rollback(self, audit_id: int) -> bool:
        row = self._db.query_one("SELECT * FROM audit_log WHERE id=?", (audit_id,))
        if row is None:
            return False
        before = loads(row["before_json"], None)
        if before is None:
            self._db.execute("DELETE FROM settings WHERE key=?", (row["key"],))
        else:
            self.set(str(row["key"]), before, action="rollback")
        return True

    # ---------- 站内通知 ----------

    def notice(self, kind: str, message: str, level: str = "info") -> None:
        self._db.execute(
            "INSERT INTO notices(kind, level, message, created_at) VALUES(?,?,?,?)",
            (kind, level, message, now_iso()),
        )

    def notices(self, limit: int = 50) -> list[dict[str, Any]]:
        return rows_to_dicts(self._db.query(
            "SELECT * FROM notices ORDER BY id DESC LIMIT ?", (limit,)
        ))

    def clear_notices(self) -> None:
        self._db.execute("DELETE FROM notices")


class StatsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def dashboard(self) -> dict[str, Any]:
        total = int(self._db.scalar("SELECT COUNT(*) FROM images") or 0)
        by_category = [
            {"category": row["cat"] or "未分类", "count": int(row["c"])}
            for row in self._db.query(
                "SELECT COALESCE(category_manual, category_ai) AS cat, COUNT(*) AS c "
                "FROM images GROUP BY cat ORDER BY c DESC"
            )
        ]
        monthly = [
            {"month": row["m"] or "未知", "count": int(row["c"])}
            for row in self._db.query(
                "SELECT substr(COALESCE(exif_taken_at, created_at), 1, 7) AS m, COUNT(*) AS c "
                "FROM images GROUP BY m ORDER BY m DESC LIMIT 24"
            )
        ]
        storage = [
            {"dir_id": int(row["dir_id"]), "path": row["path"], "bytes": int(row["b"] or 0),
             "count": int(row["c"])}
            for row in self._db.query(
                "SELECT i.dir_id, d.path, SUM(i.bytes) AS b, COUNT(*) AS c "
                "FROM images i JOIN directories d ON d.id=i.dir_id "
                "GROUP BY i.dir_id ORDER BY b DESC LIMIT 20"
            )
        ]
        states = {
            str(row["analysis_state"]): int(row["c"])
            for row in self._db.query(
                "SELECT analysis_state, COUNT(*) AS c FROM images GROUP BY analysis_state"
            )
        }
        tokens = int(self._db.scalar("SELECT COALESCE(SUM(tokens_in+tokens_out),0) FROM token_usage") or 0)
        hidden = int(self._db.scalar("SELECT COUNT(*) FROM hidden_images") or 0)
        return {
            "total": total,
            "hidden": hidden,
            "by_category": by_category,
            "monthly": monthly,
            "storage": storage,
            "analysis_states": states,
            "tokens_total": tokens,
        }

    def md5_duplicate_groups(self) -> list[dict[str, Any]]:
        rows = self._db.query(
            "SELECT md5, COUNT(*) AS c FROM images GROUP BY md5 HAVING c > 1"
        )
        groups: list[dict[str, Any]] = []
        for row in rows:
            images = rows_to_dicts(self._db.query(
                "SELECT id, path, filename, bytes, mtime FROM images WHERE md5=? ORDER BY id",
                (row["md5"],),
            ))
            groups.append({"md5": row["md5"], "images": images})
        return groups

    def all_dhashes(self) -> list[dict[str, Any]]:
        return rows_to_dicts(
            self._db.query("SELECT id, path, dhash FROM images WHERE dhash <> ''")
        )
