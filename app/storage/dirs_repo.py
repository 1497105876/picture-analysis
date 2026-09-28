"""directories 表仓储：手动登记目录的唯一读写入口。"""
from __future__ import annotations

import json
from typing import Any

from app.storage.db import Database, now_iso
from app.storage.helpers import loads, rows_to_dicts


class DirectoriesRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(
        self,
        path: str,
        *,
        recursive: bool = True,
        privacy: bool = False,
        ocr_policy: str = "auto",
        watcher: bool = False,
        source: str = "manual",
        profile: dict[str, Any] | None = None,
    ) -> int:
        self._db.execute(
            """INSERT INTO directories(path, recursive, privacy, ocr_policy, watcher, source,
                                       profile_json, created_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(path) DO UPDATE SET recursive=excluded.recursive,
                                               privacy=excluded.privacy,
                                               ocr_policy=excluded.ocr_policy,
                                               watcher=excluded.watcher""",
            (path, int(recursive), int(privacy), ocr_policy, int(watcher), source,
             json.dumps(profile or {}, ensure_ascii=False), now_iso()),
        )
        row = self._db.query_one("SELECT id FROM directories WHERE path=?", (path,))
        if row is None:
            raise KeyError(path)
        return int(row["id"])

    def get(self, dir_id: int) -> dict[str, Any] | None:
        row = self._db.query_one("SELECT * FROM directories WHERE id=?", (dir_id,))
        if row is None:
            return None
        data = dict(row)
        data["profile"] = loads(data.pop("profile_json"), {})
        return data

    def get_by_path(self, path: str) -> dict[str, Any]:
        row = self._db.query_one("SELECT * FROM directories WHERE path=?", (path,))
        if row is None:
            raise KeyError(path)
        data = dict(row)
        data["profile"] = loads(data.pop("profile_json"), {})
        return data

    def list(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for data in rows_to_dicts(self._db.query("SELECT * FROM directories ORDER BY id")):
            data["profile"] = loads(data.pop("profile_json"), {})
            result.append(data)
        return result

    def update(self, dir_id: int, **fields: Any) -> None:
        allowed = {"recursive", "enabled", "offline", "privacy", "frozen", "watcher",
                   "ocr_policy", "last_scanned_at", "profile_json"}
        pairs = [(key, value) for key, value in fields.items() if key in allowed]
        if not pairs:
            return
        columns = ", ".join(f"{key}=?" for key, _ in pairs)
        values = [value for _, value in pairs]
        self._db.execute(
            f"UPDATE directories SET {columns} WHERE id=?", (*values, dir_id)
        )

    def remove(self, dir_id: int) -> None:
        self._db.execute("DELETE FROM directories WHERE id=?", (dir_id,))

    def set_profile(self, dir_id: int, profile: dict[str, Any]) -> None:
        self._db.execute(
            "UPDATE directories SET profile_json=? WHERE id=?",
            (json.dumps(profile, ensure_ascii=False), dir_id),
        )
