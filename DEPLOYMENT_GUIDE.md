# Step-by-Step Gameplan: Local Testing & Cloud Deployment

This guide gives you the exact step-by-step instructions for:
1. **Testing on your desk today** (verifying the dashboard, replay modal, stage view, and live sync).
2. **Deploying to the Cloud for the Hackathon** (Railway or Render in under 3 minutes).

---

## Phase 1: Testing on Your Desk Today (Localhost)

The server is currently running in your workspace on **port 7400**.

### Step 1: Open the 3 Browser Views
Open these links in your browser to see the different views:

1. **Main Leaderboard Dashboard**:
   👉 **[http://127.0.0.1:7400/](http://127.0.0.1:7400/)**
   - See all participants, tool calls, MCP calls, and commits.
   - Click on **"Akhil"** in the table $\rightarrow$ The **Interactive Session Replay Modal** opens!
   - Inspect the top tools (`Bash`, `WebSearch`, `manage_task (MCP)`), Run Health, and the chronological step-by-step timeline.

2. **Stage / Projector View (For the Venue Big Screen)**:
   👉 **[http://127.0.0.1:7400/stage](http://127.0.0.1:7400/stage)**
   - Dark neon theme with live HUD stats.
   - Top 3 Team Podium (Gold, Silver, Bronze).
   - Real-time rolling ticker streaming live agent actions.

3. **1-Click Quick Join Page**:
   👉 **[http://127.0.0.1:7400/join](http://127.0.0.1:7400/join)**
   - Type in any name and team $\rightarrow$ generates the 1-line copy-paste terminal command.

---

### Step 2: Test a Participant Joining from Terminal
Open a new PowerShell terminal window and run:
```powershell
irm "http://127.0.0.1:7400/join.ps1?name=TestUser&team=AlphaSquad" | iex
```
*(Alternatively: `& ([scriptblock]::Create((irm http://127.0.0.1:7400/join.ps1))) -Name 'TestUser' -Team 'AlphaSquad'`)*
**What happens**:
1. It scans your local sessions.
2. Uploads the latest session map to the leaderboard.
3. Switch to your browser tab at `http://127.0.0.1:7400/` $\rightarrow$ **TestUser** and **AlphaSquad** immediately show up on the leaderboard with live sparklines!

---

## Phase 2: Deploying to Cloud for the Hackathon (Railway or Render)

All deployment configuration files have been created in your workspace:
- `requirements.txt` (defines `agentplay`)
- `Procfile` (tells cloud hosts to run `python server_7400.py`)
- `Dockerfile` (ready for Docker-based deployments)
- `render.yaml` (1-click blueprint for Render)
- `.dockerignore`

---

### Step 1: Push Your Code to GitHub (Takes 1 Minute)
Open PowerShell in `C:\Users\akhil\Desktop\Observability` and run:

```powershell
# 1. Initialize git
git init

# 2. Add the hub files (excludes heavy agentplay clone)
git add server_7400.py leaderboard_data.json requirements.txt Procfile Dockerfile render.yaml .dockerignore README.md EXPLAINER.md sync_to_hub.py

# 3. Commit
git commit -m "Hackathon Observability Hub & Leaderboard"

# 4. Create a repo on github.com (e.g. 'hackathon-leaderboard'), then link it:
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/hackathon-leaderboard.git
git push -u origin main
```

---

### Step 2: Choose Your Free Cloud Host (Takes 2 Minutes)

#### Option A: Railway.app (Fastest & Simplest — Recommended)
1. Go to **[https://railway.app](https://railway.app)** and click **Login with GitHub**.
2. Click **"+ New Project"** $\rightarrow$ select **"Deploy from GitHub repo"**.
3. Select your `hackathon-leaderboard` repository.
4. Click **"Deploy Now"**.
5. Once deployed, click on your service $\rightarrow$ go to **Settings** $\rightarrow$ **Networking** $\rightarrow$ click **"Generate Domain"**.
6. Railway gives you a permanent HTTPS link:
   `https://hackathon-leaderboard-production.up.railway.app`
7. **Done!**

---

#### Option B: Render.com (100% Free Forever)
1. Go to **[https://render.com](https://render.com)** and sign in with GitHub.
2. Click **"New +"** $\rightarrow$ select **"Web Service"**.
3. Connect your `hackathon-leaderboard` GitHub repository.
4. Fill in the fields:
   - **Name**: `hackathon-leaderboard`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python server_7400.py`
   - **Plan**: Select **Free**
5. Click **"Create Web Service"**.
6. In ~60 seconds, Render gives you a live public link:
   `https://hackathon-leaderboard.onrender.com`
7. **Done!**

---

## Phase 3: During the Hackathon Event

Once your cloud link is live (e.g. `https://hackathon-leaderboard.onrender.com`):

1. **For the Projector**:
   Open **`https://hackathon-leaderboard.onrender.com/stage`** on the venue screen or auditorium TV.
2. **For the Participants**:
   Put this link on the presentation slides or Discord/Slack:
   > *"To join the live leaderboard, go to https://hackathon-leaderboard.onrender.com/join"*
3. Participants open that link on their phones or laptops, copy the 1-liner, paste it into their terminal, and they are live on the leaderboard all weekend!

