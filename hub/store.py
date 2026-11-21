"""SQLite storage. One connection shared across request threads, serialised by a lock."""

from __future__ import annotations

import gzip
import hashlib
import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS participants (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    team TEXT NOT NULL,
    team_key TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    started_at TEXT,
    uploaded_at INTEGER NOT NULL,
    metrics TEXT NOT NULL,
    map BLOB NOT NULL,
    PRIMARY KEY (participant_id, session_id)
);
CREATE TABLE IF NOT EXISTS snapshots (
    participant_id INTEGER NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
    ts INTEGER NOT NULL,
    metrics TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS snapshots_by_participant ON snapshots (participant_id, ts);
CREATE TABLE IF NOT EXISTS badge_state (
    subject TEXT NOT NULL,
    badge TEXT NOT NULL,
    tier INTEGER NOT NULL,
    PRIMARY KEY (subject, badge)
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sync_status (
    participant_id INTEGER PRIMARY KEY REFERENCES participants(id) ON DELETE CASCADE,
    ts INTEGER NOT NULL,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""

SNAPSHOT_MIN_GAP_S = 60
SNAPSHOT_KEEP_S = 72 * 3600
EVENTS_KEEP = 1000


def key(s: str) -> str:
    return " ".join(s.split()).casefold()


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class NameTaken(Exception):
    pass


class Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self.version = 0  # bumped on every write that changes the leaderboard

    # -- participants -------------------------------------------------------
    def register(self, name: str, team: str) -> tuple[dict[str, Any], str]:
        token = secrets.token_urlsafe(24)
        with self.lock:
            try:
                cur = self.db.execute(
                    "INSERT INTO participants (name, name_key, team, team_key, token_hash, created_at) VALUES (?,?,?,?,?,?)",
                    (name, key(name), team, key(team), hash_token(token), int(time.time())),
                )
            except sqlite3.IntegrityError as exc:
                raise NameTaken(name) from exc
            self.version += 1
            return {"id": cur.lastrowid, "name": name, "team": team}, token

    def by_token(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        with self.lock:
            row = self.db.execute("SELECT id, name, team FROM participants WHERE token_hash=?", (hash_token(token),)).fetchone()
        return dict(row) if row else None

    def by_name(self, name: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.db.execute("SELECT id, name, team FROM participants WHERE name_key=?", (key(name),)).fetchone()
        return dict(row) if row else None

    def reissue(self, name: str) -> str | None:
        token = secrets.token_urlsafe(24)
        with self.lock:
            cur = self.db.execute("UPDATE participants SET token_hash=? WHERE name_key=?", (hash_token(token), key(name)))
        return token if cur.rowcount else None

    def remove(self, name: str) -> bool:
        with self.lock:
            cur = self.db.execute("DELETE FROM participants WHERE name_key=?", (key(name),))
            if cur.rowcount:
                self.version += 1
        return bool(cur.rowcount)

    def participants(self) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT id, name, team, team_key, created_at FROM participants")]

    # -- sessions -----------------------------------------------------------
    def upsert_session(self, pid: int, session_id: str, content_hash: str, started_at: str | None,
                       metrics: dict[str, Any], doc: dict[str, Any]) -> bool:
        """Store a session map; returns False when the same content was already stored."""
        blob = gzip.compress(json.dumps(doc, separators=(",", ":")).encode("utf-8"))
        with self.lock:
            row = self.db.execute(
                "SELECT content_hash FROM sessions WHERE participant_id=? AND session_id=?", (pid, session_id)
            ).fetchone()
            if row and row["content_hash"] == content_hash:
                return False
            self.db.execute(
                "INSERT INTO sessions (participant_id, session_id, content_hash, started_at, uploaded_at, metrics, map)"
                " VALUES (?,?,?,?,?,?,?) ON CONFLICT (participant_id, session_id) DO UPDATE SET"
                " content_hash=excluded.content_hash, started_at=excluded.started_at,"
                " uploaded_at=excluded.uploaded_at, metrics=excluded.metrics, map=excluded.map",
                (pid, session_id, content_hash, started_at, int(time.time()), json.dumps(metrics), blob),
            )
            self.version += 1
        return True

    def session_owner(self, session_id: str) -> int | None:
        with self.lock:
            row = self.db.execute(
                # rowid = first insert (an upsert keeps it); uploaded_at moves on every re-upload
                "SELECT participant_id FROM sessions WHERE session_id=? ORDER BY rowid LIMIT 1", (session_id,)
            ).fetchone()
        return row["participant_id"] if row else None

    def is_known_hash(self, pid: int, content_hash: str) -> bool:
        with self.lock:
            return self.db.execute(
                "SELECT 1 FROM sessions WHERE participant_id=? AND content_hash=?", (pid, content_hash)
            ).fetchone() is not None

    def session_rows(self, pid: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT participant_id, session_id, started_at, uploaded_at, metrics FROM sessions"
        with self.lock:
            rows = (self.db.execute(sql + " WHERE participant_id=?", (pid,)) if pid is not None else self.db.execute(sql)).fetchall()
        return [{**dict(r), "metrics": json.loads(r["metrics"])} for r in rows]

    def session_map(self, pid: int, session_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.db.execute(
                "SELECT map FROM sessions WHERE participant_id=? AND session_id=?", (pid, session_id)
            ).fetchone()
        return json.loads(gzip.decompress(row["map"])) if row else None

    # -- snapshots (participant totals over time, for "this hour" challenges) --
    def snapshot(self, pid: int, totals: dict[str, Any]) -> None:
        now = int(time.time())
        with self.lock:
            last = self.db.execute("SELECT MAX(ts) AS ts FROM snapshots WHERE participant_id=?", (pid,)).fetchone()["ts"]
            if last is not None and now - last < SNAPSHOT_MIN_GAP_S:
                self.db.execute("UPDATE snapshots SET metrics=? WHERE participant_id=? AND ts=?", (json.dumps(totals), pid, last))
                return
            self.db.execute("INSERT INTO snapshots (participant_id, ts, metrics) VALUES (?,?,?)", (pid, now, json.dumps(totals)))
            self.db.execute("DELETE FROM snapshots WHERE ts < ?", (now - SNAPSHOT_KEEP_S,))

    def baselines(self, since: int) -> dict[int, dict[str, Any]]:
        """Per participant: the last snapshot before `since`, else their first one after it."""
        with self.lock:
            rows = self.db.execute(
                "SELECT participant_id, ts, metrics FROM snapshots ORDER BY participant_id, ts"
            ).fetchall()
        out: dict[int, dict[str, Any]] = {}
        for r in rows:
            pid = r["participant_id"]
            if r["ts"] <= since or pid not in out:
                out[pid] = json.loads(r["metrics"])
        return out

    # -- sync heartbeats (what each participant's sync loop last reported) ---
    def set_sync_status(self, pid: int, payload: dict[str, Any]) -> None:
        with self.lock:
            self.db.execute(
                "INSERT INTO sync_status VALUES (?,?,?) ON CONFLICT (participant_id) DO UPDATE SET"
                " ts=excluded.ts, payload=excluded.payload",
                (pid, int(time.time()), json.dumps(payload)),
            )

    def sync_statuses(self) -> dict[int, dict[str, Any]]:
        with self.lock:
            rows = self.db.execute("SELECT participant_id, ts, payload FROM sync_status").fetchall()
        return {r["participant_id"]: {"ts": r["ts"], **json.loads(r["payload"])} for r in rows}

    # -- badges / meta / events --------------------------------------------
    def badge_tiers(self) -> dict[tuple[str, str], int]:
        with self.lock:
            return {(r["subject"], r["badge"]): r["tier"] for r in self.db.execute("SELECT * FROM badge_state")}

    def set_badge_tier(self, subject: str, badge: str, tier: int) -> None:
        with self.lock:
            self.db.execute(
                "INSERT INTO badge_state VALUES (?,?,?) ON CONFLICT (subject, badge) DO UPDATE SET tier=excluded.tier",
                (subject, badge, tier),
            )

    def meta_get(self, k: str, default: Any = None) -> Any:
        with self.lock:
            row = self.db.execute("SELECT value FROM meta WHERE key=?", (k,)).fetchone()
        return json.loads(row["value"]) if row else default

    def meta_set(self, k: str, value: Any) -> None:
        with self.lock:
            self.db.execute(
                "INSERT INTO meta VALUES (?,?) ON CONFLICT (key) DO UPDATE SET value=excluded.value", (k, json.dumps(value))
            )

    def add_event(self, type_: str, payload: dict[str, Any]) -> None:
        with self.lock:
            self.db.execute("INSERT INTO events (ts, type, payload) VALUES (?,?,?)", (int(time.time()), type_, json.dumps(payload)))
            self.db.execute("DELETE FROM events WHERE id <= (SELECT MAX(id) FROM events) - ?", (EVENTS_KEEP,))

    def events_since(self, since_id: int, limit: int = 50) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT id, ts, type, payload FROM events WHERE id > ? ORDER BY id DESC LIMIT ?", (since_id, limit)
            ).fetchall()
        return [{"id": r["id"], "ts": r["ts"], "type": r["type"], **json.loads(r["payload"])} for r in reversed(rows)]
