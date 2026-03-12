# BISMUTH — Recursive AI Development Pipeline

A self-contained, Docker-hosted AI agentic development system using the **Bismuth methodology**: short, focused sprints with learnings, git integration, milestone gates, and a visual roadmap.

---

## Quick Start

### 1. Prerequisites
- Docker + Portainer with Traefik running on the `proxy` network
- Anthropic API key — get one at [console.anthropic.com](https://console.anthropic.com)
- This repo pushed to GitHub
- (Optional) GitHub OAuth app credentials for external repo sync

### 2. Add bismuth.localhost to your hosts file

On the machine you'll browse from:
```bash
echo "127.0.0.1 bismuth.localhost" | sudo tee -a /etc/hosts
```

### 3. Deploy via Portainer

1. In `docker-compose.yml`, replace both occurrences of `YOUR_GITHUB_USERNAME` with your actual GitHub username
2. Commit and push to GitHub
3. Portainer → **Stacks** → **Add stack** → **Git Repository**
4. Set:
   - **Repository URL:** `https://github.com/YOUR_USERNAME/bismuth`
   - **Repository reference:** `refs/heads/main`
   - **Compose path:** `docker-compose.yml`
5. Click **Deploy the stack**

Portainer reads the compose file from git, then Docker builds `bismuth-ui` and `bismuth-agent` by pulling their respective subdirectories directly from GitHub — no local path resolution needed.

### 4. Open the UI

Navigate to **http://bismuth.localhost** — Traefik routes it automatically.

On first run you'll be prompted for your Anthropic API key and optional GitHub credentials. These are stored in the `bismuth-state` volume and never committed to git.

### 5. Start a project

Choose to fill in the **web form** or **upload a YAML** file (see `volumes/state/project.example.yaml` for the schema).

### 6. Updating Bismuth

Portainer → Stacks → bismuth → **Pull and redeploy**. All volumes and data are preserved.

---

## Architecture

```
http://bismuth.localhost        → Web UI (roadmap + terminal)
http://bismuth.localhost/git    → Gitea (git browser)
localhost:2222                  → Gitea SSH
```

### Services

| Service          | Role                                       |
|------------------|--------------------------------------------|
| `bismuth-ui`     | Next.js — roadmap, terminal, project setup |
| `bismuth-agent`  | Python — Claude agentic loop               |
| `bismuth-gitea`  | Local git server with web UI               |

---

## The Bismuth Methodology

Each **sprint**:
1. Reads previous learnings from `BISMUTH.md`
2. Executes a single focused objective
3. Commits to a dedicated branch (`bismuth/sprint-NNN`)
4. Tags the commit (`sprint-NNN`)
5. Updates `BISMUTH.md` with learnings
6. Updates the roadmap card with commit link

Every **N sprints** (configurable): iteration checkpoint comparing progress to roadmap.

**Milestone gates**: hard pause requiring user accept/realign before proceeding.

---

## Status Colours

| Colour | Meaning                              |
|--------|--------------------------------------|
| ⚫ Grey  | Inactive / not yet started           |
| 🟢 Green | Active, running, on track            |
| 🟡 Yellow| Issue detected, agent retrying       |
| 🔵 Blue  | Awaiting human input / gate          |
| 🔴 Red   | Critical error, human review required|

---

## Volumes

All data stored in named Docker volumes — persisted across Portainer redeployments and stack updates.

| Volume              | Contents                                             |
|---------------------|------------------------------------------------------|
| `bismuth-workspace` | Git repo — all project code the agent writes         |
| `bismuth-state`     | `bismuth.json`, `BISMUTH.md`, `roadmap.json`, `.env` |
| `bismuth-logs`      | Agent logs                                           |
| `bismuth-gitea`     | Gitea database + bare repos                          |

---

## Terminal Commands

| Command  | Effect                                          |
|----------|-------------------------------------------------|
| `BREAK`  | Pause agent at end of current sprint            |
| `resume` | Resume after a break or gate                    |
| Any text | Natural language message to the agent           |

Input is locked during active sprints except for `BREAK`.

---

## Crash Recovery

If the container restarts while a sprint is active, the agent will detect the interrupted state and prompt for confirmation before resuming.

---

## Security Notes

- API keys are stored in the `bismuth-state` Docker volume — **never committed to git**
- The `.gitignore` excludes all state files and secrets
- Gitea runs locally — no code leaves your machine unless you configure an external repo
