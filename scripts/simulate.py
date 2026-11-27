"""Simulate hackathon participants against a running hub (dry runs and load tests).

Registers N synthetic builders across T teams, then every round each builder's sessions
grow and are re-uploaded, the way the 20-second sync scripts behave. Maps are synthetic;
no real session data is used.

    python scripts/simulate.py --hub http://127.0.0.1:7400 --people 100 --teams 20 --rounds 30 --interval 20
    python scripts/simulate.py --people 24 --teams 6 --rounds 3 --interval 0     # quick seed for a demo
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import gzip
import json
import random
import statistics
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

FIRST = ["Aarav", "Diya", "Kabir", "Meera", "Rohan", "Ananya", "Ishaan", "Sara", "Vihaan", "Tara", "Arjun", "Nisha",
         "Dev", "Kiara", "Reyansh", "Zoya", "Aditya", "Riya", "Krish", "Myra", "Leo", "Ava", "Noah", "Mia", "Omar", "Lena"]
LAST = ["Rao", "Shah", "Iyer", "Nair", "Gupta", "Menon", "Das", "Reddy", "Kapoor", "Joshi", "Bose", "Pillai", "Khan", "Sen"]
TEAMS = ["Null Pointers", "Merge Conflict", "Byte Me", "Lambda Llamas", "Stack Smashers", "Kernel Panic", "Git Gud",
         "Segfault Society", "Async Avengers", "Cache Me", "Prompt Injectors", "Token Ring", "Off By One", "Hot Reload",
         "Race Condition", "Dark Mode", "Big O", "Ctrl Alt Elite", "Docker Dragons", "Rubber Ducks"]
AGENTS = [("claude-code", "claude-opus-5-5"), ("cursor", "gpt-5.5"), ("codex", "gpt-5.5-codex"),
          ("copilot-vscode", "claude-sonnet-5-5"), ("antigravity-cli", "gemini-3-pro"), ("gemini-cli", "gemini-3-flash")]
TOOLS = [("read", "Read"), ("edit", "Edit"), ("exec", "Bash"), ("search", "Grep"), ("verify", "Bash"),
         ("web", "WebSearch"), ("mcp", "mcp__github__create_issue"), ("tool", "Task"), ("commit", "Bash")]
WEIGHTS = [30, 22, 14, 10, 7, 4, 3, 2, 1]
MCP_SERVERS = ["github", "linear", "figma", "postgres", "slack", "sentry", "notion"]


class Builder:
    def __init__(self, i: int, teams: list[str], rng: random.Random) -> None:
        self.rng = rng
        self.name = f"{rng.choice(FIRST)} {rng.choice(LAST)} {i:03d}"
        self.team = teams[i % len(teams)]
        self.pace = rng.uniform(0.3, 2.2)          # how busy this builder is
        self.sloppiness = rng.uniform(0.01, 0.18)  # error rate
        self.agent, self.model = rng.choice(AGENTS)
        self.token: str | None = None
        self.sessions: list[dict] = []
        self.start = datetime.now(UTC) - timedelta(minutes=rng.randint(5, 90))

    def grow(self) -> list[dict]:
        rng = self.rng
        if not self.sessions or rng.random() < 0.08:
            sid = f"sim:{self.agent}:{rng.getrandbits(64):016x}"
            started = self.start + timedelta(minutes=rng.randint(0, 30))
            self.sessions.append({"id": sid, "started": started, "events": [], "t": 0})
        sess = self.sessions[-1]
        for _ in range(int(rng.randint(5, 25) * self.pace)):
            sess["t"] += rng.randint(2_000, 40_000)
            kind, tool = rng.choices(TOOLS, WEIGHTS)[0]
            ev = {"kind": kind, "tool": tool, "t": sess["t"], "dur": rng.randint(50, 9_000),
                  "err": kind not in ("commit",) and rng.random() < self.sloppiness}
            if kind == "edit":
                ev.update(ins=rng.randint(1, 80), **{"del": rng.randint(0, 40)})
            if kind == "mcp":
                ev["server"] = rng.choice(MCP_SERVERS[: 1 + int(self.pace * 3)])
            if kind == "commit":
                ev["vcs"] = {"action": "commit"}
            sess["events"].append(ev)
            if rng.random() < 0.5:
                sess["events"].append({"kind": "llm", "t": sess["t"], "model": self.model,
                                       "in": rng.randint(5, 900), "cr": rng.randint(5_000, 120_000),
                                       "cw": rng.randint(0, 8_000), "out": rng.randint(100, 3_000)})
        return [self.map_for(s) for s in self.sessions[-2:]]

    def map_for(self, s: dict) -> dict:
        ev = s["events"]
        tools = [e for e in ev if e["kind"] != "llm"]
        llm = [e for e in ev if e["kind"] == "llm"]
        tokens = sum(e["in"] + e["cr"] + e["cw"] + e["out"] for e in llm)
        return {
            "schema": "agentplay-v1",
            "session": {"id": s["id"], "agentTool": self.agent, "models": [self.model], "role": "root",
                        "startedAt": s["started"].strftime("%Y-%m-%dT%H:%M:%SZ"), "durationMs": s["t"]},
            "totals": {"calls": len(tools), "errors": sum(e["err"] for e in tools), "tokens": tokens,
                       "outputTokens": sum(e["out"] for e in llm), "requests": len(llm),
                       "costUsd": round(tokens * 1.1e-6, 4), "commits": sum(e["kind"] == "commit" for e in tools),
                       "maxContext": max([e["cr"] + e["cw"] for e in llm] or [0]),
                       "subagents": sum(e["tool"] == "Task" for e in tools), "delayMs": s["t"] // 5},
            "events": ev, "files": [], "repos": [], "prs": [], "tasks": [], "agents": [],
        }


def post(url: str, body: bytes, headers: dict[str, str]) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hub", default="http://127.0.0.1:7400")
    ap.add_argument("--people", type=int, default=100)
    ap.add_argument("--teams", type=int, default=20)
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--interval", type=float, default=20.0, help="seconds between rounds (sync scripts use 20)")
    ap.add_argument("--code", default="", help="event registration code, if the hub requires one")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    teams = TEAMS[: max(1, min(args.teams, len(TEAMS)))]
    builders = [Builder(i, teams, random.Random(rng.random())) for i in range(args.people)]
    hub = args.hub.rstrip("/")

    for b in builders:
        status, r = post(f"{hub}/api/register", json.dumps({"name": b.name, "team": b.team, "code": args.code}).encode(),
                         {"Content-Type": "application/json"})
        if status != 200:
            raise SystemExit(f"register {b.name}: {status} {r}")
        b.token = r["token"]
    print(f"registered {len(builders)} builders in {len(teams)} teams")

    latencies: list[float] = []
    failures = 0

    def sync(b: Builder) -> list[float]:
        nonlocal failures
        out = []
        for doc in b.grow():
            t0 = time.perf_counter()
            status, _ = post(f"{hub}/api/upload", gzip.compress(json.dumps(doc).encode()),
                             {"X-Upload-Token": b.token, "Content-Type": "application/gzip"})
            out.append(time.perf_counter() - t0)
            if status != 200:
                failures += 1
        return out

    with cf.ThreadPoolExecutor(max_workers=min(64, args.people)) as pool:
        for rnd in range(1, args.rounds + 1):
            t0 = time.perf_counter()
            # Spread uploads across the interval like real, unsynchronised laptops.
            def staggered(b: Builder) -> list[float]:
                if args.interval:
                    time.sleep(rng.uniform(0, args.interval * 0.9))
                return sync(b)
            for lat in pool.map(staggered, builders):
                latencies.extend(lat)
            t_lb = time.perf_counter()
            with urllib.request.urlopen(f"{hub}/api/leaderboard", timeout=30) as r:
                lb = json.loads(r.read())
            lb_ms = (time.perf_counter() - t_lb) * 1000
            print(f"round {rnd}: {time.perf_counter() - t0:5.1f}s  calls={lb['summary']['calls']:,}  "
                  f"badges={lb['summary']['badgesEarned']}  leaderboard={lb_ms:.0f}ms")
            if args.interval:
                time.sleep(max(0.0, args.interval - (time.perf_counter() - t0)))

    if latencies:
        q = statistics.quantiles(latencies, n=100)
        print(f"uploads: {len(latencies)}  failures: {failures}  p50={q[49] * 1000:.0f}ms  "
              f"p95={q[94] * 1000:.0f}ms  max={max(latencies) * 1000:.0f}ms")


if __name__ == "__main__":
    main()
