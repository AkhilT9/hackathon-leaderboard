# Agent Observability & Hackathon Leaderboard (`agentplay`)

This workspace combines the open-source **`agentplay`** local session engine (on port `:7317`) with a **multi-user Hackathon Control leaderboard server** (`server_7400.py` on port `:7400`) and a **session sync helper** (`sync_to_hub.py`).

---

## 1. What Is Happening Here? (Workspace Overview)

| File / Folder | Role |
| :--- | :--- |
| [`agentplay/`](agentplay) | Cloned repository (`Entelligence-AI/agentplay` + `Monika-rolls/agentplay` remote). Parses coding-agent transcripts into redacted session maps and powers the single-user replay UI on `:7317`. |
| [`server_7400.py`](server_7400.py) | Multi-user **Hackathon Control** web server + API: Main Dashboard (`/`), Stage View (`/stage`), 1-Line Onboarding (`/join`, `/join.ps1`, `/join.sh`), Session Replay (`/api/session`), and Upload Ingestion (`POST /api/upload`). Computes Run Health, detects Mentor SOS alerts, counts Git commits and MCP calls. |
| [`sync_to_hub.py`](sync_to_hub.py) | Participant CLI helper that runs `agentplay build` locally and uploads recent or live (`--watch`) session maps to the `:7400` leaderboard. |
| [`leaderboard_data.json`](leaderboard_data.json) | Persistent JSON store of uploaded session summaries and the **Live activity** feed for `server_7400.py`. |
| [`uploaded_sessions/`](uploaded_sessions) | Raw redacted `.json` map files saved by `server_7400.py` when participants upload sessions (used for live interactive replay). |
| [`current_session.json.gz`](current_session.json.gz), [`my_exported_session.json.gz`](my_exported_session.json.gz) | Sample redacted `agentplay-v1` maps exported via `agentplay export`. |

---

## 2. Architecture & Layering

The system follows a **5-layer pipeline** where raw agent transcripts stay private on each developer's laptop and only redacted telemetry maps travel to the leaderboard:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: AI Coding Harnesses (Local Disk Logs)                               │
│  Claude Code (~/.claude) · Cursor (~/.cursor) · Antigravity (~/.gemini/...)  │
│  Codex (~/.codex) · Copilot (~/.copilot / VS Code) · Goose · OpenCode · Kiro │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ LAYER 2: Ingestion, Wrappers & Redaction (`agentplay` Python Core)           │
│  1. Discover (discover.py)     → finds transcripts or SQLite DBs per harness │
│  2. Materialize (materialize.py) → decodes SQLite/DB stores to NDJSON cache  │
│  3. Parsers (_sources/local/parsers/*.py) + Tool Taxonomy (tool_taxonomy.py) │
│     → wraps proprietary logs into universal `SpanData` & canonical tools     │
│  4. Builder (builder.py)       → strips prompts/code/secrets → `agentplay-v1`│
└──────────────────┬─────────────────────────────┬─────────────────────────────┘
                   │                             │
                   ▼                             ▼
┌──────────────────────────────────┐   ┌───────────────────────────────────────┐
│ LAYER 3: Local Single-User Store │   │ LAYER 4: Export & Upload Wrappers     │
│  • ~/.agentplay/maps/*.json      │   │  • `agentplay export <id> -o s.json.gz`│
│  • ~/.agentplay/index.json       │   │  • Browser Upload modal / drag & drop │
│  • Local Viewer (:7317)          │   │  • `sync_to_hub.py` (--watch / batch) │
│    Radial Map + Timeline + Fixes │   └─────────────────┬─────────────────────┘
└──────────────────────────────────┘                     │ HTTP POST /api/upload
                                                         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ LAYER 5: Multi-User Hackathon Control Leaderboard (`server_7400.py`)         │
│  • Validates `agentplay-v1` maps (.json or .json.gz)                         │
│  • Computes Run Health (`facts.py` + `health.py`) & 24-bucket sparklines     │
│  • Aggregates per Participant & per Team (`People` / `Teams` tabs)           │
│  • Persists to `leaderboard_data.json` & streams Live Activity (`:7400`)     │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Harnesses & Wrappers Explained

In `agentplay`, **harnesses** are the AI coding tools generating raw logs, and **wrappers/normalizers** translate those heterogeneous formats into one uniform schema.

### A. Supported Harnesses (`discover.AGENTS`)
Defined in [`discover.py`](agentplay/python/src/agentplay/discover.py):

| Harness (`agentTool`) | Parser Module | Source Format |
| :--- | :--- | :--- |
| `claude-code` | `parsers/claude_code.py` | `~/.claude/projects/**/*.jsonl` (+ subagents) |
| `codex` | `parsers/codex.py` | `~/.codex/sessions/**/*.jsonl` |
| `cursor` | `parsers/cursor_store.py` & `cursor_agent_transcript.py` | `~/.cursor` transcripts, `chats/*/store.db`, VS Code `state.vscdb` |
| `copilot` / `copilot-vscode` | `parsers/copilot.py` & `copilot_vscode.py` | `~/.copilot/session-state/**` & VS Code `chatSessions` |
| `antigravity-cli` | `parsers/antigravity.py` | `~/.gemini/antigravity-cli/brain/*` (or `~/.gemini/antigravity` via env var) step logs (`transcript_full.jsonl`) |
| `gemini-cli` | `parsers/gemini.py` | `~/.gemini/tmp/*/chats/session-*.jsonl` |
| `opencode` | `parsers/opencode.py` | `~/.local/share/opencode/opencode.db` (SQLite) |
| `kiro` | `parsers/kiro.py` | `~/.kiro/sessions` |
| `command-code` | `parsers/command_code.py` | `~/.commandcode/projects/*/*.jsonl` |
| `goose` | `parsers/goose.py` | `sessions.db` (SQLite) |

### B. Wrappers & Normalization Layers Used
1. **Materialization Wrapper (`materialize.py`)**: Database-backed harnesses (`cursor`, `opencode`, `kiro`, `goose`) store sessions in SQLite/binary stores. `materialize.py` decodes them into cached NDJSON files under `~/.agentplay/cache/` before parsing.
2. **Universal Span Wrapper (`spans.py` → `SpanData` / `TraceData`)**: Every parser extracts agent-specific records (for example, `antigravity.py` unwraps `<USER_REQUEST>` prompt wrappers and pairs `PLANNER_RESPONSE` tool calls with `GENERIC` results) into an OpenTelemetry/OpenInference-inspired `SpanData` dataclass.
3. **Tool Taxonomy Wrapper (`tool_taxonomy.py`)**: Maps vendor-specific tool names into canonical names (Claude Code vocabulary) so downstream metrics work uniformly across every agent:
   - Antigravity / Cursor / Codex `run_command`, `run_terminal_command_v2`, `Shell`, `exec_command` → **`Bash`**
   - `read_file`, `view_file`, `ReadFile` → **`Read`**
   - `edit_file`, `apply_patch`, `StrReplace` → **`Edit`**
   - `write_file`, `write_to_file` → **`Write`**
   - `grep_search`, `ripgrep_raw_search`, `rg` → **`Grep`**
   - `invoke_subagent`, `Subagent`, `task_v2` → **`Task`**
4. **Redaction & Map Schema Wrapper (`builder.py` → `agentplay-v1`)**: Converts raw spans into the shareable `agentplay-v1` JSON map (`schema/agentplay-v1.schema.json`), stripping prompt text, file contents, and shell arguments while retaining tool verbs, error classes, token counts, costs, PRs, and commits.
5. **Hackathon Discovery & Hub Wrappers (added in this workspace)**:
   - **Antigravity IDE Path Wrapper**: Setting `AGENTPLAY_ANTIGRAVITY_HOMES="$HOME\.gemini\antigravity"` points `agentplay` at Antigravity IDE's local directory (instead of the default `~/.gemini/antigravity-cli`).
   - **Upload & Leaderboard Wrapper (`server_7400.py` + `sync_to_hub.py`)**: Because open-source `agentplay` is strictly local-only (no built-in cloud upload endpoint), `server_7400.py` wraps `agentplay.facts.compute()` and `agentplay.health` around a multi-user HTTP ingestion endpoint (`POST /api/upload`).

---

## 4. Multi-User Leaderboard: If I Upload, Will Everyone See My Name?

### Short Answer: **Not if you run on `127.0.0.1:7400`!**

- **`127.0.0.1` is loopback (localhost)** — it only exists on *your* laptop.
- If you upload to `http://127.0.0.1:7400`, **only you** see your name on your browser. If another participant opens `127.0.0.1:7400` on their laptop, it connects to *their* own machine, not yours.

### What Should We Do So Everyone Sees Everyone on One Leaderboard?

All participants must point both their **browser** and their **uploads** to **one shared hub URL** running `server_7400.py`. Pick one of these 3 setups:

#### Option A — Same Wi-Fi / Hackathon LAN (Fastest, no cloud needed)
1. Start the leaderboard bound to all network interfaces (`0.0.0.0`) on the host laptop:
   ```powershell
   python server_7400.py --host 0.0.0.0 --port 7400
   ```
2. Allow inbound TCP port `7400` in Windows Defender Firewall (if prompted).
3. Find your Wi-Fi IPv4 address using `ipconfig` (for example `192.168.1.42`).
4. Share **`http://192.168.1.42:7400`** with all participants:
   - **Everyone opens** `http://192.168.1.42:7400` in their browser to view the live leaderboard.
   - **Everyone uploads** using that IP:
     ```powershell
     # PowerShell
     Invoke-RestMethod -Method Post -Uri "http://192.168.1.42:7400/api/upload?participant=Name&team=Team" -InFile .\session.json.gz
     ```
     ```bash
     # macOS / Linux / Git Bash
     curl -X POST "http://192.168.1.42:7400/api/upload?participant=Name&team=Team" --data-binary @session.json.gz
     ```
     Or auto-sync live with:
     ```bash
     python sync_to_hub.py --name "Name" --team "Team" --hub http://192.168.1.42:7400 --watch
     ```

#### Option B — Different Networks / Remote Participants (Public Tunnel in 1 Command)
Keep `server_7400.py` running locally on `127.0.0.1:7400` and expose it through a quick tunnel:
```powershell
cloudflared tunnel --url http://127.0.0.1:7400
# or: ngrok http 7400
```
Share the generated `https://...` URL — everyone anywhere on the internet uploads to and views the same live `leaderboard_data.json`.

#### Option C — Cloud Hosting (Recommended for Large / Multi-Day Hackathons)
Deploy `server_7400.py` to a small VM, Railway, Render, or Fly.io with `pip install agentplay` and a persistent disk volume for `leaderboard_data.json` and `uploaded_sessions/`. (For public deployments, add a simple `?token=<EVENT_CODE>` check before `/api/upload` so strangers cannot post to your board.)

---

## 5. Hub Endpoints & Views (`:7400`)

| Route | Purpose | Audience |
| :--- | :--- | :--- |
| **`/`** | **Main Leaderboard Dashboard**: Live participant & team rankings, sparklines, MCP calls, commits, spend, and click-to-replay modal. | All participants & mentors |
| **`/stage`** | **Venue Stage / Projector View**: Full-screen dark mode HUD with Top 3 Podium, live marquee ticker, and active stats for the big screen. | Stage projector & judges |
| **`/join`** | **1-Click Quick Join Web Page**: Interactive registration UI that generates copy-paste commands for participants. | New participants joining |
| **`/join.ps1`** | **PowerShell Auto-Sync Script**: Windows 1-liner (`irm http://HUB:7400/join.ps1 \| iex`). | Windows developers |
| **`/join.sh`** | **Bash Auto-Sync Script**: Mac/Linux 1-liner (`curl -sSL http://HUB:7400/join.sh \| bash`). | Mac & Linux developers |
| **`/api/session?id=...`** | **Session Replay API**: Returns complete chronological timeline, MCP tools, Git actions, and error recovery steps for modal replay. | Dashboard UI |
| **`/api/upload`** | **Map Ingestion Endpoint**: Accepts `.json` or `.json.gz` maps from CLI or browser. | Upload clients & daemons |

---

## 6. Quick Start Commands (Manual Run)

Start the **Hackathon Control Leaderboard (`:7400`)**:
```powershell
python C:\Users\akhil\Desktop\Observability\server_7400.py
```

Start the **Personal `agentplay` Session Viewer (`:7317`)**:
```powershell
$env:AGENTPLAY_ANTIGRAVITY_HOMES = "$HOME\.gemini\antigravity"
C:\Users\akhil\AppData\Roaming\Python\Python314\Scripts\agentplay.exe view
```

Stop either server anytime with **`Ctrl + C`** in its terminal.

