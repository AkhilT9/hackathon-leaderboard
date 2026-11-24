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

from hub.badges import TEAM as TEAM_BADGES

_TEAM_BADGE_IDS = {b.id for b in TEAM_BADGES}

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


def _is_team_event(e: dict[str, Any]) -> bool:
    # badge events say subjectType; crown events only name the badge, and team badges are their own set
    return e.get("subjectType") == "team" or (e.get("type") == "crown" and e.get("badge") in _TEAM_BADGE_IDS)


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
        """Delete a participant with their sessions, badges and live-feed lines."""
        with self.lock:
            row = self.db.execute("SELECT name, team_key FROM participants WHERE name_key=?", (key(name),)).fetchone()
            if not row:
                return False
            self._purge([key(name)])
            self._drop_empty_team(row["team_key"])
            self.version += 1
        return True

    def remove_team(self, team: str) -> list[str]:
        """Delete a team and every member; returns the names removed."""
        with self.lock:
            names = [r["name"] for r in self.db.execute("SELECT name FROM participants WHERE team_key=?", (key(team),))]
            if not names:
                return []
            self._purge([key(n) for n in names])
            self._drop_empty_team(key(team))
            self.version += 1
        return names

    def _purge(self, name_keys: list[str]) -> None:
        # sessions, snapshots and sync_status go with the participant (ON DELETE CASCADE)
        for nk in name_keys:
            self.db.execute("DELETE FROM participants WHERE name_key=?", (nk,))
            self.db.execute("DELETE FROM badge_state WHERE subject=?", (f"player:{nk}",))
        if set(self.hidden()) & set(name_keys):
            self.meta_set("hidden", sorted(set(self.hidden()) - set(name_keys)))
        self._drop_events(lambda e: not _is_team_event(e) and key(str(e.get("name") or "")) in name_keys)

    def _drop_empty_team(self, team_key: str) -> None:
        if self.db.execute("SELECT 1 FROM participants WHERE team_key=?", (team_key,)).fetchone():
            return
        self.db.execute("DELETE FROM badge_state WHERE subject=?", (f"team:{team_key}",))
        self._drop_events(lambda e: _is_team_event(e) and key(str(e.get("name") or "")) == team_key)

    def _drop_events(self, match) -> None:
        rows = self.db.execute("SELECT id, type, payload FROM events").fetchall()
        ids = [(r["id"],) for r in rows if match({"type": r["type"], **json.loads(r["payload"])})]
        self.db.executemany("DELETE FROM events WHERE id=?", ids)

    def rename(self, name: str, new_name: str, new_team: str) -> dict[str, Any] | None:
        """Rename a participant and/or move them to another team. Raises NameTaken."""
        old = key(name)
        with self.lock:
            row = self.db.execute("SELECT team_key FROM participants WHERE name_key=?", (old,)).fetchone()
            if not row:
                return None
            try:
                self.db.execute("UPDATE participants SET name=?, name_key=?, team=?, team_key=? WHERE name_key=?",
                                (new_name, key(new_name), new_team, key(new_team), old))
            except sqlite3.IntegrityError as exc:
                raise NameTaken(new_name) from exc
            if key(new_name) != old:
                self.db.execute("UPDATE badge_state SET subject=? WHERE subject=?", (f"player:{key(new_name)}", f"player:{old}"))
                hidden = self.hidden()
                if old in hidden:
                    self.meta_set("hidden", sorted((set(hidden) - {old}) | {key(new_name)}))
            if key(new_team) != row["team_key"]:
                self._drop_empty_team(row["team_key"])
            self.version += 1
        return {"name": new_name, "team": new_team}

    def hidden(self) -> list[str]:
        return list(self.meta_get("hidden", []))

    def set_hidden(self, name: str, hide: bool) -> bool:
        with self.lock:
            if not self.by_name(name):
                return False
            cur = set(self.hidden())
            cur = cur | {key(name)} if hide else cur - {key(name)}
            self.meta_set("hidden", sorted(cur))
            self.version += 1
        return True

    def remove_session(self, pid: int, session_id: str) -> bool:
        with self.lock:
            cur = self.db.execute("DELETE FROM sessions WHERE participant_id=? AND session_id=?", (pid, session_id))
            if cur.rowcount:
                self.version += 1
        return bool(cur.rowcount)

    def clear_events(self) -> None:
        with self.lock:
            self.db.execute("DELETE FROM events")

    def export_bytes(self, tmp_dir: Path) -> bytes:
        """A consistent copy of the whole database (SQLite online backup)."""
        tmp = tmp_dir / f".export-{secrets.token_hex(6)}.db"
        try:
            dst = sqlite3.connect(str(tmp))
            with self.lock:
                self.db.backup(dst)
            dst.close()
            return tmp.read_bytes()
        finally:
            tmp.unlink(missing_ok=True)

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def admin_rows(self) -> list[dict[str, Any]]:
        """Every participant with upload totals and their sync loop's last report, for /admin."""
        with self.lock:
            rows = self.db.execute(
                "SELECT p.id, p.name, p.team, p.created_at, COUNT(s.session_id) AS sessions, MAX(s.uploaded_at) AS last_upload,"
                " y.ts AS sync_ts, y.payload AS sync FROM participants p"
                " LEFT JOIN sessions s ON s.participant_id = p.id LEFT JOIN sync_status y ON y.participant_id = p.id"
                " GROUP BY p.id ORDER BY p.team_key, p.name_key"
            ).fetchall()
        hidden = set(self.hidden())
        return [{**{k: r[k] for k in ("name", "team", "created_at", "sessions", "last_upload", "sync_ts")},
                 "hidden": key(r["name"]) in hidden,
                 "sync": json.loads(r["sync"]) if r["sync"] else None} for r in rows]

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
