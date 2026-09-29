"""Every run, saved to SQLite so the report and history survive a restart."""

import json
import sqlite3
import threading

from config import DB_PATH

_lock = threading.Lock()
_COLUMNS = ("id", "created_at", "finished_at", "status", "issuer", "wallet", "verifier", "format", "scenario",
            "proof_type", "expected", "result", "verdict", "error")


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    with _lock, _connect() as conn:
        conn.execute(f"""CREATE TABLE IF NOT EXISTS runs (
            {', '.join(c + ' TEXT' for c in _COLUMNS)},
            doc TEXT NOT NULL,
            PRIMARY KEY (id))""")


def save(run: dict):
    outcome = run.get("outcome") or {}
    row = {
        **{c: run.get(c) for c in _COLUMNS},
        "expected": outcome.get("expected"),
        "result": outcome.get("result"),
        "verdict": outcome.get("verdict"),
    }
    with _lock, _connect() as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO runs ({', '.join(_COLUMNS)}, doc) VALUES ({', '.join('?' * len(_COLUMNS))}, ?)",
            [row[c] for c in _COLUMNS] + [json.dumps(run, default=str)])


def get(run_id: str):
    with _lock, _connect() as conn:
        r = conn.execute("SELECT doc FROM runs WHERE id = ?", (run_id,)).fetchone()
    return json.loads(r["doc"]) if r else None


def history(limit: int = 500) -> list:
    """Summary rows, newest first. Filtering happens in the UI; this list stays small."""
    with _lock, _connect() as conn:
        rows = conn.execute("SELECT doc FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        run = json.loads(r["doc"])
        out.append({k: run.get(k) for k in (
            "id", "created_at", "finished_at", "duration_ms", "status", "issuer", "wallet", "verifier", "format",
            "scenario", "proof_type", "outcome", "error", "versions", "suspected_gaps", "unsupported")})
    return out


def clear():
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM runs")
