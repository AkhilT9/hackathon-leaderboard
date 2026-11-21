"""Hackathon Control: live leaderboard for AI coding-agent activity.

Pages:  /  /team?name=  /player?name=  /awards  /stage  /join
API:    GET  /api/leaderboard | /api/player?name= | /api/team?name= | /api/session?participant=&id=
        GET  /api/events?since= | /api/badges | /healthz
        POST /api/register {name, team, code?} -> upload token (shown once)
        POST /api/upload   (X-Upload-Token header) raw/gzip agentplay map, or {"mapBase64": ...}
        POST /api/admin/reissue | /api/admin/remove {name}  (X-Admin-Token header)
Sync:   GET  /join.ps1?token=  /join.sh?token=

Configuration (environment):
  HUB_DATA_DIR            where hub.db lives (default ./data)
  HUB_PUBLIC_URL          public https URL baked into the sync scripts (set this on any deployment)
  HUB_EVENT_NAME          shown on every page
  HUB_EVENT_START/END     ISO times; sessions started before START are ignored, END drives the countdown
  HUB_UTC_OFFSET_MINUTES  venue time zone for night-owl and power-hour clocks (default 330 = IST)
  HUB_REGISTRATION_CODE   if set, /api/register requires it
  HUB_ADMIN_TOKEN         enables the admin endpoints
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hmac
import io
import json
import mimetypes
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from hub import badges as B
from hub import join_scripts
from hub.board import Board, Config, Rejected
from hub.metrics import parse_ts
from hub.store import NameTaken, Store

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_MAP_BYTES = 60 * 1024 * 1024  # decompressed cap (gzip bombs)
MAX_JSON_BODY = 4096
MAX_LABEL_LEN = 40

PAGES = {"/": "index.html", "/team": "team.html", "/player": "player.html", "/awards": "awards.html",
         "/stage": "stage.html", "/join": "join.html"}
STATIC_FILES = {f"/static/{p.name}": p for p in STATIC_DIR.glob("*") if p.is_file()} if STATIC_DIR.is_dir() else {}

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

_HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}(:[0-9]{1,5})?$")
_PUBLIC_URL_RE = re.compile(r"^https?://[A-Za-z0-9.-]{1,253}(:[0-9]{1,5})?$")


def clean_label(value: Any) -> str:
    text = "".join(ch for ch in str(value or "") if ch.isprintable())
    return " ".join(text.split())[:MAX_LABEL_LEN]


def resolve_hub_url(host_hdr: str) -> str | None:
    public = os.environ.get("HUB_PUBLIC_URL", "").strip().rstrip("/")
    if public:
        return public if _PUBLIC_URL_RE.match(public) else None
    if not _HOST_RE.match(host_hdr):
        return None
    local = host_hdr.split(":")[0] in ("127.0.0.1", "localhost") or re.match(r"^\d+\.\d+\.\d+\.\d+(:\d+)?$", host_hdr)
    return f"{'http' if local else 'https'}://{host_hdr}"


def decode_map(raw: bytes) -> tuple[bytes, Any]:
    """Return (decompressed JSON bytes, parsed doc). Accepts raw JSON, gzip, or {"mapBase64"/"map": ...}."""
    def gunzip(data: bytes) -> bytes:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
            out = gz.read(MAX_MAP_BYTES + 1)
        if len(out) > MAX_MAP_BYTES:
            raise ValueError("Session map is larger than 60 MB once decompressed.")
        return out

    if raw[:2] == b"\x1f\x8b":
        raw = gunzip(raw)
    doc = json.loads(raw.decode("utf-8"))
    if isinstance(doc, dict) and ("mapBase64" in doc or "map" in doc):
        if doc.get("mapBase64"):
            inner = base64.b64decode(doc["mapBase64"], validate=True)
            raw = gunzip(inner) if inner[:2] == b"\x1f\x8b" else inner
            doc = json.loads(raw.decode("utf-8"))
        else:
            doc = doc["map"]
            raw = json.dumps(doc, sort_keys=True).encode("utf-8")
    return raw, doc


def _public(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in payload.items() if not k.startswith("_")}


class Handler(BaseHTTPRequestHandler):
    server_version = "HackathonControl/2"
    timeout = 30  # a client that stalls mid-body can't hold a thread forever
    board: Board
    store: Store

    # -- responses ----------------------------------------------------------
    def _send(self, status: int, body: bytes, content_type: str, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if content_type.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self) -> None:  # noqa: N802  (uptime checks; same headers as GET, no body)
        self.do_GET()

    def _json(self, status: int, payload: Any) -> None:
        self._send(status, json.dumps(payload, separators=(",", ":")).encode("utf-8"), "application/json; charset=utf-8")

    def _text(self, status: int, text: str) -> None:
        self._send(status, text.encode("utf-8"), "text/plain; charset=utf-8")

    def _file(self, path: Path, cache: str) -> None:
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        self._send(HTTPStatus.OK, path.read_bytes(), ctype, cache)

    def _read_body(self, limit: int) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length <= 0 or length > limit:
            self._json(HTTPStatus.BAD_REQUEST, {"error": f"Body must be 1 byte to {limit // 1024} KB."})
            return None
        return self.rfile.read(length)

    # -- GET ----------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        url = urlsplit(self.path)
        qs = parse_qs(url.query)
        arg = lambda k: (qs.get(k) or [""])[0].strip()  # noqa: E731
        path = url.path.rstrip("/") or "/"

        if path in PAGES:
            return self._file(STATIC_DIR / PAGES[path], "no-cache")
        if path in STATIC_FILES:
            return self._file(STATIC_FILES[path], "public, max-age=300")
        if path == "/healthz":
            return self._text(HTTPStatus.OK, "ok\n")
        if path == "/api/leaderboard":
            return self._json(HTTPStatus.OK, _public(self.board.payload()))
        if path == "/api/config":
            return self._json(HTTPStatus.OK, self.board.event_info())
        if path == "/api/badges":
            return self._json(HTTPStatus.OK, {"personal": [b.public() for b in B.PERSONAL],
                                              "team": [b.public() for b in B.TEAM], "tiers": list(B.TIER_NAMES)})
        if path == "/api/events":
            try:
                since = int(arg("since") or 0)
            except ValueError:
                since = 0
            return self._json(HTTPStatus.OK, {"events": self.store.events_since(since)})
        if path == "/api/player":
            data = self.board.player(arg("name"))
            return self._json(HTTPStatus.OK, data) if data else self._json(HTTPStatus.NOT_FOUND, {"error": "No such participant"})
        if path == "/api/team":
            data = self.board.team(arg("name"))
            return self._json(HTTPStatus.OK, data) if data else self._json(HTTPStatus.NOT_FOUND, {"error": "No such team"})
        if path == "/api/session":
            data = self.board.session_timeline(arg("participant"), arg("id"))
            return self._json(HTTPStatus.OK, data) if data else self._json(HTTPStatus.NOT_FOUND, {"error": "No such session"})
        if path == "/api/me":
            p = self.store.by_token(self.headers.get("X-Upload-Token", ""))
            return self._json(HTTPStatus.OK, p) if p else self._json(HTTPStatus.UNAUTHORIZED, {"error": "Unknown token"})
        if path in ("/join.ps1", "/join.sh"):
            return self._join_script(path, arg("token"))
        self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def _join_script(self, path: str, token: str) -> None:
        participant = self.store.by_token(token)
        if not participant:
            return self._text(HTTPStatus.NOT_FOUND, "Unknown token. Register at /join first.\n")
        hub = resolve_hub_url(self.headers.get("Host") or "")
        if hub is None:
            return self._text(HTTPStatus.BAD_REQUEST, "Invalid Host header or HUB_PUBLIC_URL.\n")
        gen = join_scripts.ps1 if path == "/join.ps1" else join_scripts.sh
        since = self.board.event_info()["start"] or ""
        self._text(HTTPStatus.OK, gen(hub, token, participant["name"], participant["team"], since))

    # -- POST ---------------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/api/upload":
            return self._upload()
        if path == "/api/register":
            return self._register()
        if path == "/api/heartbeat":
            return self._heartbeat()
        if path in ("/api/admin/reissue", "/api/admin/remove"):
            return self._admin(path)
        self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def _json_body(self) -> dict[str, Any] | None:
        raw = self._read_body(MAX_JSON_BODY)
        if raw is None:
            return None
        try:
            body = json.loads(raw.decode("utf-8"))
        except ValueError:
            body = None
        if not isinstance(body, dict):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "Body must be a JSON object."})
            return None
        return body

    def _register(self) -> None:
        body = self._json_body()
        if body is None:
            return
        code = os.environ.get("HUB_REGISTRATION_CODE", "")
        if code and not hmac.compare_digest(str(body.get("code") or "").encode(), code.encode()):
            return self._json(HTTPStatus.FORBIDDEN, {"error": "Wrong event code."})
        name, team = clean_label(body.get("name")), clean_label(body.get("team"))
        if not name or not team:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": f"Name and team are required (max {MAX_LABEL_LEN} characters)."})
        try:
            participant, token = self.store.register(name, team)
        except NameTaken:
            return self._json(HTTPStatus.CONFLICT, {"error": f"'{name}' is already registered. Ask an organiser to reissue your token."})
        self.store.add_event("joined", {"name": name, "team": team})
        self._json(HTTPStatus.OK, {"name": participant["name"], "team": participant["team"], "token": token,
                                   "hub": resolve_hub_url(self.headers.get("Host") or "")})

    def _heartbeat(self) -> None:
        body = self._json_body()
        if body is None:
            return
        participant = self.store.by_token(self.headers.get("X-Upload-Token", ""))
        if not participant:
            return self._json(HTTPStatus.UNAUTHORIZED, {"error": "Missing or unknown X-Upload-Token. Register at /join."})
        self._json(HTTPStatus.OK, self.board.heartbeat(participant, body))

    def _upload(self) -> None:
        # Read the (size-capped) body before answering: replying first makes clients see a
        # connection reset instead of the 401 that tells them their token is wrong.
        raw = self._read_body(MAX_UPLOAD_BYTES)
        if raw is None:
            return
        participant = self.store.by_token(self.headers.get("X-Upload-Token", ""))
        if not participant:
            return self._json(HTTPStatus.UNAUTHORIZED, {"error": "Missing or unknown X-Upload-Token. Register at /join."})
        try:
            data, doc = decode_map(raw)
            result = self.board.ingest(participant, data, doc)
        except (ValueError, KeyError, TypeError, OSError, EOFError) as exc:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)[:300]})
        self._json(HTTPStatus.OK, result)

    def _admin(self, path: str) -> None:
        admin = os.environ.get("HUB_ADMIN_TOKEN", "")
        given = self.headers.get("X-Admin-Token", "")
        if not admin or not hmac.compare_digest(given.encode(), admin.encode()):
            return self._json(HTTPStatus.FORBIDDEN, {"error": "Admin token required."})
        body = self._json_body()
        if body is None:
            return
        name = clean_label(body.get("name"))
        if path.endswith("reissue"):
            token = self.store.reissue(name)
            return self._json(HTTPStatus.OK, {"name": name, "token": token}) if token else self._json(HTTPStatus.NOT_FOUND, {"error": "No such participant"})
        ok = self.store.remove(name)
        self._json(HTTPStatus.OK if ok else HTTPStatus.NOT_FOUND, {"removed": ok})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass  # access logs would carry upload tokens in /join.* query strings


def load_config() -> Config:
    def ts(name: str):
        value = os.environ.get(name, "").strip()
        parsed = parse_ts(value) if value else None
        if value and parsed is None:
            raise SystemExit(f"{name} must be an ISO time such as 2026-12-05T09:00:00+05:30")
        return parsed

    return Config(
        event_name=os.environ.get("HUB_EVENT_NAME", "Hackathon Control").strip()[:80] or "Hackathon Control",
        event_start=ts("HUB_EVENT_START"),
        event_end=ts("HUB_EVENT_END"),
        utc_offset_min=int(os.environ.get("HUB_UTC_OFFSET_MINUTES", "330")),
        registration_code=os.environ.get("HUB_REGISTRATION_CODE", ""),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Hackathon Control leaderboard server")
    ap.add_argument("--host", default=os.environ.get("HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT") or 7400))
    ap.add_argument("--data-dir", default=os.environ.get("HUB_DATA_DIR") or str(BASE_DIR / "data"))
    args = ap.parse_args()

    store = Store(Path(args.data_dir) / "hub.db")
    Handler.store = store
    Handler.board = Board(store, load_config())
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    print(f"Hackathon Control on http://{args.host}:{args.port}  (data: {args.data_dir})")
    server.serve_forever()


if __name__ == "__main__":
    main()
