from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class ReplayStore:
    """SQLite-only replay metadata store; it never receives secret values."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_nonces (
                    nonce TEXT PRIMARY KEY,
                    request_timestamp INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_seen_nonces_expires_at ON seen_nonces(expires_at)"
            )

    def claim(self, nonce: str, request_timestamp: int, ttl_seconds: int) -> bool:
        now = int(time.time())
        expires_at = request_timestamp + ttl_seconds
        with self._connect() as connection:
            connection.execute("DELETE FROM seen_nonces WHERE expires_at < ?", (now,))
            try:
                connection.execute(
                    "INSERT INTO seen_nonces(nonce, request_timestamp, expires_at, created_at) VALUES (?, ?, ?, ?)",
                    (nonce, request_timestamp, expires_at, now),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute("PRAGMA busy_timeout=5000")
        return connection
