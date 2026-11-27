"""Turn one agentplay-v1 session map into flat, additive activity metrics.

Everything here reads only counts, tool names and timings; no prompt or file content.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

NON_CALL_KINDS = {"user", "llm", "compaction", "delay", "interrupt", "turn_end"}
MAX_INT = 10**13  # clamp absurd values from hand-made maps

# Additive metrics are summed across sessions; the rest have their own merge rule.
ADDITIVE = (
    "sessions", "calls", "errors", "retries", "tokens", "tokensIn", "cacheRead", "cacheWrite",
    "outputTokens", "llmRequests", "costUsd", "commits", "prs", "mcpCalls", "verifyRuns",
    "verifyPass", "webCalls", "subagents", "linesChanged", "filesTouched", "nightCalls",
    "activeMs", "comebacks", "userTurns",
)


def _int(v: Any) -> int:
    try:
        return max(0, min(MAX_INT, int(v or 0)))
    except (TypeError, ValueError):
        return 0


def _float(v: Any) -> float:
    try:
        f = float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1e9, f)) if f == f else 0.0  # NaN -> 0


def parse_ts(ts: Any) -> datetime | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def validate_map(doc: Any) -> None:
    if not isinstance(doc, dict) or not isinstance(doc.get("session"), dict) or not isinstance(doc.get("events"), list):
        raise ValueError("Not a valid agentplay session map (missing 'session' or 'events').")


def _mcp_name(e: dict[str, Any]) -> str | None:
    tool = str(e.get("tool") or "")
    if e.get("kind") == "mcp" or e.get("server"):
        return str(e.get("server") or tool or "mcp")
    if tool.startswith("mcp__"):
        parts = tool.split("__")
        return parts[1] if len(parts) > 2 else tool
    return None


def extract(doc: dict[str, Any], utc_offset_min: int = 0) -> dict[str, Any]:
    validate_map(doc)
    sess = doc["session"]
    totals = doc.get("totals") if isinstance(doc.get("totals"), dict) else {}
    events = [e for e in doc["events"] if isinstance(e, dict)]
    started = parse_ts(sess.get("startedAt"))
    local_tz_shift = timedelta(minutes=utc_offset_min)

    tool_events = [e for e in events if str(e.get("kind") or "") not in NON_CALL_KINDS]
    llm_events = [e for e in events if e.get("kind") == "llm"]

    tokens_in = sum(_int(e.get("in")) for e in llm_events)
    cache_read = sum(_int(e.get("cr")) for e in llm_events)
    cache_write = sum(_int(e.get("cw")) for e in llm_events)
    out_tokens = sum(_int(e.get("out")) for e in llm_events) or _int(totals.get("outputTokens"))
    tokens = _int(totals.get("tokens")) or (tokens_in + cache_read + cache_write + out_tokens)

    tools: Counter[str] = Counter()
    mcp_servers: set[str] = set()
    mcp_calls = verify_runs = verify_pass = web_calls = commit_events = night_calls = lines = 0
    hourly = [0] * 24
    streak = 0
    pending_comeback = False
    comebacks = 0
    first_edit_step: int | None = None

    for step, e in enumerate(tool_events, start=1):
        kind = str(e.get("kind") or "")
        tool = str(e.get("tool") or kind or "tool")[:60]
        tools[tool] += 1
        err = bool(e.get("err"))
        mcp = _mcp_name(e)
        if mcp:
            mcp_calls += 1
            mcp_servers.add(mcp[:60])
        if kind == "verify":
            verify_runs += 1
            if not err:
                verify_pass += 1
        if kind == "web":
            web_calls += 1
        vcs = e.get("vcs") if isinstance(e.get("vcs"), dict) else {}
        if kind == "commit" or str(vcs.get("action") or "").lower() == "commit":
            commit_events += 1
        if kind == "edit":
            lines += _int(e.get("ins")) + _int(e.get("del"))
            if first_edit_step is None:
                first_edit_step = step

        if started is not None:
            local = started + timedelta(milliseconds=_int(e.get("t"))) + local_tz_shift
            hourly[local.hour] += 1
            if local.hour < 5:
                night_calls += 1

        # Comeback: 3+ failures in a row, later followed by a passing verify (tests/build).
        if err:
            streak += 1
            if streak >= 3:
                pending_comeback = True
        else:
            streak = 0
            if pending_comeback and kind == "verify":
                comebacks += 1
                pending_comeback = False

    files = doc.get("files") if isinstance(doc.get("files"), list) else []
    models = sess.get("models") if isinstance(sess.get("models"), list) else []
    duration = _int(sess.get("durationMs"))

    return {
        "sessions": 1,
        "calls": _int(totals.get("calls")) or len(tool_events),
        "errors": _int(totals.get("errors")) or sum(1 for e in tool_events if e.get("err")),
        "retries": _int(totals.get("retries")),
        "tokens": tokens,
        "tokensIn": tokens_in,
        "cacheRead": cache_read,
        "cacheWrite": cache_write,
        "outputTokens": out_tokens,
        "llmRequests": _int(totals.get("requests")) or len(llm_events),
        "costUsd": round(_float(totals.get("costUsd")), 4),
        "commits": max(_int(totals.get("commits")), commit_events),
        "prs": _int(totals.get("prsCreated")) + _int(totals.get("prsMerged")),
        "mcpCalls": mcp_calls,
        "verifyRuns": verify_runs,
        "verifyPass": verify_pass,
        "webCalls": web_calls,
        "subagents": _int(totals.get("subagents")),
        "linesChanged": lines,
        "filesTouched": _int(totals.get("filesTouched")) or len(files),
        "nightCalls": night_calls,
        "activeMs": max(0, duration - _int(totals.get("delayMs"))),
        "comebacks": comebacks,
        "userTurns": _int(totals.get("userTurns")),
        "maxContext": _int(totals.get("maxContext")),
        "stepsToFirstEdit": first_edit_step,
        "hourly": hourly,
        "tools": dict(tools.most_common(40)),
        "mcpServers": sorted(mcp_servers)[:40],
        "models": sorted({str(m)[:60] for m in models if m})[:10],
        "agentTools": [str(sess.get("agentTool") or "unknown")[:40]],
    }


def empty() -> dict[str, Any]:
    m: dict[str, Any] = {k: 0 for k in ADDITIVE}
    m.update({"costUsd": 0.0, "maxContext": 0, "stepsToFirstEdit": None, "hourly": [0] * 24,
              "tools": {}, "mcpServers": [], "models": [], "agentTools": []})
    return m


def merge(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine session (or participant) metrics into one total."""
    out = empty()
    tools: Counter[str] = Counter()
    mcp: set[str] = set()
    models: set[str] = set()
    agents: set[str] = set()
    for m in items:
        for k in ADDITIVE:
            out[k] += m.get(k) or 0
        out["maxContext"] = max(out["maxContext"], m.get("maxContext") or 0)
        s = m.get("stepsToFirstEdit")
        if s and (out["stepsToFirstEdit"] is None or s < out["stepsToFirstEdit"]):
            out["stepsToFirstEdit"] = s
        for i, v in enumerate((m.get("hourly") or [])[:24]):
            out["hourly"][i] += v
        tools.update(m.get("tools") or {})
        mcp.update(m.get("mcpServers") or [])
        models.update(m.get("models") or [])
        agents.update(m.get("agentTools") or [])
    out["costUsd"] = round(out["costUsd"], 4)
    out["tools"] = dict(tools.most_common(40))
    out["mcpServers"] = sorted(mcp)
    out["models"] = sorted(models)
    out["agentTools"] = sorted(agents)
    return out


def _basename(path: str) -> str:
    return (PureWindowsPath(path).name if "\\" in path else PurePosixPath(path).name)[:120]


def minimize(doc: dict[str, Any]) -> dict[str, Any]:
    """Drop what the hub never shows before storing: full file paths and repo remotes."""
    out = dict(doc)
    files = doc.get("files") if isinstance(doc.get("files"), list) else []
    out["files"] = [
        {**f, "path": _basename(str(f.get("path") or ""))} if isinstance(f, dict) else f for f in files
    ]
    repos = doc.get("repos") if isinstance(doc.get("repos"), list) else []
    out["repos"] = [{"name": str(r.get("name") or "")[:80]} for r in repos if isinstance(r, dict)]
    return out


def timeline(doc: dict[str, Any], limit: int = 400) -> list[dict[str, Any]]:
    """Public replay steps: tool, verb, file basename, duration, error flag."""
    files = {f.get("id"): str(f.get("path") or "") for f in doc.get("files") or [] if isinstance(f, dict)}
    steps: list[dict[str, Any]] = []
    for e in doc.get("events") or []:
        if not isinstance(e, dict) or str(e.get("kind") or "") in NON_CALL_KINDS:
            continue
        target = ""
        targets = e.get("targets")
        if isinstance(targets, list) and targets and isinstance(targets[0], dict):
            t0 = targets[0]
            target = _basename(files.get(t0.get("file"), "")) or str(t0.get("label") or "")[:80]
        steps.append({
            "t": _int(e.get("t")),
            "kind": str(e.get("kind") or "")[:20],
            "tool": str(e.get("tool") or e.get("kind") or "")[:60],
            "verb": str(e.get("verb") or "")[:80],
            "target": target,
            "durMs": _int(e.get("dur")),
            "err": bool(e.get("err")),
            "mcp": bool(_mcp_name(e)),
        })
        if len(steps) >= limit:
            break
    return steps
