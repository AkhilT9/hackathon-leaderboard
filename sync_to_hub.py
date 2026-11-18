"""Sync local agentplay sessions to a Hackathon Control hub.

Participants can run this once to upload recent built maps, or with --watch
to build and push new/updated sessions automatically during a hackathon.

Examples:
    python sync_to_hub.py --name Akhil --team Observability --hub http://127.0.0.1:7400
    python sync_to_hub.py --name Akhil --team Observability --hub http://192.168.1.10:7400 --watch
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def _agentplay_root() -> Path:
    env = os.environ.get("AGENTPLAY_HOME")
    return Path(env).expanduser() if env else Path.home() / ".agentplay"


def _find_agentplay_exe() -> list[str]:
    found = shutil.which("agentplay")
    if found:
        return [found]
    win_scripts = Path(sys.executable).parent / "Scripts" / "agentplay.exe"
    if win_scripts.is_file():
        return [str(win_scripts)]
    user_scripts = Path.home() / "AppData" / "Roaming" / "Python" / f"Python{sys.version_info.major}{sys.version_info.minor}" / "Scripts" / "agentplay.exe"
    if user_scripts.is_file():
        return [str(user_scripts)]
    return [sys.executable, "-m", "agentplay"]


def run_build() -> None:
    env = os.environ.copy()
    antigravity_dir = Path.home() / ".gemini" / "antigravity"
    if antigravity_dir.is_dir() and "AGENTPLAY_ANTIGRAVITY_HOMES" not in env:
        env["AGENTPLAY_ANTIGRAVITY_HOMES"] = str(antigravity_dir)
    cmd = [*_find_agentplay_exe(), "build"]
    subprocess.run(cmd, env=env, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _map_path_for_row(root: Path, row: dict) -> Path | None:
    key = row.get("key")
    if isinstance(key, str) and key:
        p = root / "maps" / f"{key}.json"
        if p.is_file():
            return p
    return None


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def upload_map(hub_url: str, name: str, team: str, repo: str | None, map_path: Path) -> dict:
    params = {"participant": name, "team": team}
    if repo:
        params["repo"] = repo
    url = hub_url.rstrip("/") + "/api/upload?" + urllib.parse.urlencode(params)
    payload = gzip.compress(map_path.read_bytes())
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/gzip"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def sync_once(
    hub_url: str,
    name: str,
    team: str,
    repo: str | None,
    since_hours: float,
    seen_hashes: dict[str, str],
    skip_build: bool = False,
) -> int:
    if not skip_build:
        run_build()

    root = _agentplay_root()
    index_path = root / "index.json"
    if not index_path.is_file():
        print(f"No agentplay index found at {index_path}. Run `agentplay build` first.")
        return 0

    raw = json.loads(index_path.read_text(encoding="utf-8"))
    sessions = (raw.get("sessions") or {}).values()
    cutoff = datetime.now(UTC) - timedelta(hours=since_hours) if since_hours > 0 else None

    uploaded = 0
    for row in sessions:
        if row.get("role") in ("subagent", "helper") or int(row.get("calls") or 0) <= 0:
            continue
        sid = str(row.get("sessionId") or "")
        chash = str(row.get("contentHash") or row.get("updatedAt") or "")
        if not sid or seen_hashes.get(sid) == chash:
            continue

        started = _parse_iso(row.get("startedAt"))
        if cutoff is not None and started is not None and started < cutoff:
            continue

        map_path = _map_path_for_row(root, row)
        if map_path is None:
            continue

        try:
            res = upload_map(hub_url, name, team, repo, map_path)
            seen_hashes[sid] = chash
            uploaded += 1
            print(f"[ok] {sid} -> {res.get('calls')} calls, ${res.get('costUsd'):.2f}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            print(f"[err] {sid}: {exc}", file=sys.stderr)

    return uploaded


def main() -> None:
    ap = argparse.ArgumentParser(description="Upload local agentplay sessions to Hackathon Control.")
    ap.add_argument("--name", required=True, help="Participant display name")
    ap.add_argument("--team", required=True, help="Team name")
    ap.add_argument("--repo", default=None, help="Optional repo name override")
    ap.add_argument("--hub", default="http://127.0.0.1:7400", help="Hackathon Control URL")
    ap.add_argument("--hours", type=float, default=72.0, help="Only sync sessions from the last N hours (0 = all)")
    ap.add_argument("--watch", action="store_true", help="Keep polling and uploading new/changed sessions")
    ap.add_argument("--interval", type=int, default=30, help="Seconds between syncs in --watch mode")
    ap.add_argument("--no-build", action="store_true", help="Skip running `agentplay build` before uploading")
    args = ap.parse_args()

    seen: dict[str, str] = {}
    count = sync_once(args.hub, args.name, args.team, args.repo, args.hours, seen, skip_build=args.no_build)
    print(f"Sync complete: {count} session(s) uploaded to {args.hub}.")

    if not args.watch:
        return

    print(f"Watching every {args.interval}s (Ctrl+C to stop)...")
    try:
        while True:
            time.sleep(args.interval)
            sync_once(args.hub, args.name, args.team, args.repo, args.hours, seen, skip_build=args.no_build)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()

