"""Sessions: one hackathon event (or round) each, with its own SQLite file and board.

registry.json in the data dir lists them and names the active one, which `/`, `/join` and
`/stage` show when no `?s=` is given. The first start adopts an existing `hub.db` as the
session "main" in place, so upgrading moves no files. Upload tokens are random, so a token
is routed to its session by looking it up in each one (a handful of indexed queries).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from .board import Board, Config
from .store import Store

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")
MAX_SESSIONS = 50


class Registry:
    def __init__(self, data_dir: Path, defaults: Config) -> None:
        self.dir = data_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.file = data_dir / "registry.json"
        self.defaults = defaults
        self.lock = threading.RLock()
        self.boards: dict[str, Board] = {}
        if self.file.is_file():
            self.data = json.loads(self.file.read_text(encoding="utf-8"))
        else:
            self.data = {"active": "main", "sessions": [{"slug": "main", "path": "hub.db", "created": int(time.time())}]}
            self._save()
        for entry in self.data["sessions"]:
            self._open(entry)

    def _open(self, entry: dict[str, Any]) -> Board:
        board = Board(Store(self.dir / entry["path"]), self.defaults, slug=entry["slug"])
        self.boards[entry["slug"]] = board
        return board

    def _save(self) -> None:
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        os.replace(tmp, self.file)

    # -- lookups --------------------------------------------------------------
    @property
    def active_slug(self) -> str:
        return self.data["active"]

    def get(self, slug: str | None = None) -> Board | None:
        with self.lock:
            return self.boards.get(slug or self.data["active"])

    def find_token(self, token: str) -> tuple[Board, dict[str, Any]] | None:
        with self.lock:
            boards = list(self.boards.values())
        for board in boards:
            p = board.store.by_token(token)
            if p:
                return board, p
        return None

    def list(self) -> list[dict[str, Any]]:
        with self.lock:
            entries = list(self.data["sessions"])
        out = []
        for e in entries:
            b = self.boards[e["slug"]]
            s = b.payload()["summary"]
            out.append({"slug": e["slug"], "active": e["slug"] == self.active_slug, "created": e.get("created"),
                        "status": b.status(), "settings": b.cfg.to_json(),
                        "participants": len(b.store.participants()), "teams": s["teams"], "calls": s["calls"],
                        "tokens": s["tokens"], "live": s["live"]})
        return out

    # -- changes --------------------------------------------------------------
    def create(self, slug: str, settings: dict[str, Any], copy_from: str | None = None) -> Board:
        slug = str(slug or "").strip().lower()
        if not SLUG_RE.match(slug):
            raise ValueError("Slug: 1-40 lowercase letters, digits and dashes (e.g. batch-2).")
        with self.lock:
            if slug in self.boards:
                raise ValueError(f"A session called '{slug}' already exists.")
            if len(self.boards) >= MAX_SESSIONS:
                raise ValueError(f"At most {MAX_SESSIONS} sessions; delete an old one first.")
            base = self.boards[copy_from].cfg if copy_from in self.boards else self.defaults
            # copying keeps the rules, never the open/closed state or the announcement
            base = replace(base, registration_open=True, uploads_open=True, archived=False, announcement="")
            cfg = Config.from_json(settings, base)
            entry = {"slug": slug, "path": f"sessions/{slug}/hub.db", "created": int(time.time())}
            board = Board(Store(self.dir / entry["path"]), cfg, slug=slug)
            self.boards[slug] = board
            self.data["sessions"].append(entry)
            self._save()
            return board

    def set_active(self, slug: str) -> None:
        with self.lock:
            if slug not in self.boards:
                raise KeyError(slug)
            self.data["active"] = slug
            self._save()

    def delete(self, slug: str) -> None:
        with self.lock:
            if slug not in self.boards:
                raise KeyError(slug)
            if slug == self.active_slug:
                raise ValueError("Make another session active before deleting this one.")
            entry = next(e for e in self.data["sessions"] if e["slug"] == slug)
            self.data["sessions"].remove(entry)
            self._save()
            self.boards.pop(slug).store.close()
        path = self.dir / entry["path"]
        if path.parent != self.dir and path.parent.parent.name == "sessions":
            shutil.rmtree(path.parent, ignore_errors=True)
        else:  # the adopted legacy hub.db sits in the data dir itself
            for suffix in ("", "-wal", "-shm"):
                Path(str(path) + suffix).unlink(missing_ok=True)
