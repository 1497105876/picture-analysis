"""SQLite 连接与迁移：单连接 + 锁 + WAL（单机单进程写者模型）。"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Sequence, cast

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self.migrate()

    def migrate(self) -> None:
        current = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        with self._lock:
            for file in files:
                version = int(file.name.split("_", 1)[0])
                if version > current:
                    self._conn.executescript(file.read_text(encoding="utf-8"))
                    self._conn.execute(f"PRAGMA user_version={version}")
            self._conn.commit()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.execute(sql, params)
            self._conn.commit()
            return cursor

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            row: Any = self._conn.execute(sql, params).fetchone()
            return cast(sqlite3.Row | None, row)

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self.query_one(sql, params)
        return row[0] if row is not None else None

    @contextmanager
    def tx(self) -> Iterator[None]:
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                yield
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()
