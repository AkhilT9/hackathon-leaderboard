# 🚀 Hackathon AI Agent Observability & Leaderboard — Quickstart Guide

> **A real-time telemetry hub, multi-agent leaderboard, and mentor assistance platform for AI hackathons.**  
> Supports **Cursor**, **Claude Code**, **Google Antigravity**, **GitHub Copilot**, **OpenCode**, and **Codex**.

---

## 🔗 Live Links (Ready to Use Right Now)

| Resource | Live Working Link | Description |
| :--- | :--- | :--- |
| 🌐 **Main Leaderboard** | [https://hackathon-leaderboard-6m5i.onrender.com/](https://hackathon-leaderboard-6m5i.onrender.com/) | Real-time participant standings, tool metrics, commit counters, and session replays. |
| 📺 **Stage / Projector View** | [https://hackathon-leaderboard-6m5i.onrender.com/stage](https://hackathon-leaderboard-6m5i.onrender.com/stage) | High-contrast neon auditorium HUD with live top-3 podium and real-time ticker. |
| ⚡ **1-Click Join Generator** | [https://hackathon-leaderboard-6m5i.onrender.com/join](https://hackathon-leaderboard-6m5i.onrender.com/join) | Simple web form to generate custom 1-line connection commands for your team. |
| 💻 **GitHub Repository** | [https://github.com/AkhilT9/hackathon-leaderboard](https://github.com/AkhilT9/hackathon-leaderboard) | Complete open-source codebase, Dockerfile, and deployment configurations. |

---

## 👤 Part 1: For Hackathon Participants (10-Second Setup)

You do **not** need to install any complex background services or create accounts. Just run your normal AI coding assistant, and use the 1-line command below to link your laptop to the leaderboard.

### Supported AI Coding Tools
The system automatically discovers sessions from:
* 🤖 **Cursor IDE** (Composer & Agent modes)
* ⚡ **Anthropic Claude Code**
* 🧠 **Google DeepMind Antigravity**
* 🐙 **GitHub Copilot** (CLI & VS Code)
* 🛠️ **OpenCode** (Terminal autonomous agent)
* 🔮 **OpenAI Codex** & **Google Gemini CLI**

---

### Step 1: Run the 1-Line Quick Join Command

Open your terminal or PowerShell on your laptop and paste the command for your operating system:

#### 🪟 Windows (PowerShell):
```powershell
irm "https://hackathon-leaderboard-6m5i.onrender.com/join.ps1?name=YOUR_NAME&team=YOUR_TEAM" | iex
```
*(Replace `YOUR_NAME` and `YOUR_TEAM` with your actual name and team name).*

#### 🍎 macOS / 🐧 Linux (Terminal):
```bash
curl -fsSL "https://hackathon-leaderboard-6m5i.onrender.com/join.sh?name=YOUR_NAME&team=YOUR_TEAM" | bash
```

**What this command does automatically:**
1. Verifies Python is installed.
2. Ensures the privacy-first `agentplay` telemetry client is present.
3. Automatically detects your latest AI agent sessions on your computer.
4. Redacts all source code, API keys, and sensitive tokens locally.
5. Uploads your session metrics to the live cloud leaderboard!

---

### Step 2: Keep It Auto-Syncing During the Hackathon (Optional)

If you want your score, tool calls, and git commits to update automatically as you code, run the background watcher:

```bash
# 1. Download the sync script (one-time)
curl -O https://raw.githubusercontent.com/AkhilT9/hackathon-leaderboard/main/sync_to_hub.py

# 2. Run with --watch (syncs every 60 seconds)
python sync_to_hub.py --hub https://hackathon-leaderboard-6m5i.onrender.com --name "YOUR_NAME" --team "YOUR_TEAM" --watch
```

---

### 🔒 Privacy & Security Guarantee
- **Does this share my code or prompts?** **NO.**
- `agentplay` processes everything **locally on your machine**. It only transmits statistical telemetry: tool names (e.g., `bash`, `read_file`), durations, error counts, and git commit hashes.
- Your code files, prompt texts, passwords, and API keys are **completely stripped and redacted** before anything leaves your machine.

---

## 🏆 Part 2: For Mentors, Judges & Organizers

### 1. 📺 Auditorium Big-Screen Display
Project the Stage HUD onto your hackathon's venue screens:
👉 **[https://hackathon-leaderboard-6m5i.onrender.com/stage](https://hackathon-leaderboard-6m5i.onrender.com/stage)**
- **Podium**: Automatically tracks 1st, 2nd, and 3rd place teams by health and throughput.
- **Live Ticker**: Displays real-time agent actions across the room (e.g., *"Team AlphaSquad just executed git commit #14"*).

---

### 2. 🔍 "See His Session" — Interactive Deep-Dive Modal
Want to see how a participant built their project or verify they didn't just copy-paste?
1. Open the **[Live Dashboard](https://hackathon-leaderboard-6m5i.onrender.com/)**.
2. Click on any participant's name (for example, click **"Akhil"**).
3. The **Interactive Session Replay Modal** opens instantly:
   - **Top Tools & MCPs**: Breakdown of Bash, Web Searches, and custom MCP tools used.
   - **Chronological Timeline**: Step-by-step breakdown of agent actions, step durations, and retries.
   - **Run Health**: Objective 0–100 score measuring error frequency and stability.

---

### 3. 🚨 Mentor SOS Alert (Catching Stuck Teams)
- The leaderboard automatically monitors error streaks.
- When an AI agent enters a failure loop (e.g. 3+ consecutive failed builds or high error counts), a flashing **`⚠️ Mentor SOS Alert`** banner appears on that participant's profile.
- Mentors can proactively walk over and unblock the team before they waste hours on a broken build.

---

## 🛠️ Part 3: For Developers (Self-Hosting in 2 Minutes)

Want to run your own private instance for an internal event or company hackathon?

### Option A: Run Locally (Localhost)
```bash
git clone https://github.com/AkhilT9/hackathon-leaderboard.git
cd hackathon-leaderboard
pip install -r requirements.txt
python server_7400.py
```
Open **`http://localhost:7400`** in your browser.

---

### Option B: Deploy Free to Cloud (Render / Railway)
1. Fork or push the repository to your GitHub account:
   `https://github.com/AkhilT9/hackathon-leaderboard`
2. Go to **[Render.com](https://render.com)** $\rightarrow$ Click **New Web Service** $\rightarrow$ Select your repo.
3. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python server_7400.py`
4. Click **Deploy Web Service** — Render assigns a free public HTTPS domain within 2 minutes!

---

## ❓ Frequently Asked Questions (FAQ)

**Q: Do participants need to be on the same local Wi-Fi?**  
**A:** No. The cloud leaderboard runs over public HTTPS on Render, so participants can join from anywhere in the world, across any network.

**Q: What if a participant doesn't have Python?**  
**A:** Python 3 is the only prerequisite for running `agentplay`. Every standard developer machine or AI workspace already includes Python.

**Q: Can we customize scoring criteria for our hackathon?**  
**A:** Yes! The scoring weights (for Git commits, MCP tools, tool volume, and error penalties) are configurable in `server_7400.py` under the ranking calculation function.

---

*Built with ❤️ for modern AI hackathons, hack nights, and multi-agent development competitions.*
