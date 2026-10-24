"""SQLite storage for conversations, leads and bookings. One file, no server."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    messages TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    name TEXT,
    phone TEXT,
    interest TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    service TEXT NOT NULL,
    start TEXT NOT NULL,
    minutes INTEGER NOT NULL,
    calendar_event_id TEXT,
    status TEXT NOT NULL DEFAULT 'confirmed'
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str = "frontdesk.db"):
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        # FastAPI runs requests on several threads; one connection must not be used by two at once.
        self._lock = threading.RLock()

    # conversations -------------------------------------------------------
    def new_conversation(self) -> str:
        with self._lock:
            cid = uuid.uuid4().hex[:12]
            self.conn.execute("INSERT INTO conversations (id, started_at) VALUES (?, ?)", (cid, _now()))
            self.conn.commit()
            return cid

    def get_messages(self, cid: str) -> list[dict] | None:
        with self._lock:
            row = self.conn.execute("SELECT messages FROM conversations WHERE id = ?", (cid,)).fetchone()
            return json.loads(row["messages"]) if row else None

    def save_messages(self, cid: str, messages: list[dict]) -> None:
        with self._lock:
            self.conn.execute("UPDATE conversations SET messages = ? WHERE id = ?", (json.dumps(messages), cid))
            self.conn.commit()

    # leads ---------------------------------------------------------------
    def save_lead(self, cid: str, name: str | None, phone: str | None, interest: str | None,
                  notes: str | None = None) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO leads (conversation_id, created_at, name, phone, interest, notes) VALUES (?,?,?,?,?,?)",
                (cid, _now(), name, phone, interest, notes))
            self.conn.commit()
            return int(cur.lastrowid)

    # bookings ------------------------------------------------------------
    def save_booking(self, cid: str, name: str, phone: str, service: str, start: str,
                     minutes: int, calendar_event_id: str | None) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO bookings (conversation_id, created_at, name, phone, service, start, minutes, calendar_event_id)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (cid, _now(), name, phone, service, start, minutes, calendar_event_id))
            self.conn.commit()
            return int(cur.lastrowid)

    def list_bookings(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM bookings ORDER BY start DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def list_leads(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM leads ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]
