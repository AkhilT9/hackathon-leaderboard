# Hackathon Control

A live leaderboard for AI coding-agent activity at a hackathon. Each participant runs one
command; their agent sessions (Claude Code, Cursor, Codex, Copilot, Antigravity, Gemini CLI,
OpenCode…) are turned into redacted counts by [`agentplay`](https://pypi.org/project/agentplay/)
on their laptop and synced every 20 s. The hub ranks builders and teams by tool calls and
hands out badges for everything else.

**Only counts, tool names, timings, token totals and file *names* leave a laptop.** Never code,
prompts, file contents, command arguments or secrets. The hub additionally drops full file
paths and repo remotes before storing anything.

## Pages

| Route | What it is |
|---|---|
| `/` | Leaderboard: live stats, power hour, live feed, podium, builders/teams tables (sort by any metric), crown holders |
| `/player?name=` | A builder: rank, stats, trophy case, progress to every next badge tier, activity by hour, favourite tools, session replay |
| `/team?name=` | A team: **each member's share** of calls, tokens, commits, lines, MCP, tests, errors and spend; members table; team badges |
| `/awards` | Every badge with its bronze/silver/gold rule, crown holder, runners-up and how many have earned it |
| `/stage` | Projector view. Six rotating scenes (room totals, podium, team battle, power hour, crowns, live feed), full-screen spotlights with confetti for crowns, gold badges, podium entries and milestones. `←/→` scenes, `space` pause, `F` fullscreen, `?scene=N` pins one scene |
| `/join` | Register (name, team, optional event code) → personal upload token → one-line sync command for Windows or macOS/Linux, or a file upload |

## How the competition works

- **Ranking:** raw activity — tool calls (ties broken by tokens). Rank arrows compare with 15 minutes ago.
- **17 builder badges and 4 team badges**, each with bronze/silver/gold tiers. The best holder of each wears its **crown**,
  which can change hands live: Token Titan, Tool Maestro, Ship It, Test Pilot, Clean Run, Comeback Kid, MCP Explorer,
  Delegator, Cache Wizard, Frugal Builder, Context Whale, Night Owl, Speedrunner, Marathoner, Researcher, Code Sculptor,
  Polyglot; teams: All Hands, Balanced Squad, Token Treasury, Hive Mind. Rules live in `hub/badges.py`.
- **Power hour:** every clock hour has a new challenge (tool calls, test runs, tokens, lines changed, commits,
  research). Only work done *during* that hour counts.
- **Live events:** badge unlocks, crown changes, climbs into the top 10, and room milestones (1M tokens, 10K calls,
  100 commits…) feed the live feed, toasts and the stage spotlights.

## Run locally

```bash
python server_7400.py                       # http://127.0.0.1:7400, data in ./data/hub.db
python scripts/simulate.py --people 24 --teams 6 --rounds 3 --interval 0     # seed demo data
python -m unittest discover -s tests -t .   # offline tests
```

Python 3.11+, standard library only. Load test (100 builders, uploads every 20 s):
`python scripts/simulate.py --people 100 --teams 20 --rounds 6 --interval 20`
(last run: 700 uploads, 0 failures, p95 35 ms).

## Configuration (environment)

| Variable | Purpose |
|---|---|
| `HUB_PUBLIC_URL` | Public `https://` URL written into the sync scripts. **Set it on any deployment.** |
| `HUB_EVENT_NAME` | Shown on every page |
| `HUB_EVENT_START` / `HUB_EVENT_END` | ISO times. Sessions started before the start are ignored; the end drives the countdowns |
| `HUB_UTC_OFFSET_MINUTES` | Venue time zone for Night Owl and the power-hour clock (default 330 = IST) |
| `HUB_REGISTRATION_CODE` | If set, `/join` asks for it (keeps strangers off the board) |
| `HUB_ADMIN_TOKEN` | Enables `POST /api/admin/reissue` and `/api/admin/remove` (`{"name": ...}`, header `X-Admin-Token`) for lost tokens and cleanup |
| `HUB_DATA_DIR` | Where `hub.db` (SQLite) lives |

## Deploy to Google Cloud

See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md): one Compute Engine VM, Docker Compose, Caddy for HTTPS,
daily disk snapshots — `PROJECT=<id> ./deploy/gcp/deploy.sh`.

## Layout

```
server_7400.py        HTTP server: pages, JSON API, uploads, sync scripts
hub/metrics.py        session map -> activity metrics (and the public replay timeline)
hub/badges.py         badge rules and tiers
hub/board.py          ranking, teams, crowns, power hour, live events
hub/store.py          SQLite storage
hub/join_scripts.py   /join.ps1 and /join.sh (every value is a quoted literal)
static/               pages (white theme: theme.css, app.js shared; stage.css for the projector)
scripts/simulate.py   synthetic participants for demos and load tests
sync_to_hub.py        Python alternative to the one-line sync command
deploy/gcp/           Compute Engine deployment
```

`leaderboard_data.json` and `uploaded_sessions/` are from the previous version and are not read any more; they hold
real participants' session data, so delete them before publishing this repository anywhere.
