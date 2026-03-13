"""
Ralph Agent - Main Entry Point
Flask API + SocketIO server for the agentic loop
"""

import os
import json
import logging
import uuid
import shutil
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────
STATE_PATH    = Path(os.getenv("STATE_PATH", "/state"))
LOGS_PATH     = Path(os.getenv("LOGS_PATH", "/logs"))
WORKSPACE     = Path(os.getenv("WORKSPACE_PATH", "/workspace"))
PROJECTS_PATH = STATE_PATH / "projects"

# Load runtime secrets from state/.env (set via UI at first-run)
env_file = STATE_PATH / ".env"
if env_file.exists():
    load_dotenv(env_file)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOGS_PATH / "agent.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("bismuth")

# ── App ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24).hex()
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ── Loop activity flag + current agent reference ──────────────────────────────
_loop_running = False
_current_agent = None

def _run_loop_tracked(agent):
    """Wrapper that tracks whether run_loop is active."""
    global _loop_running, _current_agent
    _loop_running = True
    _current_agent = agent
    try:
        agent.run_loop()
    finally:
        _loop_running = False

# ── State helpers ─────────────────────────────────────────────────────────────
def read_state() -> dict:
    state_file = STATE_PATH / "bismuth.json"
    if state_file.exists():
        return json.loads(state_file.read_text())
    return {
        "initialised": False,
        "project": None,
        "phase": "setup",          # setup | planning | running | paused | complete | error
        "current_sprint": 0,
        "current_iteration": 0,
        "yellow_cards": 0,
        "status": "grey",          # grey | green | yellow | blue | red
        "awaiting_input": False,
        "input_prompt": None,
    }

def write_state(state: dict):
    state_file = STATE_PATH / "bismuth.json"
    STATE_PATH.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2))
    # Broadcast state change to all connected UI clients
    socketio.emit("state_update", state)
    # Auto-snapshot to project directory so project list stays current
    project_id = state.get("project_id")
    if project_id:
        proj_dir = PROJECTS_PATH / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "bismuth.json").write_text(json.dumps(state, indent=2))
        roadmap_file = STATE_PATH / "roadmap.json"
        if roadmap_file.exists():
            (proj_dir / "roadmap.json").write_text(roadmap_file.read_text())
        yaml_file = STATE_PATH / "project.yaml"
        if yaml_file.exists():
            (proj_dir / "project.yaml").write_text(yaml_file.read_text())

# ── Settings helpers ──────────────────────────────────────────────────────────

def _read_env_file() -> dict:
    env_file = STATE_PATH / ".env"
    if not env_file.exists():
        return {}
    result = {}
    for line in env_file.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            result[k.strip()] = v.strip()
    return result

def _write_env_file(env: dict):
    lines = [f"{k}={v}" for k, v in env.items() if v]
    STATE_PATH.mkdir(parents=True, exist_ok=True)
    (STATE_PATH / ".env").write_text("\n".join(lines))
    load_dotenv(STATE_PATH / ".env", override=True)

# ── REST API ──────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "agent": "ralph"})

@app.route("/agent/status", methods=["GET"])
def agent_status():
    """Returns current phase, sprint number, and whether the loop is actively running."""
    state = read_state()
    return jsonify({
        "phase": state.get("phase"),
        "current_sprint": state.get("current_sprint", 0),
        "loop_running": _loop_running,
        "awaiting_input": state.get("awaiting_input", False),
    })

@app.route("/state", methods=["GET"])
def get_state():
    state = read_state()
    if _current_agent is not None:
        total = _current_agent.tokens_used_input + _current_agent.tokens_used_output
        limit = _current_agent.token_limit_session
        state["token_stats"] = {
            "session_input":   _current_agent.tokens_used_input,
            "session_output":  _current_agent.tokens_used_output,
            "session_total":   total,
            "limit_session":   limit,
            "limit_per_minute": _current_agent.token_limit_per_minute,
            "percent_used":    round(total / limit * 100, 1) if limit else 0,
        }
    return jsonify(state)

@app.route("/project/export", methods=["GET"])
def export_project():
    import zipfile, io, subprocess
    state = read_state()
    project_name = (state.get("project") or "project").replace(" ", "-").lower()

    # Ensure working tree reflects the latest commit before zipping
    subprocess.run(
        ["git", "-C", str(WORKSPACE), "checkout", "HEAD"],
        capture_output=True,
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(WORKSPACE):
            dirs[:] = [d for d in dirs if d != ".git"]
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, WORKSPACE)
                zf.write(full_path, arcname)
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{project_name}-bismuth-export.zip",
    )

# ── Projects ──────────────────────────────────────────────────────────────────

@app.route("/projects", methods=["GET"])
def list_projects():
    PROJECTS_PATH.mkdir(parents=True, exist_ok=True)
    projects = []
    for proj_dir in sorted(PROJECTS_PATH.iterdir()):
        if not proj_dir.is_dir():
            continue
        state_file = proj_dir / "bismuth.json"
        if not state_file.exists():
            continue
        try:
            s = json.loads(state_file.read_text())
        except Exception:
            continue
        total_sprints = 0
        roadmap_file = proj_dir / "roadmap.json"
        if roadmap_file.exists():
            try:
                rm = json.loads(roadmap_file.read_text())
                total_sprints = rm.get("total_sprints", len(rm.get("sprints", [])))
            except Exception:
                pass
        projects.append({
            "id": proj_dir.name,
            "name": s.get("project", proj_dir.name),
            "status": s.get("status", "grey"),
            "phase": s.get("phase", "setup"),
            "current_sprint": s.get("current_sprint", 0),
            "total_sprints": total_sprints,
            "created_at": s.get("created_at"),
            "completed_at": s.get("completed_at"),
        })
    # Newest first
    projects.reverse()
    return jsonify(projects)

@app.route("/projects/new", methods=["POST"])
def projects_new():
    import yaml as _yaml
    from bismuth import BismuthAgent
    from datetime import datetime as _dt

    data = request.json
    if not data.get("yaml_content"):
        return jsonify({"error": "No YAML content provided"}), 400

    try:
        project_config = _yaml.safe_load(data["yaml_content"])
    except _yaml.YAMLError as e:
        return jsonify({"error": f"Invalid YAML: {e}"}), 400

    project_name = project_config.get("project", {}).get("name", "Project")
    project_id   = uuid.uuid4().hex[:8]

    # Create project directory and save YAML
    proj_dir = PROJECTS_PATH / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    (proj_dir / "project.yaml").write_text(data["yaml_content"])

    # Write to active state path too
    STATE_PATH.mkdir(parents=True, exist_ok=True)
    (STATE_PATH / "project.yaml").write_text(data["yaml_content"])

    # Clear workspace contents but keep the directory (it's a volume mount point)
    if WORKSPACE.exists():
        for item in os.scandir(WORKSPACE):
            if item.is_dir():
                shutil.rmtree(item.path)
            else:
                os.remove(item.path)
    else:
        WORKSPACE.mkdir(parents=True, exist_ok=True)

    # Set fresh active state
    state = {
        "initialised": True,
        "project": project_name,
        "project_id": project_id,
        "phase": "planning",
        "current_sprint": 0,
        "current_iteration": 0,
        "yellow_cards": 0,
        "status": "green",
        "awaiting_input": False,
        "input_prompt": None,
        "created_at": _dt.utcnow().isoformat(),
        "completed_at": None,
    }
    write_state(state)

    socketio.start_background_task(
        BismuthAgent(socketio, STATE_PATH, WORKSPACE, LOGS_PATH).generate_roadmap,
        project_config,
    )
    return jsonify({"success": True, "project_id": project_id})

@app.route("/projects/<project_id>/load", methods=["POST"])
def projects_load(project_id):
    proj_dir = PROJECTS_PATH / project_id
    if not proj_dir.exists():
        return jsonify({"error": "Project not found"}), 404

    state_file = proj_dir / "bismuth.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        write_state(state)

    roadmap_file = proj_dir / "roadmap.json"
    if roadmap_file.exists():
        content = roadmap_file.read_text()
        (STATE_PATH / "roadmap.json").write_text(content)
        socketio.emit("roadmap_update", json.loads(content))

    yaml_file = proj_dir / "project.yaml"
    if yaml_file.exists():
        (STATE_PATH / "project.yaml").write_text(yaml_file.read_text())

    log.info(f"Loaded project {project_id}")
    return jsonify({"success": True})

@app.route("/projects/<project_id>/export", methods=["GET"])
def projects_export(project_id):
    import zipfile, io, subprocess
    proj_dir = PROJECTS_PATH / project_id
    if not proj_dir.exists():
        return jsonify({"error": "Project not found"}), 404

    project_name = "project"
    state_file = proj_dir / "bismuth.json"
    if state_file.exists():
        try:
            s = json.loads(state_file.read_text())
            project_name = (s.get("project") or "project").replace(" ", "-").lower()
        except Exception:
            pass

    subprocess.run(["git", "-C", str(WORKSPACE), "checkout", "HEAD"], capture_output=True)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(WORKSPACE):
            dirs[:] = [d for d in dirs if d != ".git"]
            for file in files:
                full_path = os.path.join(root, file)
                arcname = os.path.relpath(full_path, WORKSPACE)
                zf.write(full_path, arcname)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{project_name}-bismuth-export.zip",
    )

# ── Settings ──────────────────────────────────────────────────────────────────

@app.route("/settings", methods=["GET"])
def get_settings():
    env = _read_env_file()
    return jsonify({
        "anthropic_api_key_set": bool(env.get("ANTHROPIC_API_KEY")),
        "github_token_set": bool(env.get("GITHUB_TOKEN")),
        "github_username": env.get("GITHUB_USERNAME", ""),
        "github_org": env.get("GITHUB_ORG", ""),
        "default_branch": env.get("DEFAULT_BRANCH", "main"),
        "sprints_per_iteration": int(env.get("SPRINTS_PER_ITERATION", 5)),
        "max_yellow_cards": int(env.get("MAX_YELLOW_CARDS", 2)),
    })

@app.route("/settings", methods=["POST"])
def save_settings():
    data = request.json
    env = _read_env_file()

    if data.get("anthropic_api_key"):
        env["ANTHROPIC_API_KEY"] = data["anthropic_api_key"]
    if data.get("github_token"):
        env["GITHUB_TOKEN"] = data["github_token"]
    for key, env_key in [
        ("github_username",      "GITHUB_USERNAME"),
        ("github_org",           "GITHUB_ORG"),
        ("default_branch",       "DEFAULT_BRANCH"),
    ]:
        if key in data:
            env[env_key] = data[key]
    if "sprints_per_iteration" in data:
        env["SPRINTS_PER_ITERATION"] = str(data["sprints_per_iteration"])
    if "max_yellow_cards" in data:
        env["MAX_YELLOW_CARDS"] = str(data["max_yellow_cards"])

    _write_env_file(env)

    state = read_state()
    state["initialised"] = True
    write_state(state)

    log.info("Settings updated")
    return jsonify({"success": True})

@app.route("/projects/reset", methods=["POST"])
def projects_reset():
    """Clear all active state ready for a fresh project — called by UI before showing new-project form."""
    global _current_agent, _loop_running

    # Write a clean idle state (keep initialised=True so UI stays on projects screen, not setup)
    state = {
        "initialised": True,
        "project": None,
        "project_id": None,
        "phase": "setup",
        "current_sprint": 0,
        "current_iteration": 0,
        "yellow_cards": 0,
        "status": "grey",
        "awaiting_input": False,
        "input_prompt": None,
    }
    write_state(state)  # also emits state_update to all clients

    # Remove roadmap so re-fetches return empty
    roadmap_file = STATE_PATH / "roadmap.json"
    if roadmap_file.exists():
        roadmap_file.unlink()

    # Remove living guide
    guide_file = STATE_PATH / "GUIDE.md"
    if guide_file.exists():
        guide_file.unlink()

    # Clear workspace contents but keep the directory (volume mount point)
    if WORKSPACE.exists():
        for item in os.scandir(WORKSPACE):
            if item.is_dir():
                shutil.rmtree(item.path)
            else:
                os.remove(item.path)

    _current_agent = None
    _loop_running = False

    log.info("Project state reset via /projects/reset")
    return jsonify({"status": "reset"})


@app.route("/roadmap", methods=["GET"])
def get_roadmap():
    roadmap_file = STATE_PATH / "roadmap.json"
    if roadmap_file.exists():
        return jsonify(json.loads(roadmap_file.read_text()))
    return jsonify({})

@app.route("/setup/keys", methods=["POST"])
def setup_keys():
    """Receive API keys from first-run UI and persist to state/.env"""
    data = request.json
    required = ["anthropic_api_key"]
    if not all(k in data for k in required):
        return jsonify({"error": "Missing required keys"}), 400

    env_lines = [
        f"ANTHROPIC_API_KEY={data['anthropic_api_key']}",
    ]
    if data.get("github_client_id"):
        env_lines.append(f"GITHUB_CLIENT_ID={data['github_client_id']}")
    if data.get("github_client_secret"):
        env_lines.append(f"GITHUB_CLIENT_SECRET={data['github_client_secret']}")
    if data.get("external_repo_url"):
        env_lines.append(f"EXTERNAL_REPO_URL={data['external_repo_url']}")

    STATE_PATH.mkdir(parents=True, exist_ok=True)
    (STATE_PATH / ".env").write_text("\n".join(env_lines))
    load_dotenv(STATE_PATH / ".env", override=True)

    state = read_state()
    state["initialised"] = True
    write_state(state)

    log.info("API keys configured via setup UI")
    return jsonify({"success": True})

@app.route("/project/start", methods=["POST"])
def project_start():
    """Receive project YAML and kick off roadmap generation"""
    import yaml
    from bismuth import BismuthAgent

    data = request.json
    if not data.get("yaml_content"):
        return jsonify({"error": "No YAML content provided"}), 400

    try:
        project_config = yaml.safe_load(data["yaml_content"])
    except yaml.YAMLError as e:
        return jsonify({"error": f"Invalid YAML: {e}"}), 400

    # Persist project config
    (STATE_PATH / "project.yaml").write_text(data["yaml_content"])

    # Update state so the UI transitions to the dashboard immediately
    project_name = project_config.get("project", {}).get("name", "Project")
    state = read_state()
    state["project"] = project_name
    state["phase"] = "planning"
    state["status"] = "green"
    write_state(state)

    # Kick off roadmap generation in background
    socketio.start_background_task(
        BismuthAgent(socketio, STATE_PATH, WORKSPACE, LOGS_PATH).generate_roadmap,
        project_config
    )

    return jsonify({"success": True, "message": "Roadmap generation started"})

@app.route("/project/accept-roadmap", methods=["POST"])
def accept_roadmap():
    """User accepts the proposed roadmap — proceed to sprint planning"""
    from bismuth import BismuthAgent
    state = read_state()
    state["phase"] = "planning"
    write_state(state)
    socketio.start_background_task(
        BismuthAgent(socketio, STATE_PATH, WORKSPACE, LOGS_PATH).plan_sprints
    )
    return jsonify({"success": True})

@app.route("/project/accept-sprints", methods=["POST"])
def accept_sprints():
    """User accepts sprint plan — begin execution"""
    from bismuth import BismuthAgent
    state = read_state()
    state["phase"] = "running"
    state["status"] = "green"
    write_state(state)
    agent = BismuthAgent(socketio, STATE_PATH, WORKSPACE, LOGS_PATH)
    socketio.start_background_task(_run_loop_tracked, agent)
    return jsonify({"success": True})

@app.route("/agent/input", methods=["POST"])
def agent_input():
    """Human response to an agent pause/clarification request"""
    from bismuth import BismuthAgent
    data = request.json
    if not data.get("message"):
        return jsonify({"error": "No message provided"}), 400

    BismuthAgent.deliver_input(data["message"])
    return jsonify({"success": True})

@app.route("/agent/break", methods=["POST"])
def agent_break():
    """Issue BREAK command — pause at end of current sprint"""
    from bismuth import BismuthAgent
    BismuthAgent.request_break()
    log.info("BREAK command issued by user")
    return jsonify({"success": True, "message": "Break requested — will pause after current sprint"})

@app.route("/agent/resume", methods=["POST"])
def agent_resume():
    """Resume after a break, gate pause, or crash recovery"""
    from bismuth import BismuthAgent
    state = read_state()
    sprint_index = state.get("current_sprint", 0)
    state["phase"] = "running"
    state["status"] = "green"
    state["awaiting_input"] = False
    state["input_prompt"] = None
    write_state(state)
    socketio.emit("agent_message", {
        "type": "system",
        "content": f"▶ Agent loop resuming from sprint {sprint_index}"
    })
    agent = BismuthAgent(socketio, STATE_PATH, WORKSPACE, LOGS_PATH)
    socketio.start_background_task(_run_loop_tracked, agent)
    return jsonify({"success": True, "resuming_from_sprint": sprint_index})

# ── SocketIO events ───────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    log.info(f"UI client connected: {request.sid}")
    emit("state_update", read_state())

@socketio.on("chat_message")
def on_chat_message(data):
    """Natural language message from user terminal"""
    from bismuth import BismuthAgent
    state = read_state()
    message = data.get("message", "").strip()

    # Crash recovery — handle resume/restart commands
    if state.get("phase") == "crash_recovery":
        cmd = message.lower()
        if cmd == "restart":
            state["current_sprint"] = 0
            write_state(state)
            emit("agent_message", {"type": "system", "content": "↩ Restarting from sprint 0..."})
        elif cmd == "resume":
            emit("agent_message", {"type": "system", "content": f"▶ Resuming from sprint {state.get('current_sprint', 0)}..."})
        else:
            emit("agent_message", {"type": "system", "content": "Type **resume** to continue from the last sprint, or **restart** to begin from sprint 0."})
            return
        # Trigger resume via the REST logic directly
        state = read_state()
        sprint_index = state.get("current_sprint", 0)
        state["phase"] = "running"
        state["status"] = "green"
        state["awaiting_input"] = False
        state["input_prompt"] = None
        write_state(state)
        socketio.emit("agent_message", {"type": "system", "content": f"▶ Agent loop resuming from sprint {sprint_index}"})
        agent = BismuthAgent(socketio, STATE_PATH, WORKSPACE, LOGS_PATH)
        socketio.start_background_task(_run_loop_tracked, agent)
        return

    # During active sprint — only BREAK is accepted
    if state["phase"] == "running" and not state["awaiting_input"]:
        if message.upper() == "BREAK":
            BismuthAgent.request_break()
            emit("agent_message", {
                "type": "system",
                "content": "⏸ Break requested. Agent will pause after the current sprint completes."
            })
        else:
            emit("agent_message", {
                "type": "system",
                "content": "🔒 Agent is mid-sprint. Input locked. Type BREAK to pause after this sprint."
            })
        return

    # Agent is awaiting input — deliver message
    if state["awaiting_input"]:
        BismuthAgent.deliver_input(message)
        emit("agent_message", {"type": "system", "content": "✓ Message received by agent"})
        return

    # Otherwise treat as general chat — confirm receipt, no echo (client already shows it)
    emit("agent_message", {"type": "system", "content": "✓ Message received by agent"})

# ── Boot ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    STATE_PATH.mkdir(parents=True, exist_ok=True)
    LOGS_PATH.mkdir(parents=True, exist_ok=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    log.info("Ralph Agent starting on :5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
