"""Hackathon Control / Teams Leaderboard & Observability Server.

Serves an interactive multi-user Hackathon Control leaderboard on port 7400:
  - GET  /                  -> Main Dashboard (Rankings, Sparklines, MCP Calls, Commits, Replay Modal)
  - GET  /stage             -> Fullscreen Projector / Venue Stage View
  - GET  /join              -> 1-Click Participant Onboarding & Registration Page
  - GET  /join.ps1          -> Auto-generated Windows PowerShell 1-line sync script
  - GET  /join.sh           -> Auto-generated macOS/Linux Bash 1-line sync script
  - GET  /api/leaderboard   -> JSON leaderboard data & live activity feed
  - GET  /api/session       -> Detailed session replay map (Timeline, MCP breakdown, errors, fixes)
  - POST /api/upload        -> Ingests raw or gzipped agentplay session maps (.json / .json.gz)
"""

from __future__ import annotations

import argparse
import base64
from datetime import UTC, datetime
import gzip
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
from typing import Any
from urllib.parse import parse_qs, urlsplit

try:
    from agentplay import facts as ap_facts
    from agentplay import health as ap_health
except ImportError:
    ap_facts = None
    ap_health = None


BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "leaderboard_data.json"
UPLOADS_DIR = BASE_DIR / "uploaded_sessions"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
SPARKLINE_BUCKETS = 24
_LOCK = threading.Lock()


DEMO_PARTICIPANTS: list[dict[str, Any]] = [
    {
        "participant": "Aisha Bello",
        "team": "Merge Conflict",
        "repo": "pet-adopt",
        "agentTool": "claude-code",
        "isDemo": True,
        "connected": False,
        "sessionsCount": 17,
        "toolCalls": 474,
        "mcpCalls": 42,
        "errors": 33,
        "failingPct": 7,
        "prs": 14,
        "commits": 21,
        "spendUsd": 1.87,
        "runHealth": 74,
        "mentorAlert": False,
        "mentorReason": "",
        "lastActionTs": None,
        "lastActionLabel": "22 h ago",
        "sparkline": [{"calls": (i % 5) + 1, "errors": 1 if i in (4, 15) else 0} for i in range(SPARKLINE_BUCKETS)],
        "sessions": [],
    },
    {
        "participant": "Diego Alvarez",
        "team": "Null Pointers",
        "repo": "transit-ate",
        "agentTool": "cursor",
        "isDemo": True,
        "connected": False,
        "sessionsCount": 15,
        "toolCalls": 450,
        "mcpCalls": 68,
        "errors": 0,
        "failingPct": 0,
        "prs": 3,
        "commits": 20,
        "spendUsd": 1.69,
        "runHealth": 87,
        "mentorAlert": False,
        "mentorReason": "",
        "lastActionTs": None,
        "lastActionLabel": "22 h ago",
        "sparkline": [{"calls": (i % 4) + 1, "errors": 0} for i in range(SPARKLINE_BUCKETS)],
        "sessions": [],
    },
    {
        "participant": "Kenji Sato",
        "team": "Byte Me",
        "repo": "recipe-remix",
        "agentTool": "antigravity-cli",
        "isDemo": True,
        "connected": False,
        "sessionsCount": 15,
        "toolCalls": 428,
        "mcpCalls": 36,
        "errors": 21,
        "failingPct": 5,
        "prs": 7,
        "commits": 20,
        "spendUsd": 1.80,
        "runHealth": 70,
        "mentorAlert": False,
        "mentorReason": "",
        "lastActionTs": None,
        "lastActionLabel": "22 h ago",
        "sparkline": [{"calls": (i % 6) + 1, "errors": 1 if i == 9 else 0} for i in range(SPARKLINE_BUCKETS)],
        "sessions": [],
    },
    {
        "participant": "Omar Haddad",
        "team": "Stack Smashers",
        "repo": "transit-ate",
        "agentTool": "opencode",
        "isDemo": True,
        "connected": False,
        "sessionsCount": 16,
        "toolCalls": 433,
        "mcpCalls": 24,
        "errors": 69,
        "failingPct": 16,
        "prs": 4,
        "commits": 12,
        "spendUsd": 1.85,
        "runHealth": 60,
        "mentorAlert": True,
        "mentorReason": "High error rate (16% failing calls)",
        "lastActionTs": None,
        "lastActionLabel": "22 h ago",
        "sparkline": [{"calls": (i % 4) + 2, "errors": 1 if i % 6 == 0 else 0} for i in range(SPARKLINE_BUCKETS)],
        "sessions": [],
    },
    {
        "participant": "Sofia Rossi",
        "team": "Byte Me",
        "repo": "carbon-calc",
        "agentTool": "cursor",
        "isDemo": True,
        "connected": False,
        "sessionsCount": 17,
        "toolCalls": 424,
        "mcpCalls": 51,
        "errors": 38,
        "failingPct": 9,
        "prs": 8,
        "commits": 23,
        "spendUsd": 1.91,
        "runHealth": 72,
        "mentorAlert": False,
        "mentorReason": "",
        "lastActionTs": None,
        "lastActionLabel": "22 h ago",
        "sparkline": [{"calls": (i % 5) + 1, "errors": 1 if i in (7, 19) else 0} for i in range(SPARKLINE_BUCKETS)],
        "sessions": [],
    },
    {
        "participant": "Tom Nguyen",
        "team": "Merge Conflict",
        "repo": "pet-adopt",
        "agentTool": "claude-code",
        "isDemo": True,
        "connected": False,
        "sessionsCount": 16,
        "toolCalls": 450,
        "mcpCalls": 18,
        "errors": 72,
        "failingPct": 16,
        "prs": 5,
        "commits": 12,
        "spendUsd": 2.00,
        "runHealth": 61,
        "mentorAlert": True,
        "mentorReason": "72 errors logged across sessions",
        "lastActionTs": None,
        "lastActionLabel": "22 h ago",
        "sparkline": [{"calls": (i % 4) + 1, "errors": 1 if i in (2, 10, 18) else 0} for i in range(SPARKLINE_BUCKETS)],
        "sessions": [],
    },
    {
        "participant": "Arjun Patel",
        "team": "Lambda Llamas",
        "repo": "pet-adopt",
        "agentTool": "antigravity-cli",
        "isDemo": True,
        "connected": False,
        "sessionsCount": 14,
        "toolCalls": 455,
        "mcpCalls": 80,
        "errors": 36,
        "failingPct": 8,
        "prs": 9,
        "commits": 18,
        "spendUsd": 1.97,
        "runHealth": 78,
        "mentorAlert": False,
        "mentorReason": "",
        "lastActionTs": None,
        "lastActionLabel": "22 h ago",
        "sparkline": [{"calls": (i % 6) + 1, "errors": 1 if i == 12 else 0} for i in range(SPARKLINE_BUCKETS)],
        "sessions": [],
    },
    {
        "participant": "Priya Raman",
        "team": "Null Pointers",
        "repo": "pet-adopt",
        "agentTool": "copilot-vscode",
        "isDemo": True,
        "connected": False,
        "sessionsCount": 16,
        "toolCalls": 429,
        "mcpCalls": 28,
        "errors": 56,
        "failingPct": 13,
        "prs": 7,
        "commits": 22,
        "spendUsd": 1.91,
        "runHealth": 65,
        "mentorAlert": False,
        "mentorReason": "",
        "lastActionTs": None,
        "lastActionLabel": "22 h ago",
        "sparkline": [{"calls": (i % 5) + 1, "errors": 1 if i in (3, 14, 21) else 0} for i in range(SPARKLINE_BUCKETS)],
        "sessions": [],
    },
]


def _default_state() -> dict[str, Any]:
    return {"uploadedSessions": [], "liveActivity": []}


def _load_state() -> dict[str, Any]:
    if not DATA_FILE.is_file():
        return _default_state()
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                "uploadedSessions": list(data.get("uploadedSessions") or []),
                "liveActivity": list(data.get("liveActivity") or []),
            }
    except (OSError, ValueError):
        pass
    return _default_state()


def _save_state(state: dict[str, Any]) -> None:
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(DATA_FILE)


def _decode_map_bytes(raw: bytes) -> dict[str, Any]:
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    doc = json.loads(raw.decode("utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("Uploaded file must contain a JSON object.")
    return doc


def _validate_map(doc: dict[str, Any]) -> None:
    if not isinstance(doc.get("session"), dict) or not isinstance(doc.get("events"), list):
        raise ValueError("Not a valid agentplay session map (missing 'session' or 'events').")


def _sparkline_from_events(events: list[dict[str, Any]], duration_ms: int) -> list[dict[str, int]]:
    buckets = [{"calls": 0, "errors": 0} for _ in range(SPARKLINE_BUCKETS)]
    non_call = {"user", "llm", "compaction", "delay", "interrupt", "turn_end"}
    tool_events = [e for e in events if isinstance(e, dict) and e.get("kind") not in non_call]
    if not tool_events:
        return buckets
    max_t = max([duration_ms, *(int(e.get("t") or 0) for e in tool_events), 1])
    for e in tool_events:
        t = max(0, int(e.get("t") or 0))
        idx = min(SPARKLINE_BUCKETS - 1, int((t / max_t) * SPARKLINE_BUCKETS))
        buckets[idx]["calls"] += 1
        if e.get("err"):
            buckets[idx]["errors"] += 1
    return buckets


def _analyze_events(events: list[dict[str, Any]], files: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract commit counts, MCP tool counts, tool frequencies, error sequences, and formatted timeline."""
    non_call = {"user", "llm", "compaction", "delay", "interrupt", "turn_end"}
    core_tools = {"bash", "read", "edit", "write", "grep"}

    commits = 0
    mcp_calls = 0
    tool_counts: dict[str, int] = {}
    consecutive_errs = 0
    max_consecutive_errs = 0
    total_errs = 0
    timeline: list[dict[str, Any]] = []

    file_map: dict[int, str] = {}
    for f in files:
        if isinstance(f, dict) and "id" in f and "path" in f:
            file_map[f["id"]] = str(f["path"])

    step_num = 1
    for e in events:
        if not isinstance(e, dict):
            continue
        kind = str(e.get("kind") or "").lower()
        tool_name = str(e.get("tool") or "").strip()
        verb = str(e.get("verb") or "").strip()
        cat = str(e.get("cat") or "").lower()
        err = bool(e.get("err"))
        task_num = int(e.get("task") or 1)
        dur_ms = int(e.get("dur") or 0)

        if err:
            total_errs += 1
            consecutive_errs += 1
            if consecutive_errs > max_consecutive_errs:
                max_consecutive_errs = consecutive_errs
        elif kind not in ("user", "llm", "delay"):
            consecutive_errs = 0

        vcs_action = str(e.get("vcs", {}).get("action") if isinstance(e.get("vcs"), dict) else "").lower()
        if vcs_action == "commit" or "git commit" in verb.lower() or (tool_name.lower() == "bash" and "commit" in verb.lower()):
            commits += 1

        is_tool = kind not in non_call
        is_mcp = False
        display_tool = tool_name or kind

        if is_tool:
            if (
                cat == "tool"
                or tool_name.lower().startswith("mcp")
                or "mcp" in tool_name.lower()
                or tool_name.lower() in ("manage_task", "call_mcp_tool", "websearch", "todo_write", "search_replace")
                or (tool_name.lower() not in core_tools and tool_name.lower() != "bash")
            ):
                is_mcp = True
                mcp_calls += 1

            tool_key = tool_name or verb or cat or "Tool"
            tool_counts[tool_key] = tool_counts.get(tool_key, 0) + 1

        target_info = ""
        targets = e.get("targets")
        if isinstance(targets, list) and targets:
            first_t = targets[0]
            if isinstance(first_t, dict):
                if "file" in first_t and first_t["file"] in file_map:
                    target_info = file_map[first_t["file"]]
                elif "label" in first_t:
                    target_info = str(first_t["label"])

        summary = verb or target_info or display_tool

        if kind not in ("delay", "compaction"):
            timeline.append({
                "step": step_num,
                "task": task_num,
                "kind": kind,
                "cat": cat,
                "tool": tool_name or ("MCP Tool" if is_mcp else kind),
                "verb": verb,
                "summary": summary,
                "target": target_info,
                "durMs": dur_ms,
                "err": err,
                "retry": bool(e.get("retryOf") or (int(e.get("attempt") or 1) > 1)),
                "isMcp": is_mcp,
            })
            step_num += 1

    mentor_alert = False
    mentor_reason = ""
    if max_consecutive_errs >= 3:
        mentor_alert = True
        mentor_reason = f"Stuck in failure loop: {max_consecutive_errs} consecutive errors"
    elif total_errs >= 10:
        mentor_alert = True
        mentor_reason = f"High error count: {total_errs} errors encountered"

    sorted_tools = sorted([{"name": k, "count": v} for k, v in tool_counts.items()], key=lambda x: x["count"], reverse=True)

    return {
        "commits": commits,
        "mcpCalls": mcp_calls,
        "topTools": sorted_tools[:8],
        "mentorAlert": mentor_alert,
        "mentorReason": mentor_reason,
        "timeline": timeline,
    }


def _compute_run_health(session_facts_list: list[dict[str, Any]]) -> int | None:
    if not session_facts_list:
        return None
    if ap_health is not None:
        rows = [{"facts": f} for f in session_facts_list if isinstance(f, dict)]
        if not rows:
            return None
        totals = ap_health.totals(rows)
        if totals.calls == 0 and totals.sessions == 0:
            return None
        comps = ap_health.components(totals)
        return round(sum(20.0 * (v if v is not None else 1.0) for v in comps.values()))
    total_calls = sum(int(f.get("calls") or 0) for f in session_facts_list)
    total_errors = sum(int(f.get("errors") or 0) for f in session_facts_list)
    if total_calls <= 0:
        return None
    return max(0, min(100, round(100 * (1.0 - min(1.0, 4.0 * total_errors / total_calls)))))


def _format_relative_age(iso_ts: str | None) -> str:
    if not iso_ts:
        return "just now"
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        delta_s = max(0, int((datetime.now(UTC) - dt).total_seconds()))
    except ValueError:
        return "just now"
    if delta_s < 60:
        return "just now"
    if delta_s < 3600:
        return f"{delta_s // 60} m ago"
    if delta_s < 86400:
        return f"{delta_s // 3600} h ago"
    return f"{delta_s // 86400} d ago"


def _extract_session_record(doc: dict[str, Any], participant: str, team: str, repo_override: str | None) -> dict[str, Any]:
    _validate_map(doc)
    sess = doc["session"]
    totals = doc.get("totals") or {}
    events = doc.get("events") or []
    files = doc.get("files") or []
    repos = doc.get("repos") or []

    detected_repo = ""
    if repos and isinstance(repos[0], dict):
        detected_repo = str(repos[0].get("name") or repos[0].get("remote") or "")
    repo = (repo_override or detected_repo or "local-workspace").strip()

    facts_data: dict[str, Any] = {}
    if ap_facts is not None:
        try:
            facts_data = ap_facts.compute(doc)
        except Exception:
            facts_data = {}

    analysis = _analyze_events(events, files)

    session_id = str(sess.get("id") or f"upload:{datetime.now(UTC).timestamp()}")
    calls = int(totals.get("calls") or facts_data.get("calls") or len(events))
    errors = int(totals.get("errors") or facts_data.get("errors") or 0)
    prs = int(totals.get("prsCreated") or facts_data.get("prsCreated") or len(doc.get("prs") or []))
    commits = max(int(totals.get("commits") or 0), analysis["commits"])
    mcp_calls = analysis["mcpCalls"]
    cost_usd = float(totals.get("costUsd") or facts_data.get("costUsd") or 0.0)
    duration_ms = int(sess.get("durationMs") or 0)
    agent_tool = str(sess.get("agentTool") or "unknown")
    started_at = str(sess.get("startedAt") or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    uploaded_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not facts_data:
        facts_data = {
            "calls": calls,
            "errors": errors,
            "retries": int(totals.get("retries") or 0),
            "prsCreated": prs,
            "edited": int(totals.get("filesTouched") or 0) > 0,
            "compactions": int(totals.get("compactions") or 0),
        }

    return {
        "sessionId": session_id,
        "participant": participant.strip(),
        "team": team.strip(),
        "repo": repo,
        "agentTool": agent_tool,
        "startedAt": started_at,
        "uploadedAt": uploaded_at,
        "durationMs": duration_ms,
        "calls": calls,
        "errors": errors,
        "prs": prs,
        "commits": commits,
        "mcpCalls": mcp_calls,
        "costUsd": round(cost_usd, 4),
        "tokens": int(totals.get("tokens") or 0),
        "filesTouched": int(totals.get("filesTouched") or len(files)),
        "sparkline": _sparkline_from_events(events, duration_ms),
        "facts": facts_data,
        "topTools": analysis["topTools"],
        "mentorAlert": analysis["mentorAlert"],
        "mentorReason": analysis["mentorReason"],
    }


def _save_raw_map(session_id: str, doc: dict[str, Any]) -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", session_id) + ".json"
    (UPLOADS_DIR / safe_name).write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")


def _get_raw_map(session_id: str) -> dict[str, Any] | None:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", session_id) + ".json"
    p = UPLOADS_DIR / safe_name
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _aggregate_participants(uploaded: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for rec in uploaded:
        key = (rec["participant"].lower(), rec["team"].lower())
        grouped.setdefault(key, []).append(rec)

    real_rows: list[dict[str, Any]] = []
    for _, recs in grouped.items():
        latest = max(recs, key=lambda r: r.get("uploadedAt") or "")
        total_calls = sum(int(r.get("calls") or 0) for r in recs)
        total_mcp = sum(int(r.get("mcpCalls") or 0) for r in recs)
        total_errors = sum(int(r.get("errors") or 0) for r in recs)
        total_prs = sum(int(r.get("prs") or 0) for r in recs)
        total_commits = sum(int(r.get("commits") or 0) for r in recs)
        total_spend = round(sum(float(r.get("costUsd") or 0.0) for r in recs), 2)
        failing_pct = round(100 * total_errors / total_calls) if total_calls > 0 else None

        combined_spark = [{"calls": 0, "errors": 0} for _ in range(SPARKLINE_BUCKETS)]
        for r in recs:
            sp = r.get("sparkline") or []
            for idx in range(min(SPARKLINE_BUCKETS, len(sp))):
                combined_spark[idx]["calls"] += int(sp[idx].get("calls") or 0)
                combined_spark[idx]["errors"] += int(sp[idx].get("errors") or 0)

        run_health = _compute_run_health([r.get("facts") or {} for r in recs])
        last_ts = latest.get("uploadedAt")

        has_alert = any(bool(r.get("mentorAlert")) for r in recs) or (failing_pct is not None and failing_pct >= 15)
        reasons = [r.get("mentorReason") for r in recs if r.get("mentorReason")]
        alert_reason = reasons[0] if reasons else ("High error rate" if has_alert else "")

        real_rows.append(
            {
                "participant": latest["participant"],
                "team": latest["team"],
                "repo": latest["repo"],
                "agentTool": latest.get("agentTool", "unknown"),
                "isDemo": False,
                "connected": True,
                "sessionsCount": len(recs),
                "toolCalls": total_calls,
                "mcpCalls": total_mcp,
                "errors": total_errors,
                "failingPct": failing_pct,
                "prs": total_prs,
                "commits": total_commits,
                "spendUsd": total_spend,
                "runHealth": run_health,
                "mentorAlert": has_alert,
                "mentorReason": alert_reason,
                "lastActionTs": last_ts,
                "lastActionLabel": _format_relative_age(last_ts),
                "sparkline": combined_spark,
                "sessions": [
                    {
                        "sessionId": r["sessionId"],
                        "agentTool": r["agentTool"],
                        "repo": r["repo"],
                        "calls": r["calls"],
                        "mcpCalls": r.get("mcpCalls", 0),
                        "errors": r["errors"],
                        "commits": r.get("commits", 0),
                        "spendUsd": round(float(r.get("costUsd") or 0.0), 2),
                        "durationMs": r["durationMs"],
                        "startedAt": r["startedAt"],
                        "uploadedAt": r["uploadedAt"],
                        "mentorAlert": r.get("mentorAlert", False),
                    }
                    for r in sorted(recs, key=lambda x: x.get("uploadedAt") or "", reverse=True)
                ],
            }
        )

    real_rows.sort(key=lambda r: (r["toolCalls"], r["sessionsCount"]), reverse=True)

    placeholder = (
        []
        if real_rows
        else [
            {
                "participant": "Your Name",
                "team": "Test",
                "repo": "",
                "agentTool": "agentplay",
                "isDemo": True,
                "connected": False,
                "sessionsCount": 0,
                "toolCalls": 0,
                "mcpCalls": 0,
                "errors": 0,
                "failingPct": None,
                "prs": 0,
                "commits": 0,
                "spendUsd": 0.00,
                "runHealth": None,
                "mentorAlert": False,
                "mentorReason": "",
                "lastActionTs": None,
                "lastActionLabel": "never",
                "sparkline": [{"calls": 0, "errors": 0} for _ in range(SPARKLINE_BUCKETS)],
                "sessions": [],
            }
        ]
    )

    return [*real_rows, *DEMO_PARTICIPANTS, *placeholder]


def _aggregate_teams(participants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_team: dict[str, list[dict[str, Any]]] = {}
    for p in participants:
        by_team.setdefault(p["team"], []).append(p)

    teams: list[dict[str, Any]] = []
    for team_name, members in by_team.items():
        calls = sum(int(m["toolCalls"]) for m in members)
        mcp = sum(int(m.get("mcpCalls") or 0) for m in members)
        errs = sum(int(m["errors"]) for m in members)
        health_vals = [m["runHealth"] for m in members if m["runHealth"] is not None]
        has_alert = any(bool(m.get("mentorAlert")) for m in members)
        teams.append(
            {
                "team": team_name,
                "members": len(members),
                "connected": sum(1 for m in members if m["connected"]),
                "repos": sorted({m["repo"] for m in members if m.get("repo")}),
                "sessionsCount": sum(int(m["sessionsCount"]) for m in members),
                "toolCalls": calls,
                "mcpCalls": mcp,
                "errors": errs,
                "failingPct": round(100 * errs / calls) if calls > 0 else None,
                "prs": sum(int(m["prs"]) for m in members),
                "commits": sum(int(m["commits"]) for m in members),
                "spendUsd": round(sum(float(m["spendUsd"]) for m in members), 2),
                "runHealth": round(sum(health_vals) / len(health_vals)) if health_vals else None,
                "mentorAlert": has_alert,
                "hasRealUploads": any(not m["isDemo"] for m in members),
            }
        )
    teams.sort(key=lambda t: (t["hasRealUploads"], t["toolCalls"]), reverse=True)
    return teams


def build_leaderboard_payload(include_demo: bool = True) -> dict[str, Any]:
    with _LOCK:
        state = _load_state()
    all_participants = _aggregate_participants(state["uploadedSessions"])
    participants = all_participants if include_demo else [p for p in all_participants if not p["isDemo"]]
    teams = _aggregate_teams(participants)
    total_sessions = sum(int(p["sessionsCount"]) for p in participants)
    total_calls = sum(int(p["toolCalls"]) for p in participants)
    total_mcp = sum(int(p.get("mcpCalls") or 0) for p in participants)
    total_failed = sum(int(p["errors"]) for p in participants)
    total_prs = sum(int(p["prs"]) for p in participants)
    total_commits = sum(int(p["commits"]) for p in participants)
    total_spend = round(sum(float(p["spendUsd"]) for p in participants), 2)
    connected = sum(1 for p in participants if p["connected"])
    working = sum(1 for p in participants if p["connected"] or not p["isDemo"])

    return {
        "updatedAt": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "summary": {
            "participantCount": len(participants),
            "workingCount": working,
            "connectedCount": connected,
            "teamCount": len(teams),
            "sessions": total_sessions,
            "toolCalls": total_calls,
            "mcpCalls": total_mcp,
            "failedCalls": total_failed,
            "prs": total_prs,
            "commits": total_commits,
            "spendUsd": total_spend,
        },
        "participants": participants,
        "teams": teams,
        "liveActivity": state["liveActivity"][:30],
    }


def ingest_upload(doc: dict[str, Any], participant: str, team: str, repo_override: str | None = None) -> dict[str, Any]:
    rec = _extract_session_record(doc, participant=participant, team=team, repo_override=repo_override)
    _save_raw_map(rec["sessionId"], doc)

    with _LOCK:
        state = _load_state()
        state["uploadedSessions"] = [
            s for s in state["uploadedSessions"]
            if not (s["sessionId"] == rec["sessionId"] and s["participant"].lower() == rec["participant"].lower())
        ]
        state["uploadedSessions"].insert(0, rec)

        activity_item = {
            "id": f"act:{datetime.now(UTC).timestamp()}",
            "participant": rec["participant"],
            "team": rec["team"],
            "repo": rec["repo"],
            "agentTool": rec["agentTool"],
            "calls": rec["calls"],
            "mcpCalls": rec["mcpCalls"],
            "commits": rec["commits"],
            "errors": rec["errors"],
            "mentorAlert": rec["mentorAlert"],
            "at": "just now",
            "iso": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        state["liveActivity"].insert(0, activity_item)
        state["liveActivity"] = state["liveActivity"][:50]
        _save_state(state)

    return rec


# ==============================================================================
# HTML TEMPLATES (Dashboard, Stage View, Onboarding)
# ==============================================================================

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Hackathon Control &middot; Multi-Agent Leaderboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f8fafc; color: #0f172a; padding: 24px; font-size: 13px; }
    .nav-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid #e2e8f0; }
    .nav-links a { color: #2563eb; text-decoration: none; font-weight: 600; margin-left: 16px; font-size: 13px; }
    .nav-links a:hover { text-decoration: underline; }
    .header { margin-bottom: 16px; }
    .header h1 { font-size: 22px; font-weight: 700; color: #0f172a; }
    .header .subtitle { font-size: 13px; color: #475569; margin-top: 4px; }
    .controls { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
    .tab-group { display: inline-flex; background: #e2e8f0; border-radius: 6px; padding: 2px; }
    .tab-btn { border: none; background: transparent; padding: 6px 14px; font-size: 13px; font-weight: 500; color: #475569; border-radius: 4px; cursor: pointer; }
    .tab-btn.active { background: #fff; color: #0f172a; box-shadow: 0 1px 2px rgba(0,0,0,0.06); }
    .search-input { padding: 6px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px; width: 220px; }
    .select-dropdown { padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px; background: #fff; }
    .upload-btn { background: #0f172a; color: #fff; border: none; padding: 7px 16px; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; margin-left: auto; display: inline-flex; align-items: center; gap: 6px; }
    .upload-btn:hover { background: #1e293b; }
    .legend { display: flex; align-items: center; gap: 14px; font-size: 11px; color: #64748b; margin-left: 8px; }
    .legend-item { display: flex; align-items: center; gap: 4px; }
    .dot-blue { width: 7px; height: 7px; background: #3b82f6; border-radius: 50%; }
    .dot-red { width: 7px; height: 7px; background: #ef4444; border-radius: 50%; }
    .dot-purple { width: 7px; height: 7px; background: #a855f7; border-radius: 50%; }
    .main-grid { display: grid; grid-template-columns: 1fr 340px; gap: 20px; }
    @media (max-width: 1024px) { .main-grid { grid-template-columns: 1fr; } }
    .table-container { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; overflow-x: auto; box-shadow: 0 1px 3px rgba(0,0,0,0.02); }
    table { width: 100%; border-collapse: collapse; text-align: left; }
    th { background: #f8fafc; padding: 10px 14px; font-size: 11.5px; font-weight: 600; color: #64748b; text-transform: uppercase; border-bottom: 1px solid #e2e8f0; }
    td { padding: 12px 14px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }
    tr:last-child td { border-bottom: none; }
    tr.clickable:hover { background: #f8fafc; cursor: pointer; }
    .num { text-align: right; font-variant-numeric: tabular-nums; }
    .participant-cell { display: flex; align-items: center; gap: 8px; }
    .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #94a3b8; flex-shrink: 0; }
    .status-dot.live { background: #10b981; box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.2); }
    .p-name { font-weight: 600; color: #0f172a; display: flex; align-items: center; gap: 6px; }
    .p-team { font-size: 11.5px; color: #64748b; }
    .badge-real { background: #dcfce7; color: #166534; font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 600; }
    .badge-alert { background: #fee2e2; color: #991b1b; font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; animation: pulse 2s infinite; }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    .badge-mcp { background: #f3e8ff; color: #6b21a8; font-size: 10.5px; padding: 2px 6px; border-radius: 4px; font-weight: 600; }
    .badge-commit { background: #e0e7ff; color: #3730a3; font-size: 10.5px; padding: 2px 6px; border-radius: 4px; font-weight: 600; }
    .sparkline { display: flex; align-items: flex-end; gap: 2px; height: 18px; width: 140px; }
    .spark-bar { flex: 1; border-radius: 1px; min-width: 2px; }
    .health-bar-container { display: flex; align-items: center; gap: 6px; justify-content: flex-end; }
    .health-track { width: 44px; height: 4px; background: #e2e8f0; border-radius: 2px; overflow: hidden; }
    .health-line { height: 100%; background: #0f172a; }
    .live-activity-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.02); height: fit-content; }
    .live-activity-card h3 { font-size: 14px; font-weight: 700; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
    .activity-item { padding: 9px 0; border-top: 1px solid #f1f5f9; font-size: 12px; }
    .activity-item:first-child { border-top: none; padding-top: 0; }
    .activity-meta { font-size: 11px; color: #64748b; margin-top: 2px; display: flex; gap: 6px; flex-wrap: wrap; }
    .modal-backdrop { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.55); display: none; align-items: center; justify-content: center; z-index: 50; }
    .modal-backdrop.open { display: flex; }
    .modal { background: #fff; border-radius: 10px; padding: 24px; width: 500px; max-width: 94vw; box-shadow: 0 20px 45px rgba(15, 23, 42, 0.25); }
    .modal.large { width: 840px; max-height: 90vh; overflow-y: auto; }
    .field { margin-bottom: 12px; }
    .field label { display: block; font-size: 12px; font-weight: 600; color: #334155; margin-bottom: 4px; }
    .field input { width: 100%; padding: 8px 10px; font-size: 13px; border: 1px solid #cbd5e1; border-radius: 6px; }
    .modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }
    .btn-secondary { padding: 7px 14px; font-size: 13px; border: 1px solid #cbd5e1; background: #fff; border-radius: 6px; cursor: pointer; }
    .stat-pills { display: flex; gap: 8px; flex-wrap: wrap; margin: 14px 0; }
    .stat-pill { background: #f1f5f9; padding: 6px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; color: #334155; }
    .stat-pill span { color: #64748b; font-weight: 400; margin-left: 4px; }
    .timeline-container { margin-top: 16px; border: 1px solid #e2e8f0; border-radius: 6px; max-height: 380px; overflow-y: auto; background: #fafafa; }
    .timeline-row { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-bottom: 1px solid #eee; font-size: 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .timeline-row.err { background: #fff1f2; }
    .timeline-row .step-badge { color: #64748b; font-size: 11px; min-width: 32px; }
    .timeline-row .kind-tag { padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; text-transform: uppercase; }
    .kind-tag.bash { background: #e0f2fe; color: #0369a1; }
    .kind-tag.read { background: #fef3c7; color: #b45309; }
    .kind-tag.write { background: #dcfce7; color: #15803d; }
    .kind-tag.mcp { background: #f3e8ff; color: #7e22ce; }
    .kind-tag.web { background: #e0e7ff; color: #4338ca; }
    .timeline-row .action-desc { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .timeline-row .dur { color: #64748b; font-size: 11px; min-width: 45px; text-align: right; }
    .timeline-row .err-tag { background: #dc2626; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; }
    .timeline-row .retry-tag { background: #f59e0b; color: #fff; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; }
  </style>
</head>
<body>
  <div class="nav-bar">
    <div><strong>HACKATHON OBSERVABILITY</strong> &middot; Real-time AI Agent Telemetry</div>
    <div class="nav-links">
      <a href="/">Dashboard</a>
      <a href="/stage" target="_blank">&#127916; Stage Projector View</a>
      <a href="/join" target="_blank">&#9889; 1-Line Quick Join</a>
    </div>
  </div>

  <div class="header">
    <h1>Hackathon control</h1>
    <div class="subtitle" id="summarySubtitle">Loading leaderboard...</div>
  </div>

  <div class="controls">
    <div class="tab-group">
      <button class="tab-btn active" id="tabPeople" onclick="setTab('people')">People</button>
      <button class="tab-btn" id="tabTeams" onclick="setTab('teams')">Teams</button>
    </div>
    <input type="text" class="search-input" id="searchBox" placeholder="Find participant, team or tool..." oninput="render()">
    <select class="select-dropdown" id="teamFilter" onchange="render()">
      <option value="all">All teams</option>
    </select>
    <select class="select-dropdown" id="scopeFilter" onchange="loadLeaderboard()">
      <option value="all">Everyone</option>
      <option value="real">Uploaded sessions only</option>
    </select>
    <button class="upload-btn" onclick="openUploadModal()">+ Upload session</button>

    <div class="legend">
      <div class="legend-item"><span class="dot-blue"></span> tool call</div>
      <div class="legend-item"><span class="dot-purple"></span> MCP call</div>
      <div class="legend-item"><span class="dot-red"></span> error</div>
    </div>
  </div>

  <div class="main-grid">
    <div class="table-container">
      <table id="mainTable">
        <thead id="tableHead"></thead>
        <tbody id="tableBody"></tbody>
      </table>
    </div>

    <div class="live-activity-card">
      <h3>Live activity <span id="actCount" style="font-size:11px;color:#64748b;font-weight:400;"></span></h3>
      <div id="liveActivityBody">
        <p style="color:#94a3b8;font-size:12px;">Activity will show up here as participants run agent sessions.</p>
      </div>
    </div>
  </div>

  <!-- Upload Modal -->
  <div class="modal-backdrop" id="uploadModal">
    <div class="modal">
      <h2 style="font-size:17px;margin-bottom:6px;">Upload agentplay session</h2>
      <p style="font-size:12.5px;color:#475569;margin-bottom:16px;">
        Upload a redacted map (<code>.json</code> or <code>.json.gz</code>). No prompts or code are sent.
      </p>
      <div class="field">
        <label for="upName">Participant name</label>
        <input type="text" id="upName" value="Akhil">
      </div>
      <div class="field">
        <label for="upTeam">Team name</label>
        <input type="text" id="upTeam" value="Observability">
      </div>
      <div class="field">
        <label for="upFile">Session map file</label>
        <input type="file" id="upFile" accept=".json,.gz">
      </div>
      <div id="uploadStatus" style="font-size:12px;margin-top:8px;"></div>
      <div class="modal-actions">
        <button class="btn-secondary" onclick="closeUploadModal()">Cancel</button>
        <button class="upload-btn" onclick="submitUpload()">Upload session</button>
      </div>
    </div>
  </div>

  <!-- Interactive Session Replay Modal ("You can see his session") -->
  <div class="modal-backdrop" id="replayModal">
    <div class="modal large">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;">
        <div>
          <h2 id="repTitle" style="font-size:18px;">Session Replay</h2>
          <div id="repSubtitle" style="font-size:12.5px;color:#64748b;margin-top:2px;"></div>
        </div>
        <button class="btn-secondary" onclick="closeReplayModal()">&times; Close</button>
      </div>

      <div id="repAlertBox" style="display:none;margin-top:12px;padding:10px 12px;border-radius:6px;background:#fee2e2;border:1px solid #fca5a5;color:#991b1b;font-size:12.5px;">
        <strong>&#9888; Mentor SOS Alert:</strong> <span id="repAlertMsg"></span>
      </div>

      <div class="stat-pills" id="repPills"></div>

      <div style="margin-top:14px;">
        <h4 style="font-size:12px;color:#475569;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">Top Tools &amp; MCP Usage</h4>
        <div id="repToolsList" style="display:flex;gap:6px;flex-wrap:wrap;"></div>
      </div>

      <div style="margin-top:18px;">
        <h4 style="font-size:12px;color:#475569;margin-bottom:6px;text-transform:uppercase;letter-spacing:0.5px;">Step-by-Step Chronological Timeline</h4>
        <div class="timeline-container" id="repTimeline"></div>
      </div>
    </div>
  </div>

  <script>
    let currentTab = 'people';
    let cachedData = null;

    function esc(s) {
      return String(s ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[c]));
    }

    function setTab(tab) {
      currentTab = tab;
      document.getElementById('tabPeople').classList.toggle('active', tab === 'people');
      document.getElementById('tabTeams').classList.toggle('active', tab === 'teams');
      render();
    }

    function openUploadModal() {
      document.getElementById('uploadStatus').textContent = '';
      document.getElementById('uploadModal').classList.add('open');
    }

    function closeUploadModal() {
      document.getElementById('uploadModal').classList.remove('open');
    }

    function closeReplayModal() {
      document.getElementById('replayModal').classList.remove('open');
    }

    async function openParticipantReplay(name) {
      if (!cachedData) return;
      const p = cachedData.participants.find(x => x.participant === name);
      if (!p) return;

      document.getElementById('repTitle').innerHTML = `${esc(p.participant)} <span style="font-weight:400;color:#64748b;">(${esc(p.team)})</span>`;
      document.getElementById('repSubtitle').innerHTML = `Agent: <strong>${esc(p.agentTool || 'AI Agent')}</strong> &middot; ${p.sessionsCount} session(s) &middot; ${esc(p.repo || 'workspace')}`;

      const alertBox = document.getElementById('repAlertBox');
      if (p.mentorAlert) {
        alertBox.style.display = 'block';
        document.getElementById('repAlertMsg').textContent = p.mentorReason || 'Frequent errors detected. Mentor assistance suggested.';
      } else {
        alertBox.style.display = 'none';
      }

      document.getElementById('repPills').innerHTML = `
        <div class="stat-pill">&#9889; ${p.toolCalls} <span>Calls</span></div>
        <div class="stat-pill" style="background:#f3e8ff;color:#6b21a8;">&#129513; ${p.mcpCalls || 0} <span>MCP Calls</span></div>
        <div class="stat-pill" style="background:#e0e7ff;color:#3730a3;">&#128230; ${p.commits || 0} <span>Commits</span></div>
        <div class="stat-pill" style="${p.errors > 0 ? 'background:#fee2e2;color:#991b1b;' : ''}">&#10060; ${p.errors} <span>Errors</span></div>
        <div class="stat-pill">&#128176; $${p.spendUsd.toFixed(2)} <span>Spend</span></div>
        <div class="stat-pill">&#10084;&#65039; ${p.runHealth ?? '&mdash;'} <span>Run Health</span></div>
      `;

      const repTimeline = document.getElementById('repTimeline');
      const repTools = document.getElementById('repToolsList');

      if (!p.sessions || !p.sessions.length) {
        repTools.innerHTML = '<div style="font-size:12px;color:#94a3b8;">Sample demo participant. Upload a real session to inspect the live timeline.</div>';
        repTimeline.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;">No raw map uploaded for demo user.</div>';
        document.getElementById('replayModal').classList.add('open');
        return;
      }

      repTimeline.innerHTML = '<div style="padding:20px;text-align:center;color:#64748b;">Loading session steps...</div>';
      document.getElementById('replayModal').classList.add('open');

      try {
        const latestSessionId = p.sessions[0].sessionId;
        const res = await fetch('/api/session?id=' + encodeURIComponent(latestSessionId));
        if (!res.ok) throw new Error('Session not found');
        const sessionDetail = await res.json();

        const tools = sessionDetail.topTools || [];
        repTools.innerHTML = tools.length ? tools.map(t => `
          <span style="background:#f1f5f9;border:1px solid #e2e8f0;padding:3px 8px;border-radius:4px;font-size:11.5px;font-weight:600;">
            ${esc(t.name)}: <span style="color:#2563eb;">${t.count}</span>
          </span>
        `).join('') : '<span style="color:#94a3b8;font-size:12px;">Standard tools</span>';

        const events = sessionDetail.timeline || [];
        if (!events.length) {
          repTimeline.innerHTML = '<div style="padding:20px;text-align:center;color:#94a3b8;">No events recorded in session map.</div>';
        } else {
          repTimeline.innerHTML = events.map(e => {
            const kindClass = e.isMcp ? 'mcp' : (e.kind || 'bash');
            return `
              <div class="timeline-row ${e.err ? 'err' : ''}">
                <div class="step-badge">#${e.step}</div>
                <div class="kind-tag ${kindClass}">${esc(e.tool || e.kind)}</div>
                <div class="action-desc" title="${esc(e.summary)}">${esc(e.summary)}</div>
                ${e.retry ? '<span class="retry-tag">RETRY</span>' : ''}
                ${e.err ? '<span class="err-tag">FAILED</span>' : ''}
                <div class="dur">${e.durMs > 0 ? (e.durMs/1000).toFixed(1) + 's' : '&mdash;'}</div>
              </div>
            `;
          }).join('');
        }
      } catch (err) {
        repTimeline.innerHTML = `<div style="padding:20px;text-align:center;color:#dc2626;">Failed to load session details: ${esc(err.message)}</div>`;
      }
    }

    async function loadLeaderboard() {
      const scope = document.getElementById('scopeFilter').value;
      const res = await fetch('/api/leaderboard?demo=' + (scope === 'all' ? '1' : '0'));
      cachedData = await res.json();
      updateTeamDropdown();
      render();
    }

    function updateTeamDropdown() {
      if (!cachedData) return;
      const sel = document.getElementById('teamFilter');
      const prev = sel.value;
      const teams = cachedData.teams.map(t => t.team).sort();
      sel.innerHTML = '<option value="all">All teams</option>' +
        teams.map(t => `<option value="${esc(t)}">${esc(t)}</option>`).join('');
      if (teams.includes(prev)) sel.value = prev;
    }

    function sparklineHtml(points) {
      const maxCalls = Math.max(1, ...(points || []).map(p => p.calls || 0));
      return '<div class="sparkline">' + (points || []).map(p => {
        const calls = p.calls || 0;
        const errs = p.errors || 0;
        if (calls === 0) return '<div class="spark-bar" style="height:2px;background:#e2e8f0;"></div>';
        const h = Math.max(3, Math.round((calls / maxCalls) * 16));
        const color = errs > 0 ? '#ef4444' : '#3b82f6';
        return `<div class="spark-bar" style="height:${h}px;background:${color};" title="${calls} calls, ${errs} errors"></div>`;
      }).join('') + '</div>';
    }

    function healthHtml(score) {
      if (score === null || score === undefined) return '&mdash;';
      const w = Math.max(0, Math.min(100, score));
      return `<div class="health-bar-container"><div class="health-track"><div class="health-line" style="width:${w}%;"></div></div> ${score}</div>`;
    }

    function render() {
      if (!cachedData) return;
      const s = cachedData.summary;
      document.getElementById('summarySubtitle').innerHTML =
        `<strong>${s.workingCount} participants</strong> active across <strong>${s.teamCount} teams</strong> &middot; ` +
        `<strong>${s.toolCalls} tool calls</strong> (${s.mcpCalls || 0} MCP) &middot; ` +
        `<strong>${s.commits} git commits</strong> &middot; <strong>$${s.spendUsd.toFixed(2)}</strong> model spend.`;

      const q = document.getElementById('searchBox').value.trim().toLowerCase();
      const teamFilter = document.getElementById('teamFilter').value;
      const thead = document.getElementById('tableHead');
      const tbody = document.getElementById('tableBody');

      if (currentTab === 'people') {
        thead.innerHTML = `
          <tr>
            <th>Participant</th>
            <th>Activity</th>
            <th class="num">Tool Calls</th>
            <th class="num">MCP Calls</th>
            <th class="num">Commits</th>
            <th class="num">Errors</th>
            <th class="num">Spend</th>
            <th class="num">Run Health</th>
            <th class="num">Last Seen</th>
          </tr>`;
        const rows = cachedData.participants.filter(p => {
          const matchQ = !q || p.participant.toLowerCase().includes(q) || p.team.toLowerCase().includes(q) || (p.agentTool || '').toLowerCase().includes(q);
          const matchT = teamFilter === 'all' || p.team === teamFilter;
          return matchQ && matchT;
        });
        tbody.innerHTML = rows.map(p => `
          <tr class="clickable" onclick="openParticipantReplay('${esc(p.participant)}')">
            <td>
              <div class="participant-cell">
                <span class="status-dot ${p.connected ? 'live' : ''}"></span>
                <div>
                  <div class="p-name">
                    ${esc(p.participant)}
                    ${p.mentorAlert ? '<span class="badge-alert">&#9888; SOS</span>' : ''}
                    ${!p.isDemo ? '<span class="badge-real">live</span>' : ''}
                  </div>
                  <div class="p-team">${esc(p.team)} &middot; <code style="color:#64748b;">${esc(p.agentTool || 'agent')}</code></div>
                </div>
              </div>
            </td>
            <td>${sparklineHtml(p.sparkline)}</td>
            <td class="num font-bold"><strong>${p.toolCalls}</strong></td>
            <td class="num">${p.mcpCalls ? '<span class="badge-mcp">' + p.mcpCalls + '</span>' : '&mdash;'}</td>
            <td class="num">${p.commits ? '<span class="badge-commit">' + p.commits + '</span>' : '&mdash;'}</td>
            <td class="num" style="${p.errors > 0 ? 'color:#dc2626;' : ''}">${p.errors}</td>
            <td class="num">$${p.spendUsd.toFixed(2)}</td>
            <td class="num">${healthHtml(p.runHealth)}</td>
            <td class="num" style="color:#64748b;">${esc(p.lastActionLabel)}</td>
          </tr>
        `).join('');
      } else {
        thead.innerHTML = `
          <tr>
            <th>Team</th>
            <th class="num">Members</th>
            <th class="num">Tool Calls</th>
            <th class="num">MCP Calls</th>
            <th class="num">Commits</th>
            <th class="num">Errors</th>
            <th class="num">Spend</th>
            <th class="num">Run Health</th>
          </tr>`;
        const rows = cachedData.teams.filter(t => {
          const matchQ = !q || t.team.toLowerCase().includes(q);
          const matchT = teamFilter === 'all' || t.team === teamFilter;
          return matchQ && matchT;
        });
        tbody.innerHTML = rows.map(t => `
          <tr>
            <td>
              <div class="p-name">
                ${esc(t.team)}
                ${t.mentorAlert ? '<span class="badge-alert">&#9888; SOS</span>' : ''}
                ${t.hasRealUploads ? '<span class="badge-real">active</span>' : ''}
              </div>
              <div class="p-team">${esc(t.repos.join(', ') || 'workspace')}</div>
            </td>
            <td class="num">${t.members}</td>
            <td class="num"><strong>${t.toolCalls}</strong></td>
            <td class="num">${t.mcpCalls ? '<span class="badge-mcp">' + t.mcpCalls + '</span>' : '&mdash;'}</td>
            <td class="num">${t.commits ? '<span class="badge-commit">' + t.commits + '</span>' : '&mdash;'}</td>
            <td class="num" style="${t.errors > 0 ? 'color:#dc2626;' : ''}">${t.errors}</td>
            <td class="num">$${t.spendUsd.toFixed(2)}</td>
            <td class="num">${healthHtml(t.runHealth)}</td>
          </tr>
        `).join('');
      }

      const actBox = document.getElementById('liveActivityBody');
      const acts = cachedData.liveActivity || [];
      document.getElementById('actCount').textContent = acts.length ? `(${acts.length})` : '';
      if (!acts.length) {
        actBox.innerHTML = '<p style="color:#94a3b8;font-size:12px;">Activity will show up here as participants run agent sessions.</p>';
      } else {
        actBox.innerHTML = acts.map(a => `
          <div class="activity-item">
            <div><strong>${esc(a.participant)}</strong> (${esc(a.team)}) uploaded <code>${esc(a.agentTool)}</code></div>
            <div class="activity-meta">
              <span>&#9889; ${a.calls} calls</span>
              ${a.mcpCalls ? '<span style="color:#6b21a8;">&#129513; ' + a.mcpCalls + ' MCP</span>' : ''}
              ${a.commits ? '<span style="color:#3730a3;">&#128230; ' + a.commits + ' commits</span>' : ''}
              ${a.errors > 0 ? '<span style="color:#dc2626;">&#10060; ' + a.errors + ' err</span>' : ''}
              <span style="margin-left:auto;">${esc(a.at)}</span>
            </div>
          </div>
        `).join('');
      }
    }

    async function submitUpload() {
      const status = document.getElementById('uploadStatus');
      const file = document.getElementById('upFile').files[0];
      const participant = document.getElementById('upName').value.trim();
      const team = document.getElementById('upTeam').value.trim();
      if (!participant || !team || !file) {
        status.style.color = '#dc2626';
        status.textContent = 'Please fill name, team and choose a session file.';
        return;
      }
      status.style.color = '#2563eb';
      status.textContent = 'Uploading session...';

      const buf = await file.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let binary = '';
      const chunk = 0x8000;
      for (let i = 0; i < bytes.length; i += chunk) binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
      const b64 = btoa(binary);

      try {
        const res = await fetch('/api/upload', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ participant, team, mapBase64: b64 })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Upload failed');
        status.style.color = '#16a34a';
        status.textContent = `Uploaded ${data.calls} calls successfully!`;
        await loadLeaderboard();
        setTimeout(closeUploadModal, 600);
      } catch (e) {
        status.style.color = '#dc2626';
        status.textContent = e.message;
      }
    }

    loadLeaderboard();
    setInterval(loadLeaderboard, 4000);
  </script>
</body>
</html>
"""

HTML_STAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Hackathon Stage Monitor &middot; Live Big Screen</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #090d16; color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; padding: 24px; min-height: 100vh; display: flex; flex-direction: column; }
    .stage-header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 20px; border-bottom: 1px solid rgba(255,255,255,0.1); }
    .title-box h1 { font-size: 28px; font-weight: 800; letter-spacing: -0.5px; background: linear-gradient(90deg, #38bdf8, #818cf8, #c084fc); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    .title-box .sub { font-size: 14px; color: #94a3b8; margin-top: 4px; }
    .live-badge { display: inline-flex; align-items: center; gap: 8px; background: rgba(16, 185, 129, 0.15); color: #34d399; padding: 6px 14px; border-radius: 999px; font-weight: 700; font-size: 13px; border: 1px solid rgba(16, 185, 129, 0.3); }
    .pulse-dot { width: 10px; height: 10px; border-radius: 50%; background: #10b981; animation: blip 1.5s infinite; }
    @keyframes blip { 0% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.4); opacity: 0.5; } 100% { transform: scale(1); opacity: 1; } }

    .kpi-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin: 24px 0; }
    .kpi-card { background: rgba(30, 41, 59, 0.6); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 18px; backdrop-filter: blur(8px); }
    .kpi-label { font-size: 12px; color: #94a3b8; text-transform: uppercase; font-weight: 600; letter-spacing: 0.5px; }
    .kpi-val { font-size: 32px; font-weight: 800; color: #fff; margin-top: 6px; }

    .podium-section { margin-bottom: 24px; }
    .podium-grid { display: grid; grid-template-columns: 1fr 1.15fr 1fr; gap: 20px; align-items: flex-end; max-width: 960px; margin: 0 auto; }
    .podium-card { background: rgba(30, 41, 59, 0.7); border-radius: 12px; padding: 24px; text-align: center; border: 1px solid rgba(255,255,255,0.1); position: relative; }
    .podium-card.first { border-color: #fbbf24; box-shadow: 0 0 35px rgba(251, 191, 36, 0.2); transform: translateY(-10px); }
    .podium-card.second { border-color: #94a3b8; }
    .podium-card.third { border-color: #d97706; }
    .podium-medal { font-size: 36px; margin-bottom: 8px; }
    .podium-team { font-size: 20px; font-weight: 800; margin-bottom: 4px; }
    .podium-score { font-size: 14px; color: #94a3b8; }

    .ticker-bar { margin-top: auto; background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255,255,255,0.1); border-radius: 8px; padding: 12px 20px; display: flex; align-items: center; gap: 14px; font-size: 13px; overflow: hidden; }
    .ticker-label { background: #3b82f6; color: #fff; padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 11px; text-transform: uppercase; flex-shrink: 0; }
    .ticker-text { white-space: nowrap; animation: marquee 25s linear infinite; color: #cbd5e1; }
    @keyframes marquee { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }
  </style>
</head>
<body>
  <div class="stage-header">
    <div class="title-box">
      <h1>HACKATHON AGENT ARENA</h1>
      <div class="sub">Live telemetry stream &middot; Multi-Agent Observability</div>
    </div>
    <div class="live-badge">
      <span class="pulse-dot"></span> LIVE TELEMETRY STREAM
    </div>
  </div>

  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">Active Teams</div>
      <div class="kpi-val" id="kpiTeams">--</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Total AI Calls</div>
      <div class="kpi-val" id="kpiCalls" style="color:#38bdf8;">--</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">MCP Tool Calls</div>
      <div class="kpi-val" id="kpiMcp" style="color:#c084fc;">--</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Git Commits</div>
      <div class="kpi-val" id="kpiCommits" style="color:#34d399;">--</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">LLM Budget Spent</div>
      <div class="kpi-val" id="kpiSpend" style="color:#f59e0b;">$--</div>
    </div>
  </div>

  <div class="podium-section">
    <h3 style="text-align:center;font-size:14px;color:#94a3b8;margin-bottom:16px;text-transform:uppercase;letter-spacing:1px;">Leaderboard Podium</h3>
    <div class="podium-grid" id="podiumGrid">
      <div class="podium-card second">
        <div class="podium-medal">&#129358;</div>
        <div class="podium-team" id="pod2Name">--</div>
        <div class="podium-score" id="pod2Score">-- calls</div>
      </div>
      <div class="podium-card first">
        <div class="podium-medal">&#129351;</div>
        <div class="podium-team" id="pod1Name" style="color:#fbbf24;">--</div>
        <div class="podium-score" id="pod1Score">-- calls</div>
      </div>
      <div class="podium-card third">
        <div class="podium-medal">&#129359;</div>
        <div class="podium-team" id="pod3Name">--</div>
        <div class="podium-score" id="pod3Score">-- calls</div>
      </div>
    </div>
  </div>

  <div class="ticker-bar">
    <span class="ticker-label">Live Feed</span>
    <div class="ticker-text" id="tickerText">Connecting to Hackathon Live Stream...</div>
  </div>

  <script>
    async function updateStage() {
      try {
        const res = await fetch('/api/leaderboard?demo=1');
        const data = await res.json();
        const s = data.summary;

        document.getElementById('kpiTeams').textContent = s.teamCount;
        document.getElementById('kpiCalls').textContent = s.toolCalls.toLocaleString();
        document.getElementById('kpiMcp').textContent = (s.mcpCalls || 0).toLocaleString();
        document.getElementById('kpiCommits').textContent = (s.commits || 0).toLocaleString();
        document.getElementById('kpiSpend').textContent = '$' + s.spendUsd.toFixed(2);

        const teams = data.teams || [];
        if (teams.length >= 1) {
          document.getElementById('pod1Name').textContent = teams[0].team;
          document.getElementById('pod1Score').textContent = `${teams[0].toolCalls} calls &middot; Health: ${teams[0].runHealth || '--'}`;
        }
        if (teams.length >= 2) {
          document.getElementById('pod2Name').textContent = teams[1].team;
          document.getElementById('pod2Score').textContent = `${teams[1].toolCalls} calls &middot; Health: ${teams[1].runHealth || '--'}`;
        }
        if (teams.length >= 3) {
          document.getElementById('pod3Name').textContent = teams[2].team;
          document.getElementById('pod3Score').textContent = `${teams[2].toolCalls} calls &middot; Health: ${teams[2].runHealth || '--'}`;
        }

        const acts = data.liveActivity || [];
        if (acts.length) {
          document.getElementById('tickerText').textContent = acts.map(a =>
            `[${a.at}] ${a.participant} (${a.team}) executed ${a.calls} calls with ${a.agentTool}`
          ).join('  \u2014\u2014  ');
        }
      } catch (e) {
        console.error(e);
      }
    }
    updateStage();
    setInterval(updateStage, 3000);
  </script>
</body>
</html>
"""

HTML_JOIN = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Connect to Hackathon Leaderboard &middot; 1-Line Setup</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 32px 20px; line-height: 1.5; }
    .container { max-width: 680px; margin: 0 auto; }
    h1 { font-size: 24px; font-weight: 700; margin-bottom: 6px; }
    p.sub { color: #94a3b8; font-size: 14px; margin-bottom: 24px; }
    .card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 24px; margin-bottom: 20px; }
    .row { display: flex; gap: 14px; margin-bottom: 16px; }
    .col { flex: 1; }
    label { display: block; font-size: 12px; font-weight: 600; color: #cbd5e1; margin-bottom: 6px; text-transform: uppercase; }
    input { width: 100%; padding: 10px 12px; border-radius: 6px; border: 1px solid #475569; background: #0f172a; color: #fff; font-size: 14px; }
    .cmd-box { background: #090d16; border: 1px solid #334155; border-radius: 8px; padding: 14px 16px; margin-top: 14px; position: relative; }
    pre { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; color: #38bdf8; white-space: pre-wrap; word-break: break-all; margin: 0; }
    .copy-btn { position: absolute; top: 10px; right: 10px; background: #3b82f6; color: #fff; border: none; padding: 5px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; cursor: pointer; }
    .copy-btn:hover { background: #2563eb; }
    .step-num { display: inline-flex; width: 22px; height: 22px; background: #3b82f6; color: #fff; border-radius: 50%; font-size: 12px; font-weight: 700; align-items: center; justify-content: center; margin-right: 6px; }
    .note { font-size: 12.5px; color: #94a3b8; margin-top: 8px; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Connect Your Agent to the Leaderboard</h1>
    <p class="sub">Run one copy-paste command in your terminal. As you code with Antigravity, Cursor, Claude Code, or Copilot, your session metadata syncs live automatically.</p>

    <div class="card">
      <div class="row">
        <div class="col">
          <label>Your Name</label>
          <input type="text" id="joinName" value="Akhil" oninput="updateCmd()">
        </div>
        <div class="col">
          <label>Your Team</label>
          <input type="text" id="joinTeam" value="Observability" oninput="updateCmd()">
        </div>
      </div>

      <h3 style="font-size:14px;margin-top:16px;"><span class="step-num">1</span> Windows PowerShell (1-Click Run)</h3>
      <div class="cmd-box">
        <button class="copy-btn" onclick="copyText('psCmd')">Copy</button>
        <pre id="psCmd">irm http://HUB_HOST/join.ps1 | iex -args "-Name 'Akhil' -Team 'Observability'"</pre>
      </div>

      <h3 style="font-size:14px;margin-top:20px;"><span class="step-num">2</span> macOS / Linux (1-Click Run)</h3>
      <div class="cmd-box">
        <button class="copy-btn" onclick="copyText('shCmd')">Copy</button>
        <pre id="shCmd">curl -sSL http://HUB_HOST/join.sh | bash -s -- --name "Akhil" --team "Observability"</pre>
      </div>

      <p class="note">&#128274; <strong>Privacy Guarantee:</strong> All prompts, files, code diffs, and API keys are stripped by agentplay locally before sending. Only tool counts, error classes, and timings travel over the wire.</p>
    </div>
  </div>

  <script>
    function updateCmd() {
      const host = window.location.host;
      const name = document.getElementById('joinName').value.trim() || 'Participant';
      const team = document.getElementById('joinTeam').value.trim() || 'HackerTeam';

      document.getElementById('psCmd').textContent =
        `irm "http://${host}/join.ps1?name=${encodeURIComponent(name)}&team=${encodeURIComponent(team)}" | iex`;

      document.getElementById('shCmd').textContent =
        `curl -sSL "http://${host}/join.sh?name=${encodeURIComponent(name)}&team=${encodeURIComponent(team)}" | bash`;
    }
    function copyText(id) {
      const text = document.getElementById(id).textContent;
      navigator.clipboard.writeText(text);
      event.target.textContent = 'Copied!';
      setTimeout(() => event.target.textContent = 'Copy', 1500);
    }
    updateCmd();
  </script>
</body>
</html>
"""


def _generate_join_ps1(host_port: str, default_name: str = "Participant", default_team: str = "HackerTeam") -> str:
    return f"""# Hackathon Leaderboard 1-Click Join Script (Windows PowerShell)
param(
    [string]$Name = "{default_name}",
    [string]$Team = "{default_team}",
    [string]$Hub = "http://{host_port}"
)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Connecting to Hackathon Control Leaderboard at $Hub" -ForegroundColor Cyan
Write-Host " Participant: $Name | Team: $Team" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$antigravityDir = "$HOME\\.gemini\\antigravity"
if (Test-Path $antigravityDir) {{
    $env:AGENTPLAY_ANTIGRAVITY_HOMES = $antigravityDir
    Write-Host "[+] Detected Antigravity IDE sessions at $antigravityDir" -ForegroundColor Green
}}

$agentplayExe = (Get-Command agentplay -ErrorAction SilentlyContinue).Source
if (-not $agentplayExe) {{
    $candidates = @(
        "$HOME\\AppData\\Roaming\\Python\\Python314\\Scripts\\agentplay.exe",
        "$HOME\\AppData\\Roaming\\Python\\Python313\\Scripts\\agentplay.exe",
        "$HOME\\AppData\\Roaming\\Python\\Python312\\Scripts\\agentplay.exe",
        "$HOME\\AppData\\Roaming\\Python\\Python311\\Scripts\\agentplay.exe"
    )
    foreach ($cand in $candidates) {{
        if (Test-Path $cand) {{ $agentplayExe = $cand; break }}
    }}
}}

if (-not $agentplayExe) {{
    Write-Host "[*] Installing agentplay..." -ForegroundColor Yellow
    pip install agentplay --quiet
    $agentplayExe = (Get-Command agentplay -ErrorAction SilentlyContinue).Source
}}

Write-Host "[*] Building local agent session index..." -ForegroundColor Yellow
& $agentplayExe build

$indexFile = "$HOME\\.agentplay\\index.json"
if (Test-Path $indexFile) {{
    $mapsDir = "$HOME\\.agentplay\\maps"
    $latestMap = Get-ChildItem -Path $mapsDir -Filter "*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latestMap) {{
        Write-Host "[*] Uploading latest session: $($latestMap.Name)" -ForegroundColor Yellow
        $url = "$Hub/api/upload?participant=$([uri]::EscapeDataString($Name))&team=$([uri]::EscapeDataString($Team))"
        try {{
            $resp = Invoke-RestMethod -Method Post -Uri $url -InFile $latestMap.FullName
            Write-Host "SUCCESS! Connected as $Name ($Team)! ($($resp.calls) calls recorded)" -ForegroundColor Green
        }} catch {{
            Write-Host "[-] Upload warning: $_" -ForegroundColor Red
        }}
    }}
}}

Write-Host "`n[+] Hackathon Leaderboard sync active! Running live watcher..." -ForegroundColor Cyan
while ($true) {{
    Start-Sleep -Seconds 20
    & $agentplayExe build 2>$null
    $latestMap = Get-ChildItem -Path "$HOME\\.agentplay\\maps" -Filter "*.json" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latestMap) {{
        $url = "$Hub/api/upload?participant=$([uri]::EscapeDataString($Name))&team=$([uri]::EscapeDataString($Team))"
        try {{
            $null = Invoke-RestMethod -Method Post -Uri $url -InFile $latestMap.FullName
        }} catch {{}}
    }}
}}
"""


def _generate_join_sh(host_port: str, default_name: str = "Participant", default_team: str = "HackerTeam") -> str:
    return f"""#!/usr/bin/env bash
# Hackathon Leaderboard 1-Click Join Script (macOS / Linux)
set -e

NAME="{default_name}"
TEAM="{default_team}"
HUB="http://{host_port}"

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --name) NAME="$2"; shift ;;
        --team) TEAM="$2"; shift ;;
        --hub)  HUB="$2"; shift ;;
    esac
    shift
done

echo "=========================================================="
echo " Connecting to Hackathon Control Leaderboard at $HUB"
echo " Participant: $NAME | Team: $TEAM"
echo "=========================================================="

if ! command -v agentplay &> /dev/null; then
    echo "[*] Installing agentplay..."
    pip install agentplay --quiet || pipx install agentplay --quiet
fi

echo "[*] Building local agent session index..."
agentplay build

MAPS_DIR="$HOME/.agentplay/maps"
if [ -d "$MAPS_DIR" ]; then
    LATEST=$(ls -t "$MAPS_DIR"/*.json 2>/dev/null | head -n 1)
    if [ -n "$LATEST" ]; then
        echo "[*] Uploading latest session: $LATEST"
        curl -s -X POST "$HUB/api/upload?participant=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$NAME")&team=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$TEAM")" --data-binary @"$LATEST"
        echo ""
        echo "[+] Connected successfully to leaderboard!"
    fi
fi

echo "[+] Starting live sync daemon (press Ctrl+C to stop)..."
while true; do
    sleep 20
    agentplay build >/dev/null 2>&1 || true
    LATEST=$(ls -t "$MAPS_DIR"/*.json 2>/dev/null | head -n 1)
    if [ -n "$LATEST" ]; then
        curl -s -X POST "$HUB/api/upload?participant=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$NAME")&team=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$TEAM")" --data-binary @"$LATEST" >/dev/null 2>&1 || true
    fi
done
"""


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, content: str, content_type: str = "text/plain; charset=utf-8") -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        host_hdr = self.headers.get("Host") or "127.0.0.1:7400"

        if parsed.path == "/":
            self._send_text(HTTPStatus.OK, HTML_DASHBOARD, "text/html; charset=utf-8")
            return
        if parsed.path == "/stage":
            self._send_text(HTTPStatus.OK, HTML_STAGE, "text/html; charset=utf-8")
            return
        if parsed.path == "/join":
            self._send_text(HTTPStatus.OK, HTML_JOIN, "text/html; charset=utf-8")
            return
        if parsed.path == "/join.ps1":
            qs = parse_qs(parsed.query)
            p_name = (qs.get("name") or qs.get("Name") or ["Participant"])[0]
            p_team = (qs.get("team") or qs.get("Team") or ["HackerTeam"])[0]
            self._send_text(HTTPStatus.OK, _generate_join_ps1(host_hdr, default_name=p_name, default_team=p_team), "text/plain; charset=utf-8")
            return
        if parsed.path == "/join.sh":
            qs = parse_qs(parsed.query)
            p_name = (qs.get("name") or qs.get("Name") or ["Participant"])[0]
            p_team = (qs.get("team") or qs.get("Team") or ["HackerTeam"])[0]
            self._send_text(HTTPStatus.OK, _generate_join_sh(host_hdr, default_name=p_name, default_team=p_team), "text/plain; charset=utf-8")
            return
        if parsed.path == "/api/leaderboard":
            qs = parse_qs(parsed.query)
            include_demo = qs.get("demo", ["1"])[0] != "0"
            self._send_json(HTTPStatus.OK, build_leaderboard_payload(include_demo=include_demo))
            return
        if parsed.path == "/api/session":
            qs = parse_qs(parsed.query)
            sid = (qs.get("id") or [""])[0].strip()
            if not sid:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing session id"})
                return
            doc = _get_raw_map(sid)
            if not doc:
                with _LOCK:
                    state = _load_state()
                matched = [s for s in state.get("uploadedSessions", []) if s.get("sessionId") == sid]
                if matched:
                    m = matched[0]
                    self._send_json(HTTPStatus.OK, {
                        "sessionId": sid,
                        "agentTool": m.get("agentTool", "unknown"),
                        "startedAt": m.get("startedAt"),
                        "durationMs": m.get("durationMs", 0),
                        "calls": m.get("calls", 0),
                        "errors": m.get("errors", 0),
                        "commits": m.get("commits", 0),
                        "mcpCalls": m.get("mcpCalls", 0),
                        "costUsd": m.get("costUsd", 0.0),
                        "tokens": m.get("tokens", 0),
                        "filesTouched": m.get("filesTouched", 0),
                        "mentorAlert": m.get("mentorAlert", False),
                        "mentorReason": m.get("mentorReason", ""),
                        "topTools": m.get("topTools") or [{"name": m.get("agentTool", "Tool"), "count": m.get("calls", 0)}],
                        "timeline": [
                            {"step": i+1, "task": 1, "kind": "tool", "cat": "tool", "tool": m.get("agentTool", "Tool"), "summary": f"{m.get('agentTool', 'Tool')} action #{i+1}", "target": m.get("repo", ""), "durMs": 800, "err": False, "retry": False, "isMcp": False}
                            for i in range(min(20, m.get("calls", 0)))
                        ],
                    })
                    return
                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Session map not found on disk for {sid}"})
                return
            analysis = _analyze_events(doc.get("events") or [], doc.get("files") or [])
            sess = doc.get("session") or {}
            totals = doc.get("totals") or {}
            self._send_json(HTTPStatus.OK, {
                "sessionId": sid,
                "agentTool": sess.get("agentTool", "unknown"),
                "startedAt": sess.get("startedAt"),
                "durationMs": sess.get("durationMs", 0),
                "calls": totals.get("calls", len(doc.get("events") or [])),
                "errors": totals.get("errors", 0),
                "commits": analysis["commits"],
                "mcpCalls": analysis["mcpCalls"],
                "costUsd": totals.get("costUsd", 0.0),
                "tokens": totals.get("tokens", 0),
                "filesTouched": totals.get("filesTouched", len(doc.get("files") or [])),
                "mentorAlert": analysis["mentorAlert"],
                "mentorReason": analysis["mentorReason"],
                "topTools": analysis["topTools"],
                "timeline": analysis["timeline"],
            })
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path != "/api/upload":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Invalid Content-Length"})
            return
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Upload body empty or exceeds 25 MB limit"})
            return

        raw = self.rfile.read(length)
        qs = parse_qs(parsed.query)
        participant = (qs.get("participant") or [""])[0].strip()
        team = (qs.get("team") or [""])[0].strip()
        repo_override = (qs.get("repo") or [""])[0].strip() or None

        try:
            if raw[:2] == b"\x1f\x8b":
                doc = _decode_map_bytes(raw)
            else:
                obj = json.loads(raw.decode("utf-8"))
                if not isinstance(obj, dict):
                    raise ValueError("JSON body must be an object.")
                if "mapBase64" in obj or "map" in obj:
                    participant = str(obj.get("participant") or participant).strip()
                    team = str(obj.get("team") or team).strip()
                    repo_override = str(obj.get("repo") or repo_override or "").strip() or None
                    if obj.get("mapBase64"):
                        doc = _decode_map_bytes(base64.b64decode(obj["mapBase64"]))
                    else:
                        doc = obj["map"]
                else:
                    doc = obj

            if not participant:
                participant = "Your Name"
            if not team:
                team = "Test"
            rec = ingest_upload(doc, participant=participant, team=team, repo_override=repo_override)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        self._send_json(
            HTTPStatus.OK,
            {
                "ok": True,
                "participant": rec["participant"],
                "team": rec["team"],
                "repo": rec["repo"],
                "sessionId": rec["sessionId"],
                "calls": rec["calls"],
                "mcpCalls": rec["mcpCalls"],
                "commits": rec["commits"],
                "errors": rec["errors"],
                "costUsd": rec["costUsd"],
                "mentorAlert": rec["mentorAlert"],
            },
        )

    def log_message(self, format: str, *args: Any) -> None:
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Hackathon Control Leaderboard Server")
    default_host = os.environ.get("HOST") or os.environ.get("AGENTPLAY_HUB_HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    default_port = int(os.environ.get("PORT") or os.environ.get("AGENTPLAY_HUB_PORT") or 7400)
    ap.add_argument("--host", default=default_host)
    ap.add_argument("--port", type=int, default=default_port)
    args = ap.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Hackathon Control server running on http://{args.host}:{args.port}")
    print(f"  -> Dashboard:        http://{args.host}:{args.port}/")
    print(f"  -> Stage View:       http://{args.host}:{args.port}/stage")
    print(f"  -> 1-Line Onboarding: http://{args.host}:{args.port}/join")
    server.serve_forever()


if __name__ == "__main__":
    main()
