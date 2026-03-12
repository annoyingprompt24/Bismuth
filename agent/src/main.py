"""
Ralph Agent - Main Entry Point
Flask API + SocketIO server for the agentic loop
"""

import os
import json
import logging
from pathlib import Path
from flask import Flask, request, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from dotenv import load_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────
STATE_PATH  = Path(os.getenv("STATE_PATH", "/state"))
LOGS_PATH   = Path(os.getenv("LOGS_PATH", "/logs"))
WORKSPACE   = Path(os.getenv("WORKSPACE_PATH", "/workspace"))

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

# ── REST API ──────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "agent": "ralph"})

@app.route("/state", methods=["GET"])
def get_state():
    return jsonify(read_state())

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
    from src.bismuth import BismuthAgent

    data = request.json
    if not data.get("yaml_content"):
        return jsonify({"error": "No YAML content provided"}), 400

    try:
        project_config = yaml.safe_load(data["yaml_content"])
    except yaml.YAMLError as e:
        return jsonify({"error": f"Invalid YAML: {e}"}), 400

    # Persist project config
    (STATE_PATH / "project.yaml").write_text(data["yaml_content"])

    # Kick off roadmap generation in background
    socketio.start_background_task(
        BismuthAgent(socketio, STATE_PATH, WORKSPACE, LOGS_PATH).generate_roadmap,
        project_config
    )

    return jsonify({"success": True, "message": "Roadmap generation started"})

@app.route("/project/accept-roadmap", methods=["POST"])
def accept_roadmap():
    """User accepts the proposed roadmap — proceed to sprint planning"""
    from src.bismuth import BismuthAgent
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
    from src.bismuth import BismuthAgent
    state = read_state()
    state["phase"] = "running"
    state["status"] = "green"
    write_state(state)
    socketio.start_background_task(
        BismuthAgent(socketio, STATE_PATH, WORKSPACE, LOGS_PATH).run_loop
    )
    return jsonify({"success": True})

@app.route("/agent/input", methods=["POST"])
def agent_input():
    """Human response to an agent pause/clarification request"""
    from src.bismuth import BismuthAgent
    data = request.json
    if not data.get("message"):
        return jsonify({"error": "No message provided"}), 400

    BismuthAgent.deliver_input(data["message"])
    return jsonify({"success": True})

@app.route("/agent/break", methods=["POST"])
def agent_break():
    """Issue BREAK command — pause at end of current sprint"""
    from src.bismuth import BismuthAgent
    BismuthAgent.request_break()
    log.info("BREAK command issued by user")
    return jsonify({"success": True, "message": "Break requested — will pause after current sprint"})

@app.route("/agent/resume", methods=["POST"])
def agent_resume():
    """Resume after a break or gate pause"""
    from src.bismuth import BismuthAgent
    state = read_state()
    state["phase"] = "running"
    state["status"] = "green"
    state["awaiting_input"] = False
    write_state(state)
    socketio.start_background_task(
        BismuthAgent(socketio, STATE_PATH, WORKSPACE, LOGS_PATH).run_loop
    )
    return jsonify({"success": True})

# ── SocketIO events ───────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    log.info(f"UI client connected: {request.sid}")
    emit("state_update", read_state())

@socketio.on("chat_message")
def on_chat_message(data):
    """Natural language message from user terminal"""
    from src.bismuth import BismuthAgent
    state = read_state()

    # During active sprint — only BREAK is accepted
    if state["phase"] == "running" and not state["awaiting_input"]:
        if data.get("message", "").strip().upper() == "BREAK":
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
        BismuthAgent.deliver_input(data["message"])
        emit("agent_message", {"type": "user", "content": data["message"]})
        return

    # Otherwise treat as general chat
    emit("agent_message", {"type": "user", "content": data["message"]})

# ── Boot ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    STATE_PATH.mkdir(parents=True, exist_ok=True)
    LOGS_PATH.mkdir(parents=True, exist_ok=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    log.info("Ralph Agent starting on :5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
