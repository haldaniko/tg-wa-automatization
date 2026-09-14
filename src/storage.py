from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def init(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lead_messages (
                    row_key TEXT PRIMARY KEY,
                    phone TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    telegram_user_id INTEGER,
                    telegram_message_id INTEGER,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def get(self, row_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM lead_messages WHERE row_key = ?",
                (row_key,),
            ).fetchone()
        return dict(row) if row else None

    def claim(self, row_key: str, phone: str) -> str:
        now = _now()
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO lead_messages (row_key, phone, status, created_at, updated_at)
                    VALUES (?, ?, 'processing', ?, ?)
                    """,
                    (row_key, phone, now, now),
                )
                return "claimed"
            except sqlite3.IntegrityError:
                row = conn.execute(
                    "SELECT status FROM lead_messages WHERE row_key = ?",
                    (row_key,),
                ).fetchone()
                if row and row["status"] == "sent":
                    return "sent"
                if row and row["status"] == "processing":
                    return "processing"

                conn.execute(
                    """
                    UPDATE lead_messages
                    SET phone = ?, status = 'processing', error = NULL, updated_at = ?
                    WHERE row_key = ?
                    """,
                    (phone, now, row_key),
                )
                return "claimed"

    def mark_processing(self, row_key: str, phone: str) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO lead_messages (row_key, phone, status, created_at, updated_at)
                VALUES (?, ?, 'processing', ?, ?)
                ON CONFLICT(row_key) DO UPDATE SET
                    phone = excluded.phone,
                    status = CASE
                        WHEN lead_messages.status = 'sent' THEN lead_messages.status
                        ELSE 'processing'
                    END,
                    error = NULL,
                    updated_at = excluded.updated_at
                """,
                (row_key, phone, now, now),
            )

    def mark_sent(
        self,
        row_key: str,
        phone: str,
        message: str,
        telegram_user_id: int | None,
        telegram_message_id: int | None,
    ) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE lead_messages
                SET phone = ?,
                    status = 'sent',
                    message = ?,
                    telegram_user_id = ?,
                    telegram_message_id = ?,
                    error = NULL,
                    updated_at = ?
                WHERE row_key = ?
                """,
                (phone, message, telegram_user_id, telegram_message_id, now, row_key),
            )

    def mark_failed(self, row_key: str, phone: str, error: str) -> None:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE lead_messages
                SET phone = ?, status = 'failed', error = ?, updated_at = ?
                WHERE row_key = ?
                """,
                (phone, error[:2000], now, row_key),
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn
