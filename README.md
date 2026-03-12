# BISMUTH — Recursive AI Development Pipeline

A self-contained, Docker-hosted AI agentic development system using the **Bismuth methodology**: short, focused sprints with learnings, git integration, milestone gates, and a visual roadmap.

---

## Quick Start

### 1. Prerequisites
- Docker + Docker Compose
- Anthropic API key (get one at [console.anthropic.com](https://console.anthropic.com))
- (Optional) GitHub OAuth app credentials for external repo sync

### 2. Clone and start

```bash
git clone <this-repo>
cd bismuth-system
docker compose up -d
```

### 3. Open the UI

Navigate to **http://localhost** in your browser.

On first run, you'll be prompted to enter your Anthropic API key and optional GitHub OAuth credentials. These are stored in `volumes/state/.env` and never committed to git.

### 4. Start a project

Choose to fill in the **web form** or **upload a YAML** file (see `volumes/state/project.example.yaml` for the schema).

---

## Architecture

```
http://localhost        → Web UI (roadmap + terminal)
http://localhost/git    → Gitea (git browser)
http://localhost:3001   → Gitea direct access
```

### Services

| Service   | Role                                      |
|-----------|-------------------------------------------|
| `nginx`   | Reverse proxy — single entry point        |
| `web-ui`  | Next.js — roadmap, terminal, project setup|
| `agent`   | Python — Claude agentic loop              |
| `gitea`   | Local git server with web UI              |

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

| Path                    | Contents                              |
|-------------------------|---------------------------------------|
| `volumes/workspace`     | Git repo — all project code           |
| `volumes/state`         | `bismuth.json`, `BISMUTH.md`, `roadmap.json`, `.env` |
| `volumes/logs`          | Agent logs                            |

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

- API keys are stored in `volumes/state/.env` — **never committed to git**
- The `.gitignore` excludes `volumes/state/.env`
- Gitea runs locally — no code leaves your machine unless you configure an external repo
