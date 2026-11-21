"""Offline tests: metrics, badges, storage, live events, join scripts and HTTP handling.

    python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import gzip
import json
import shlex
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import server_7400 as srv
from hub import badges as B
from hub import join_scripts
from hub import metrics as M
from hub.board import Board, Config
from hub.store import NameTaken, Store


def make_map(sid="s1", calls=10, errors=0, verify_after_errors=False, mcp=None, tokens=0, started="2026-12-05T20:00:00Z",
             role="root", edits=0):
    events = []
    t = 0
    for i in range(calls):
        t += 1000
        events.append({"kind": "exec", "tool": "Bash", "t": t, "err": i < errors})
    if verify_after_errors:
        events.append({"kind": "verify", "tool": "Bash", "t": t + 1000, "err": False})
    for i in range(edits):
        events.append({"kind": "edit", "tool": "Edit", "t": t + 2000 + i, "ins": 10, "del": 5})
    for server in mcp or []:
        events.append({"kind": "mcp", "tool": "x", "server": server, "t": t + 3000})
    if tokens:
        events.append({"kind": "llm", "in": tokens // 4, "cr": tokens // 2, "cw": tokens // 8, "out": tokens // 8, "t": 1})
    return {"schema": "agentplay-v1",
            "session": {"id": sid, "agentTool": "claude-code", "startedAt": started, "durationMs": t, "role": role,
                        "models": ["m1"]},
            "totals": {"maxContext": 1234}, "events": events,
            "files": [{"id": 1, "path": "C:\\Users\\someone\\secret-project\\src\\main.py"}],
            "repos": [{"name": "proj", "remote": "https://example.com/private/proj.git"}]}


class MetricsTests(unittest.TestCase):
    def test_extract_counts(self):
        m = M.extract(make_map(calls=12, errors=3, verify_after_errors=True, mcp=["github", "linear"], tokens=800, edits=2))
        self.assertEqual(m["calls"], 12 + 1 + 2 + 2)
        self.assertEqual(m["errors"], 3)
        self.assertEqual(m["comebacks"], 1)
        self.assertEqual(m["mcpServers"], ["github", "linear"])
        self.assertEqual(m["tokens"], 200 + 400 + 100 + 100)
        self.assertEqual(m["linesChanged"], 30)
        self.assertEqual(m["verifyPass"], 1)

    def test_night_calls_use_venue_offset(self):
        # 20:00Z = 01:30 IST, so every call is a night call at +330 and none at UTC.
        self.assertEqual(M.extract(make_map(calls=5), utc_offset_min=330)["nightCalls"], 5)
        self.assertEqual(M.extract(make_map(calls=5), utc_offset_min=0)["nightCalls"], 0)

    def test_merge_sums_and_unions(self):
        a, b = M.extract(make_map("a", calls=3, mcp=["github"])), M.extract(make_map("b", calls=4, mcp=["slack"]))
        m = M.merge([a, b])
        self.assertEqual(m["sessions"], 2)
        self.assertEqual(m["calls"], a["calls"] + b["calls"])
        self.assertEqual(m["mcpServers"], ["github", "slack"])

    def test_minimize_strips_paths_and_remotes(self):
        doc = M.minimize(make_map())
        self.assertEqual(doc["files"][0]["path"], "main.py")
        self.assertEqual(doc["repos"], [{"name": "proj"}])

    def test_invalid_map(self):
        with self.assertRaises(ValueError):
            M.extract({"session": {}})

    def test_hostile_numbers_are_clamped(self):
        doc = make_map()
        doc["totals"] = {"calls": "1e99", "tokens": -5, "costUsd": "nan"}
        m = M.extract(doc)
        self.assertEqual(m["tokens"], 0)
        self.assertEqual(m["costUsd"], 0.0)


class BadgeTests(unittest.TestCase):
    def test_tiers(self):
        m = M.merge([M.extract(make_map(calls=600))])
        self.assertEqual(B.BY_ID["tool_maestro"].tier(m), 2)

    def test_lower_is_better(self):
        m = M.merge([M.extract(make_map(calls=200, errors=3))])
        self.assertEqual(B.BY_ID["clean_run"].tier(m), 3)  # 1.5% error rate
        small = M.merge([M.extract(make_map(calls=50))])
        self.assertEqual(B.BY_ID["clean_run"].tier(small), 0)  # needs 100+ calls

    def test_crowns_pick_best_holder(self):
        hi = M.merge([M.extract(make_map(calls=700))])
        lo = M.merge([M.extract(make_map(calls=150))])
        crowns = B.crowns(B.PERSONAL, [("lo", lo, B.evaluate(B.PERSONAL, lo)), ("hi", hi, B.evaluate(B.PERSONAL, hi))])
        self.assertEqual(crowns["tool_maestro"], "hi")


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "hub.db")
        self.board = Board(self.store, Config())

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def upload(self, p, doc):
        raw = json.dumps(doc).encode()
        return self.board.ingest(p, raw, doc)

    def test_register_unique_names(self):
        self.store.register("Ada", "Team A")
        with self.assertRaises(NameTaken):
            self.store.register("  ada ", "Other")

    def test_upload_rank_and_events(self):
        a, _ = self.store.register("Ada", "Team A")
        b, _ = self.store.register("Bob", "Team A")
        self.upload(a, make_map("s1", calls=150))
        self.upload(b, make_map("s2", calls=40))
        data = self.board.payload()
        self.assertEqual([p["name"] for p in data["players"]], ["Ada", "Bob"])
        self.assertEqual(data["teams"][0]["metrics"]["calls"], 190)
        types = {e["type"] for e in self.store.events_since(0)}
        self.assertTrue({"badge", "crown", "milestone"} <= types or {"badge", "crown"} <= types)
        self.assertIn("tool_maestro", data["players"][0]["crowns"])

    def test_same_content_is_unchanged(self):
        a, _ = self.store.register("Ada", "T")
        self.upload(a, make_map("s1"))
        self.assertTrue(self.upload(a, make_map("s1"))["unchanged"])

    def test_session_counts_once_and_cannot_be_overwritten(self):
        a, _ = self.store.register("Ada", "T")
        m, _ = self.store.register("Mallory", "X")
        self.upload(a, make_map("shared", calls=50))
        self.assertIn("skipped", self.upload(m, make_map("shared", calls=0)))
        self.assertEqual(len(self.board.session_timeline("Ada", "shared")["steps"]), 50)
        self.assertIsNone(self.board.session_timeline("Mallory", "shared"))
        self.assertEqual(self.board.payload()["teams"][0]["metrics"]["calls"], 50)
        # The owner keeps syncing growth of its session after anyone else's attempt.
        self.assertEqual(self.upload(a, make_map("shared", calls=60))["calls"], 60)
        self.assertIn("skipped", self.upload(m, make_map("shared", calls=70)))

    def test_subagent_and_pre_event_sessions_skipped(self):
        board = Board(self.store, Config(event_start=M.parse_ts("2026-12-06T00:00:00Z")))
        a, _ = self.store.register("Ada", "T")
        self.assertIn("skipped", board.ingest(a, b"x", make_map(role="subagent")))
        self.assertIn("skipped", board.ingest(a, b"y", make_map(started="2026-12-05T00:00:00Z")))

    def test_heartbeat_makes_builder_live_and_is_sanitised(self):
        a, _ = self.store.register("Ada", "T")
        self.assertFalse(self.board.payload()["players"][0]["live"])
        self.board.heartbeat(a, {"found": 3, "eligible": "x", "skipped": {"no activity in the last 12 hours": 3},
                                 "agents": ["claude-code"], "error": "boom\x00" + "e" * 500, "extra": "ignored"})
        self.board._cache = None  # heartbeats don't invalidate the cache on purpose; force a rebuild here
        detail = self.board.player("Ada")
        self.assertTrue(detail["live"] and detail["connected"])
        self.assertEqual(detail["sync"]["found"], 3)
        self.assertEqual(detail["sync"]["eligible"], 0)
        self.assertEqual(len(detail["sync"]["error"]), 300)
        self.assertNotIn("extra", detail["sync"])

    def test_power_hour_ignores_first_dump(self):
        a, _ = self.store.register("Ada", "T")
        self.upload(a, make_map("s1", calls=100))
        self.assertEqual(self.board.payload()["powerHour"]["top"], [])

    def test_team_progress_and_player_detail(self):
        a, _ = self.store.register("Ada", "T")
        self.upload(a, make_map("s1", calls=120))
        self.assertEqual(self.board.player("ada")["name"], "Ada")
        self.assertEqual(self.board.team("t")["members"][0]["name"], "Ada")
        self.assertIsNone(self.board.player("nobody"))


class JoinScriptTests(unittest.TestCase):
    PAYLOADS = ["$(echo PWNED)", "x'; echo PWNED; '", "`echo PWNED`", 'a"b\\c', "x’; Write-Host PWNED; ‘"]

    def test_sh_quote_round_trips(self):
        for p in self.PAYLOADS:
            self.assertEqual(shlex.split(join_scripts.sh_quote(p)), [p])

    def test_ps_quote_doubles_every_quote(self):
        for p in self.PAYLOADS:
            q = join_scripts.ps_quote(p)
            inner = q[1:-1]
            for ch in "'\u2018\u2019\u201a\u201b":
                self.assertNotIn(ch, inner.replace(ch * 2, ""), p)  # every quote inside is escaped by doubling


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        store = Store(Path(cls.tmp.name) / "hub.db")
        srv.Handler.store = store
        srv.Handler.board = Board(store, Config())
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        srv.Handler.store.db.close()
        cls.tmp.cleanup()

    def req(self, path, body=None, headers=None, method=None):
        r = urllib.request.Request(self.base + path, data=body, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def register(self, name, team="T"):
        status, _, body = self.req("/api/register", json.dumps({"name": name, "team": team}).encode(),
                                   {"Content-Type": "application/json"})
        self.assertEqual(status, 200, body)
        return json.loads(body)["token"]

    def test_pages_have_csp(self):
        status, headers, _ = self.req("/")
        self.assertEqual(status, 200)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])

    def test_head_has_headers_without_body(self):
        status, headers, body = self.req("/healthz", method="HEAD")
        self.assertEqual((status, body), (200, b""))
        self.assertEqual(headers["Content-Length"], "3")

    def test_static_traversal_blocked(self):
        for p in ("/static/../server_7400.py", "/static/..%2fserver_7400.py", "/static/nope.js"):
            self.assertEqual(self.req(p)[0], 404, p)

    def test_upload_requires_token(self):
        doc = gzip.compress(json.dumps(make_map()).encode())
        self.assertEqual(self.req("/api/upload", doc)[0], 401)
        self.assertEqual(self.req("/api/upload", doc, {"X-Upload-Token": "bogus"})[0], 401)

    def test_upload_and_leaderboard(self):
        token = self.register("Http Ada", "Web")
        status, _, body = self.req("/api/upload", gzip.compress(json.dumps(make_map("h1", calls=33)).encode()),
                                   {"X-Upload-Token": token})
        self.assertEqual(status, 200, body)
        lb = json.loads(self.req("/api/leaderboard")[2])
        self.assertNotIn("_players", lb)
        self.assertIn("Http Ada", [p["name"] for p in lb["players"]])

    def test_heartbeat_requires_token(self):
        body = json.dumps({"found": 1}).encode()
        self.assertEqual(self.req("/api/heartbeat", body, {"X-Upload-Token": "bogus"})[0], 401)
        token = self.register("Beat")
        self.assertEqual(self.req("/api/heartbeat", body, {"X-Upload-Token": token})[0], 200)

    def test_gzip_bomb_rejected(self):
        token = self.register("Bomber")
        bomb = gzip.compress(b" " * (srv.MAX_MAP_BYTES + 10))
        status, _, body = self.req("/api/upload", bomb, {"X-Upload-Token": token})
        self.assertEqual(status, 400)
        self.assertIn(b"60 MB", body)

    def test_join_script_needs_known_token_and_valid_host(self):
        self.assertEqual(self.req("/join.sh?token=nope")[0], 404)
        token = self.register("Script $(whoami)")
        status, _, body = self.req("/join.sh?token=" + token)
        self.assertEqual(status, 200)
        self.assertIn(b"NAME='Script $(whoami)'", body)
        self.assertEqual(self.req("/join.sh?token=" + token, headers={"Host": 'x"; evil'})[0], 400)

    def test_register_validation(self):
        status, _, _ = self.req("/api/register", json.dumps({"name": "\n\t", "team": "T"}).encode())
        self.assertEqual(status, 400)
        self.register("Dup")
        status, _, _ = self.req("/api/register", json.dumps({"name": "DUP", "team": "T"}).encode())
        self.assertEqual(status, 409)

    def test_admin_disabled_without_token(self):
        status, _, _ = self.req("/api/admin/remove", json.dumps({"name": "Dup"}).encode(), {"X-Admin-Token": ""})
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
