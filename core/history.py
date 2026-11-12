"""Historial de descargas persistido en SQLite."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from core.models import Job
from core.utils import data_home, ensure_dirs


class HistoryStore:
    def __init__(self, path: Path | None = None) -> None:
        ensure_dirs()
        self.path = path or (data_home() / "history.db")
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    uploader TEXT,
                    fmt TEXT NOT NULL,
                    quality TEXT,
                    filepath TEXT,
                    size INTEGER DEFAULT 0,
                    duration REAL DEFAULT 0,
                    thumbnail TEXT,
                    completed_at REAL NOT NULL,
                    favorite INTEGER DEFAULT 0
                )
                """
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_downloads_completed ON downloads(completed_at DESC)")
            self._conn.commit()

    def add(self, job: Job) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO downloads (job_id, url, title, uploader, fmt, quality, filepath, size,
                                       duration, thumbnail, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.url,
                    job.title or job.display_title,
                    job.uploader,
                    job.fmt.value,
                    job.options.quality,
                    job.filepath,
                    job.size,
                    job.duration,
                    job.thumbnail_url,
                    time.time(),
                ),
            )
            self._conn.commit()

    def list(self, search: str = "", kind: str = "all", favorites: bool = False, sort: str = "recent") -> list[dict]:
        clauses = ["1=1"]
        params: list = []
        if search:
            clauses.append("(title LIKE ? OR uploader LIKE ? OR filepath LIKE ?)")
            like = f"%{search}%"
            params += [like, like, like]
        if kind == "audio":
            clauses.append("fmt != 'mp4'")
        elif kind == "video":
            clauses.append("fmt = 'mp4'")
        if favorites:
            clauses.append("favorite = 1")
        order = {
            "recent": "completed_at DESC",
            "oldest": "completed_at ASC",
            "title": "title COLLATE NOCASE ASC",
            "size": "size DESC",
        }.get(sort, "completed_at DESC")
        query = f"SELECT * FROM downloads WHERE {' AND '.join(clauses)} ORDER BY {order} LIMIT 800"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def stats(self) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS count, COALESCE(SUM(size), 0) AS total_size FROM downloads"
            ).fetchone()
            formats = self._conn.execute(
                "SELECT fmt, COUNT(*) AS count FROM downloads GROUP BY fmt ORDER BY count DESC"
            ).fetchall()
        return {
            "count": row["count"] if row else 0,
            "total_size": row["total_size"] if row else 0,
            "formats": [dict(r) for r in formats],
        }

    def set_favorite(self, entry_id: int, favorite: bool) -> None:
        with self._lock:
            self._conn.execute("UPDATE downloads SET favorite = ? WHERE id = ?", (1 if favorite else 0, entry_id))
            self._conn.commit()

    def delete(self, entry_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM downloads WHERE id = ?", (entry_id,))
            self._conn.commit()

    def clear(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM downloads")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
