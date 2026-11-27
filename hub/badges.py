"""Badge rules. Each badge reads one value from a metrics total and maps it to a tier.

Tier 0 = locked, 1 = bronze, 2 = silver, 3 = gold. The single best holder of each badge
(among those who reached at least bronze) also holds its crown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

TIER_NAMES = ("Locked", "Bronze", "Silver", "Gold")


@dataclass(frozen=True)
class Badge:
    id: str
    name: str
    rule: str
    icon: str
    color: str
    unit: str
    tiers: tuple[float, float, float]
    value: Callable[[dict[str, Any]], float | None]
    lower_better: bool = False
    fmt: str = "int"  # int | pct | ratio | hours | usd

    def tier(self, m: dict[str, Any]) -> int:
        v = self.value(m)
        if v is None:
            return 0
        reached = 0
        for i, threshold in enumerate(self.tiers, start=1):
            if (v <= threshold) if self.lower_better else (v >= threshold):
                reached = i
        return reached

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "rule": self.rule, "icon": self.icon, "color": self.color,
            "unit": self.unit, "tiers": list(self.tiers), "lowerBetter": self.lower_better, "fmt": self.fmt,
        }


def _ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def _error_rate(m: dict[str, Any]) -> float | None:
    return _ratio(m["errors"], m["calls"]) if m["calls"] >= 100 else None


def _cache_ratio(m: dict[str, Any]) -> float | None:
    llm = m["tokensIn"] + m["cacheRead"] + m["cacheWrite"]
    return _ratio(m["cacheRead"], llm) if m["tokens"] >= 1_000_000 and llm else None


def _commits_per_usd(m: dict[str, Any]) -> float | None:
    shipped = m["commits"] + m["prs"]
    return _ratio(shipped, m["costUsd"]) if shipped and m["costUsd"] >= 0.5 else None


BLUE, RED, YELLOW, GREEN = "#1a73e8", "#ea4335", "#f9ab00", "#1e8e3e"

PERSONAL: tuple[Badge, ...] = (
    Badge("token_titan", "Token Titan", "Most tokens processed", "coin", YELLOW, "tokens",
          (5e6, 5e7, 2e8), lambda m: m["tokens"]),
    Badge("tool_maestro", "Tool Maestro", "Most tool calls", "wrench", BLUE, "calls",
          (100, 500, 1500), lambda m: m["calls"]),
    Badge("ship_it", "Ship It", "Commits plus pull requests", "rocket", RED, "commits + PRs",
          (1, 5, 15), lambda m: m["commits"] + m["prs"]),
    Badge("test_pilot", "Test Pilot", "Test and build runs", "flask", GREEN, "verify runs",
          (5, 20, 60), lambda m: m["verifyRuns"]),
    Badge("clean_run", "Clean Run", "Lowest error rate (100+ calls)", "sparkles", BLUE, "error rate",
          (0.10, 0.05, 0.02), _error_rate, lower_better=True, fmt="pct"),
    Badge("comeback_kid", "Comeback Kid", "3+ errors in a row, then a passing test run", "refresh", RED,
          "comebacks", (1, 3, 6), lambda m: m["comebacks"]),
    Badge("mcp_explorer", "MCP Explorer", "Distinct MCP servers used", "plug", GREEN, "MCP servers",
          (1, 3, 6), lambda m: len(m["mcpServers"])),
    Badge("delegator", "Delegator", "Subagents launched", "bot", YELLOW, "subagents",
          (1, 5, 15), lambda m: m["subagents"]),
    Badge("cache_wizard", "Cache Wizard", "Share of input served from cache (1M+ tokens)", "database", BLUE,
          "cache hit", (0.5, 0.75, 0.9), _cache_ratio, fmt="pct"),
    Badge("frugal_builder", "Frugal Builder", "Commits + PRs per dollar", "leaf", GREEN, "per $",
          (0.5, 2, 5), _commits_per_usd, fmt="ratio"),
    Badge("context_whale", "Context Whale", "Largest context window used", "layers", BLUE, "tokens",
          (2e5, 5e5, 9e5), lambda m: m["maxContext"]),
    Badge("night_owl", "Night Owl", "Tool calls between midnight and 5 am", "moon", YELLOW, "calls",
          (20, 100, 300), lambda m: m["nightCalls"]),
    Badge("speedrunner", "Speedrunner", "Fewest steps before the first edit", "zap", RED, "steps",
          (10, 5, 2), lambda m: m["stepsToFirstEdit"], lower_better=True),
    Badge("marathoner", "Marathoner", "Active agent time", "clock", GREEN, "hours",
          (1, 3, 6), lambda m: m["activeMs"] / 3_600_000, fmt="hours"),
    Badge("researcher", "Researcher", "Web searches and fetches", "globe", BLUE, "lookups",
          (5, 20, 50), lambda m: m["webCalls"]),
    Badge("code_sculptor", "Code Sculptor", "Lines added and removed", "pen", RED, "lines",
          (200, 1000, 5000), lambda m: m["linesChanged"]),
    Badge("polyglot", "Polyglot", "Distinct models and agents used", "shuffle", YELLOW, "models + agents",
          (3, 4, 6), lambda m: len(m["models"]) + len(m["agentTools"])),
)


def _balance(t: dict[str, Any]) -> float | None:
    calls = [c for c in t.get("memberCalls") or []]
    if len(calls) < 2 or max(calls) == 0:
        return None
    return min(calls) / max(calls)


TEAM: tuple[Badge, ...] = (
    Badge("all_hands", "All Hands", "Every member active (2+ members)", "users", GREEN, "members active",
          (2, 3, 4), lambda t: t["activeMembers"] if t["activeMembers"] == t["memberCount"] else None),
    Badge("balanced_squad", "Balanced Squad", "Quietest member's calls vs. busiest", "scale", BLUE, "balance",
          (0.25, 0.4, 0.6), _balance, fmt="pct"),
    Badge("team_token_titan", "Token Treasury", "Team tokens processed", "crown", YELLOW, "tokens",
          (5e7, 5e8, 2e9), lambda t: t["tokens"]),
    Badge("hive_mind", "Hive Mind", "Distinct tools used across the team", "hive", RED, "tools",
          (10, 20, 35), lambda t: len(t["tools"])),
)

BY_ID = {b.id: b for b in (*PERSONAL, *TEAM)}


def evaluate(badges: tuple[Badge, ...], m: dict[str, Any]) -> dict[str, int]:
    return {b.id: t for b in badges if (t := b.tier(m)) > 0}


def crowns(badges: tuple[Badge, ...], subjects: list[tuple[str, dict[str, Any], dict[str, int]]]) -> dict[str, str]:
    """badge id -> key of its best holder (only among subjects with at least bronze)."""
    out: dict[str, str] = {}
    for b in badges:
        best_key, best_v = None, None
        for key, m, earned in subjects:
            if b.id not in earned:
                continue
            v = b.value(m)
            if v is None:
                continue
            if best_v is None or (v < best_v if b.lower_better else v > best_v):
                best_key, best_v = key, v
        if best_key is not None:
            out[b.id] = best_key
    return out
