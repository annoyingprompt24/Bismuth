"""
State recovery module — detects incomplete sprints on container restart
and flags for user confirmation before resuming.
"""

import json
import logging
from pathlib import Path
from datetime import datetime

log = logging.getLogger("bismuth.recovery")


def check_and_recover(state_path: Path, socketio) -> dict:
    """
    Called on agent startup. Inspects persisted state and determines
    if a crash recovery flow is needed.
    Returns the current state dict.
    """
    state_file = state_path / "bismuth.json"

    if not state_file.exists():
        log.info("No previous state found — clean start")
        return _default_state()

    state = json.loads(state_file.read_text())
    log.info(f"Previous state found: phase={state.get('phase')}, sprint={state.get('current_sprint')}")

    # If agent was mid-sprint or running, flag crash recovery
    if state.get("phase") in ("running", "planning"):
        log.warning("Crash detected — agent was active at last shutdown")
        log.warning(f"Last successful sprint: {state.get('current_sprint', 0)}")
        state["phase"]          = "crash_recovery"
        state["status"]         = "red"
        state["awaiting_input"] = True
        state["input_prompt"]   = (
            "⚠️ The agent was interrupted unexpectedly. "
            f"Last active sprint: {state.get('current_sprint', 0)}. "
            "Type **resume** to continue from the last completed sprint, "
            "or **restart** to start the sprint plan from the beginning."
        )
        state_file.write_text(json.dumps(state, indent=2))

        # Broadcast crash recovery state to UI
        socketio.emit("state_update", state)
        socketio.emit("agent_message", {
            "type": "flag",
            "content": state["input_prompt"],
            "ts": datetime.utcnow().isoformat()
        })

    return state


def _default_state() -> dict:
    return {
        "initialised": False,
        "project": None,
        "phase": "setup",
        "current_sprint": 0,
        "current_iteration": 0,
        "yellow_cards": 0,
        "status": "grey",
        "awaiting_input": False,
        "input_prompt": None,
    }
