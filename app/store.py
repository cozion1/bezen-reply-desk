"""SQLite storage: replies, their step-by-step trace, and the follow-up queue."""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

DB_PATH = os.environ.get("REPLY_DESK_DB", os.path.join(os.path.dirname(__file__), "..", "data", "desk.db"))
_lock = threading.Lock()


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _lock, _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS replies (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              received_at TEXT NOT NULL,
              text TEXT NOT NULL,
              lead TEXT NOT NULL DEFAULT '{}',
              status TEXT NOT NULL DEFAULT 'new',
              reading TEXT,
              final_message TEXT,
              decided_by TEXT,
              follow_up_on TEXT
            );
            CREATE TABLE IF NOT EXISTS steps (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              reply_id INTEGER NOT NULL,
              at TEXT NOT NULL,
              step TEXT NOT NULL,
              detail TEXT NOT NULL
            );
            """
        )


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["lead"] = json.loads(d["lead"] or "{}")
    d["reading"] = json.loads(d["reading"]) if d["reading"] else None
    return d


def add_reply(text: str, lead: dict) -> int:
    with _lock, _conn() as c:
        cur = c.execute("INSERT INTO replies (received_at, text, lead) VALUES (?, ?, ?)", (now(), text, json.dumps(lead)))
        rid = cur.lastrowid
        c.execute("INSERT INTO steps (reply_id, at, step, detail) VALUES (?, ?, 'intake', ?)",
                  (rid, now(), f"Reply received from {lead.get('company', 'unknown lead')}."))
        return rid


def log_step(reply_id: int, step: str, detail: str) -> None:
    with _lock, _conn() as c:
        c.execute("INSERT INTO steps (reply_id, at, step, detail) VALUES (?, ?, ?, ?)", (reply_id, now(), step, detail))


def update(reply_id: int, **fields) -> None:
    if "reading" in fields and fields["reading"] is not None:
        fields["reading"] = json.dumps(fields["reading"])
    cols = ", ".join(f"{k} = ?" for k in fields)
    with _lock, _conn() as c:
        c.execute(f"UPDATE replies SET {cols} WHERE id = ?", (*fields.values(), reply_id))


def get(reply_id: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM replies WHERE id = ?", (reply_id,)).fetchone()
        if not r:
            return None
        d = _row(r)
        d["steps"] = [dict(s) for s in c.execute("SELECT at, step, detail FROM steps WHERE reply_id = ? ORDER BY id", (reply_id,))]
        return d


def all_replies() -> list[dict]:
    with _conn() as c:
        return [_row(r) for r in c.execute("SELECT * FROM replies ORDER BY id DESC")]


def clear() -> None:
    with _lock, _conn() as c:
        c.execute("DELETE FROM steps")
        c.execute("DELETE FROM replies")
