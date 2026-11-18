# 🚀 Hackathon AI Leaderboard — Quick User Guide

> **Follow these exact steps to test the system in your browser or connect your own laptop.**

---

## 🏃 Option 1: Try It in 30 Seconds (Browser Only — No Setup Needed!)

If someone wants to see what this is and how it works without running any terminal commands, send them this:

### 1. Open the Live Leaderboard
👉 Click here: **[https://hackathon-leaderboard-6m5i.onrender.com/](https://hackathon-leaderboard-6m5i.onrender.com/)**  
*(See all participants, live tool calls, MCP queries, and git commits).*

### 2. Click on "Akhil" in the Table
👉 In the participant list, click directly on the row named **"Akhil"**.  
*(This opens the **Interactive Session Replay Modal**).*

### 3. See His Real Agent Timeline
👉 Scroll through his **175-step timeline**:
- See every tool his agent used (`bash`, `WebSearch`, `manage_task MCP`).
- See how long each step took and how errors were fixed.
- Check his **Run Health (52%)** score.

### 4. Look at the Red "Mentor SOS Alert"
👉 Look at the red warning banner at the top of the modal:  
`⚠️ Mentor SOS Alert: High error count: 12 errors encountered`  
*(This shows how hackathon mentors get notified automatically when a participant's agent is stuck in an error loop).*

### 5. Check the Big-Screen Projector View
👉 Click **"Stage Projector View"** at the top right, or open:  
**[https://hackathon-leaderboard-6m5i.onrender.com/stage](https://hackathon-leaderboard-6m5i.onrender.com/stage)**  
*(This is the full-screen cyberpunk auditorium view with the Top 3 Podium and real-time live ticker).*

---

## 💻 Option 2: Connect Your Own Laptop (1-Minute Participant Setup)

If a developer at the hackathon wants to connect their laptop so their own name and tools show up on the board:

### Supported AI Coding Tools:
- **Cursor IDE**
- **Claude Code**
- **Google Antigravity**
- **GitHub Copilot**
- **OpenCode**
- **OpenAI Codex**

---

### Step 1: Open Your Terminal
- **Windows:** Open PowerShell.
- **Mac / Linux:** Open Terminal.

### Step 2: Copy & Paste the 1-Line Join Command
*(Change `Alex` and `TeamRocket` to your own name and team):*

#### On Windows (PowerShell):
```powershell
irm "https://hackathon-leaderboard-6m5i.onrender.com/join.ps1?name=Alex&team=TeamRocket" | iex
```

#### On Mac / Linux (Terminal):
```bash
curl -fsSL "https://hackathon-leaderboard-6m5i.onrender.com/join.sh?name=Alex&team=TeamRocket" | bash
```

### Step 3: Refresh the Leaderboard!
👉 Go to **[https://hackathon-leaderboard-6m5i.onrender.com/](https://hackathon-leaderboard-6m5i.onrender.com/)**  
Your name (`Alex`) and team (`TeamRocket`) are now live on the board!

### Step 4: Click Your Name
👉 Click your row on the leaderboard to see your own tool stats, git commit count, and interactive timeline!

---

## 🔒 Privacy Guarantee: Does This Leak My Code?

**NO.**  
- The client scanner runs **100% locally on your computer**.
- It extracts **only numerical telemetry**: tool names (e.g. `bash`, `read_file`), step execution time, and error counts.
- **Your source code, prompts, passwords, and API keys are completely stripped** and never leave your machine.

---

## 🔗 Quick Links Summary
- **Live Leaderboard:** [https://hackathon-leaderboard-6m5i.onrender.com/](https://hackathon-leaderboard-6m5i.onrender.com/)
- **Stage Projector Display:** [https://hackathon-leaderboard-6m5i.onrender.com/stage](https://hackathon-leaderboard-6m5i.onrender.com/stage)
- **1-Click Join Generator:** [https://hackathon-leaderboard-6m5i.onrender.com/join](https://hackathon-leaderboard-6m5i.onrender.com/join)
- **GitHub Source Code:** [https://github.com/AkhilT9/hackathon-leaderboard](https://github.com/AkhilT9/hackathon-leaderboard)
