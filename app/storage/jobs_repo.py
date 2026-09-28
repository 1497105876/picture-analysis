"""任务队列仓储（jobs / job_events）。"""
from __future__ import annotations

import json
import time
from typing import Any

from app.storage.db import Database, now_iso
from app.storage.helpers import loads, rows_to_dicts


class JobsRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    def enqueue(
        self,
        job_type: str,
        *,
        image_id: int | None = None,
        dir_id: int | None = None,
        priority: int = 0,
        payload: dict[str, Any] | None = None,
        max_attempts: int = 3,
        dedupe: bool = True,
    ) -> int:
        if dedupe:
            existing = self._db.query_one(
                "SELECT id FROM jobs WHERE type=? AND COALESCE(image_id,-1)=COALESCE(?,-1) "
                "AND state IN ('pending','running','paused')",
                (job_type, image_id),
            )
            if existing is not None:
                return int(existing["id"])
        now = now_iso()
        cursor = self._db.execute(
            "INSERT INTO jobs(type, image_id, dir_id, state, priority, payload_json, "
            "max_attempts, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (job_type, image_id, dir_id, "pending", priority,
             json.dumps(payload or {}, ensure_ascii=False), max_attempts, now, now),
        )
        return int(cursor.lastrowid or 0)

    def get(self, job_id: int) -> dict[str, Any] | None:
        row = self._db.query_one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if row is None:
            return None
        data = dict(row)
        data["payload"] = loads(data.pop("payload_json"), {})
        return data

    def rows(self, state: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        sql = "SELECT * FROM jobs"
        params: tuple[Any, ...] = ()
        if state:
            sql += " WHERE state=?"
            params = (state,)
        rows = rows_to_dicts(self._db.query(sql + " ORDER BY id DESC LIMIT ?", (*params, limit)))
        for row in rows:
            row["payload"] = loads(row.pop("payload_json"), {})
        return rows

    def next_pending(self) -> dict[str, Any] | None:
        row = self._db.query_one(
            "SELECT * FROM jobs WHERE state='pending' AND (retry_at IS NULL OR retry_at<=?) "
            "ORDER BY priority DESC, id ASC LIMIT 1",
            (time.time(),),
        )
        if row is None:
            return None
        data = dict(row)
        data["payload"] = loads(data.pop("payload_json"), {})
        return data

    def claim(self, job_id: int) -> bool:
        """原子占用（pending→running），多 worker 下防抢单。"""
        cursor = self._db.execute(
            "UPDATE jobs SET state='running', updated_at=? WHERE id=? AND state='pending'",
            (now_iso(), job_id),
        )
        return cursor.rowcount > 0

    def find(self, job_id: int) -> dict[str, Any] | None:
        return self.get(job_id)

    def update_payload(self, job_id: int, payload: dict[str, Any]) -> None:
        self._db.execute(
            "UPDATE jobs SET payload_json=? WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), job_id),
        )

    def transition(
        self, job_id: int, state: str, *, error: str | None = None,
        retry_at: float | None = None, bump_attempt: bool = False,
    ) -> None:
        sets = ["state=?", "updated_at=?"]
        params: list[Any] = [state, now_iso()]
        if error is not None:
            sets.append("error=?")
            params.append(error)
        if retry_at is not None:
            sets.append("retry_at=?")
            params.append(retry_at)
        if bump_attempt:
            sets.append("attempts=attempts+1")
        params.append(job_id)
        self._db.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id=?", tuple(params))

    def reset_running(self) -> None:
        """进程重启：running 复位 pending（断点续跑）。"""
        self._db.execute(
            "UPDATE jobs SET state='pending', updated_at=? WHERE state='running'",
            (now_iso(),),
        )

    def counts(self) -> dict[str, int]:
        rows = self._db.query("SELECT state, COUNT(*) AS c FROM jobs GROUP BY state")
        return {str(row["state"]): int(row["c"]) for row in rows}

    def add_event(self, job_id: int, message: str, level: str = "info") -> None:
        self._db.execute(
            "INSERT INTO job_events(job_id, level, message, created_at) VALUES(?,?,?,?)",
            (job_id, level, message, now_iso()),
        )

    def events(self, job_id: int, limit: int = 100) -> list[dict[str, Any]]:
        return rows_to_dicts(self._db.query(
            "SELECT * FROM job_events WHERE job_id=? ORDER BY id DESC LIMIT ?",
            (job_id, limit),
        ))

    def clear_finished(self) -> int:
        cursor = self._db.execute(
            "DELETE FROM jobs WHERE state IN ('succeeded','dead')"
        )
        return cursor.rowcount
