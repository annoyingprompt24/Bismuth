"""
Ralph Agent Core
Implements the Ralph methodology sprint loop, state machine, and git integration.
"""

import os
import json
import time
import queue
import logging
import threading
import yaml
from pathlib import Path
from datetime import datetime
from typing import Optional

import anthropic
import git
import eventlet.tpool

log = logging.getLogger("bismuth.agent")

# ── Shared inter-thread communication ────────────────────────────────────────
_input_queue: queue.Queue = queue.Queue()
_break_requested: threading.Event = threading.Event()


class BismuthAgent:
    """
    Core agentic loop implementing the Ralph methodology.
    Short, focused sprints with learnings, git commits, and milestone gates.
    """

    def __init__(self, socketio, state_path: Path, workspace: Path, logs_path: Path):
        self.socketio    = socketio
        self.state_path  = state_path
        self.workspace   = workspace
        self.logs_path   = logs_path
        self.client      = None  # initialised lazily after API key confirmed
        self.conversation_history = []

    # ── Class-level control methods (callable without instance) ──────────────

    @classmethod
    def request_break(cls):
        _break_requested.set()

    @classmethod
    def deliver_input(cls, message: str):
        _input_queue.put(message)

    # ── State helpers ─────────────────────────────────────────────────────────

    def read_state(self) -> dict:
        f = self.state_path / "bismuth.json"
        return json.loads(f.read_text()) if f.exists() else {}

    def write_state(self, state: dict):
        (self.state_path / "bismuth.json").write_text(json.dumps(state, indent=2))
        self.socketio.emit("state_update", state)
        self.socketio.sleep(0)  # yield to event loop so the update is flushed

    def read_roadmap(self) -> dict:
        f = self.state_path / "roadmap.json"
        return json.loads(f.read_text()) if f.exists() else {}

    def write_roadmap(self, roadmap: dict):
        (self.state_path / "roadmap.json").write_text(json.dumps(roadmap, indent=2))
        self.socketio.emit("roadmap_update", roadmap)
        self.socketio.sleep(0)  # yield to event loop so the update is flushed

    def read_ralph_md(self) -> str:
        f = self.state_path / "BISMUTH.md"
        return f.read_text() if f.exists() else ""

    def write_ralph_md(self, content: str):
        (self.state_path / "BISMUTH.md").write_text(content)

    def read_project_yaml(self) -> dict:
        f = self.state_path / "project.yaml"
        return yaml.safe_load(f.read_text()) if f.exists() else {}

    # ── Claude API ────────────────────────────────────────────────────────────

    def get_client(self) -> anthropic.Anthropic:
        if not self.client:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not set — complete setup first")
            self.client = anthropic.Anthropic(api_key=api_key)
        return self.client

    def chat(self, user_message: str, system: Optional[str] = None) -> str:
        """Send a message to Claude and return the response text."""
        self.conversation_history.append({"role": "user", "content": user_message})

        kwargs = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 4096,
            "messages": self.conversation_history,
        }
        if system:
            kwargs["system"] = system

        # Run in a real OS thread so httpx doesn't block the eventlet event loop
        response = eventlet.tpool.execute(self.get_client().messages.create, **kwargs)
        reply = response.content[0].text

        self.conversation_history.append({"role": "assistant", "content": reply})
        self.emit_message("assistant", reply)
        return reply

    # ── Emit helpers ──────────────────────────────────────────────────────────

    def emit_message(self, msg_type: str, content: str):
        self.socketio.emit("agent_message", {"type": msg_type, "content": content})

    def emit_log(self, content: str, level: str = "info"):
        log.info(content)
        self.socketio.emit("agent_log", {"level": level, "content": content, "ts": datetime.utcnow().isoformat()})

    def set_status(self, status: str, phase: Optional[str] = None):
        """Update status colour and optionally phase."""
        state = self.read_state()
        state["status"] = status
        if phase:
            state["phase"] = phase
        self.write_state(state)

    def pause_for_input(self, prompt: str) -> str:
        """Pause execution and wait for human input via the terminal."""
        state = self.read_state()
        state["awaiting_input"] = True
        state["input_prompt"] = prompt
        state["status"] = "blue"
        self.write_state(state)

        self.emit_message("gate", f"⏸ **Input Required**\n\n{prompt}")

        # Block until user responds
        response = _input_queue.get(block=True)

        state = self.read_state()
        state["awaiting_input"] = False
        state["input_prompt"] = None
        self.write_state(state)

        return response

    # ── Git helpers ───────────────────────────────────────────────────────────

    def get_repo(self) -> git.Repo:
        try:
            return git.Repo(self.workspace)
        except git.InvalidGitRepositoryError:
            repo = git.Repo.init(self.workspace)
            # Create initial commit so branches can be made
            readme = self.workspace / "README.md"
            readme.write_text("# Ralph Project\n\nInitialised by Ralph Agent.\n")
            repo.index.add(["README.md"])
            repo.index.commit("chore: initialise repository")
            return repo

    def create_sprint_branch(self, sprint_id: str) -> str:
        branch = f"bismuth/sprint-{sprint_id}"
        repo = self.get_repo()
        repo.git.checkout("-b", branch)
        self.emit_log(f"Created branch: {branch}")
        return branch

    def commit_sprint(self, sprint_id: str, summary: str) -> str:
        try:
            repo = self.get_repo()
            repo.git.add(A=True)

            msg = f"bismuth(sprint-{sprint_id}): {summary}"
            if repo.is_dirty(untracked_files=True):
                commit = repo.index.commit(msg)
                sha = commit.hexsha[:8]
                self.emit_log(f"Committed sprint {sprint_id}: {sha}")
            else:
                log.warning(f"Sprint {sprint_id}: no changes to commit — using last commit as reference")
                commit = repo.head.commit
                sha = commit.hexsha[:8]

            tag = f"sprint-{sprint_id}"
            # Delete existing tag if present (retry case)
            try:
                repo.git.tag("-d", tag)
                log.info(f"Deleted existing tag {tag} before retag")
            except Exception:
                pass  # tag didn't exist
            repo.create_tag(tag, message=summary)

            return sha
        except Exception as e:
            log.warning(f"Git operations failed for sprint {sprint_id}: {e} — continuing without commit")
            self.emit_log(f"⚠️ Git commit/tag failed: {e}", level="warning")
            return "no-commit"

    def get_gitea_url(self, sprint_id: str) -> str:
        gitea_base = os.getenv("GITEA_URL", "http://localhost:3001")
        gitea_user = os.getenv("GITEA_USER", "bismuth")
        project    = self.read_project_yaml().get("project", {}).get("name", "project").lower().replace(" ", "-")
        return f"{gitea_base}/{gitea_user}/{project}/src/tag/sprint-{sprint_id}"

    # ── Phase 2: Roadmap generation ───────────────────────────────────────────

    def generate_roadmap(self, project_config: dict):
        """Generate initial roadmap from project YAML. User must accept before work begins."""
        self.emit_log("Generating roadmap from project config...")
        self.set_status("green", "planning")

        project      = project_config.get("project", {})
        name         = project.get("name", "Untitled Project")
        description  = project.get("description", "")
        dod          = project.get("definition_of_done", [])
        scope        = project.get("scope_boundaries", [])
        milestones   = project.get("milestones", [])
        sprints_per  = project.get("sprints_per_iteration", 6)

        system = """You are the Ralph planning agent. You create precise, executable project roadmaps.
Your roadmaps are structured, realistic, and broken into clear milestones.
Each milestone should be independently deliverable and testable.
Respond only in valid JSON."""

        prompt = f"""Create a project roadmap for:

Name: {name}
Description: {description}
Definition of Done: {json.dumps(dod)}
Scope Boundaries: {json.dumps(scope)}
Suggested Milestones: {json.dumps(milestones)}
Sprints per iteration: {sprints_per}

Return a JSON roadmap in this exact structure:
{{
  "project_name": "{name}",
  "total_milestones": <number>,
  "sprints_per_iteration": {sprints_per},
  "milestones": [
    {{
      "id": "M1",
      "title": "<title>",
      "description": "<description>",
      "definition_of_done": ["<criterion>"],
      "estimated_sprints": <number>,
      "status": "grey"
    }}
  ]
}}"""

        raw = self.chat(prompt, system=system)

        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]

        try:
            roadmap = json.loads(raw)
        except json.JSONDecodeError as e:
            log.error(f"generate_roadmap JSON parse failed: {e}. Raw: {raw[:500]}")
            self.set_status("red", "error")
            self.pause_for_input(
                "🔴 **Roadmap Generation Failed to Parse**\n\n"
                "The agent could not parse the generated roadmap. "
                "Type **retry** to regenerate or check the agent logs for details."
            )
            return
        self.write_roadmap(roadmap)
        self.emit_log(f"Roadmap generated: {roadmap['total_milestones']} milestones")

        # Present to user for acceptance
        state = self.read_state()
        state["phase"]          = "awaiting_roadmap_approval"
        state["status"]         = "blue"
        state["awaiting_input"] = True
        state["input_prompt"]   = "Please review the proposed roadmap and accept or realign."
        self.write_state(state)

        self.emit_message("gate", "📋 **Roadmap Ready for Review**\n\nPlease review the roadmap in the timeline view and click **Accept** to proceed or **Realign** to provide feedback.")

    # ── Phase 3: Sprint planning ───────────────────────────────────────────────

    def plan_sprints(self):
        """Break roadmap milestones into individual sprints. User accepts before execution."""
        roadmap  = self.read_roadmap()
        project  = self.read_project_yaml()
        self.emit_log("Planning sprints from roadmap...")

        system = """You are the Ralph sprint planning agent.
Break milestones into small, focused, independently-executable sprints.
Each sprint must have a single clear deliverable and take no more than a few Claude API calls to complete.
Respond only in valid JSON."""

        prompt = f"""Break this roadmap into sprints:

{json.dumps(roadmap, indent=2)}

Project scope boundaries: {json.dumps(project.get('project', {}).get('scope_boundaries', []))}

Return JSON:
{{
  "sprints": [
    {{
      "id": "001",
      "milestone_id": "M1",
      "title": "<short title>",
      "objective": "<single clear deliverable>",
      "acceptance_criteria": ["<criterion>"],
      "estimated_turns": <1-5>,
      "status": "grey"
    }}
  ]
}}"""

        raw = self.chat(prompt, system=system)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]

        try:
            sprint_plan = json.loads(raw)
        except json.JSONDecodeError as e:
            log.error(f"plan_sprints JSON parse failed: {e}. Raw: {raw[:500]}")
            self.set_status("red", "error")
            self.pause_for_input(
                "🔴 **Sprint Planning Failed to Parse**\n\n"
                "The agent could not parse the sprint plan. "
                "Type **retry** to regenerate or check the agent logs for details."
            )
            return

        # Merge into roadmap
        roadmap["sprints"] = sprint_plan["sprints"]
        roadmap["total_sprints"] = len(sprint_plan["sprints"])
        self.write_roadmap(roadmap)

        state = self.read_state()
        state["phase"]          = "awaiting_sprint_approval"
        state["status"]         = "blue"
        state["awaiting_input"] = True
        state["input_prompt"]   = "Please review the sprint plan and accept or provide feedback."
        self.write_state(state)

        self.emit_message("gate", f"🗂 **Sprint Plan Ready**\n\n{len(sprint_plan['sprints'])} sprints planned across {roadmap['total_milestones']} milestones.\n\nReview in the roadmap view and click **Accept Sprints** to begin execution.")

    # ── Phase 4: Main sprint execution loop ───────────────────────────────────

    def run_loop(self):
        """Main Ralph execution loop. Runs sprints sequentially."""
        roadmap = self.read_roadmap()
        state   = self.read_state()
        sprints = roadmap.get("sprints", [])

        start_sprint = state.get("current_sprint", 0)
        self.emit_log(f"Starting loop from sprint index {start_sprint}")

        for i, sprint in enumerate(sprints[start_sprint:], start=start_sprint):
            # Check for break request
            if _break_requested.is_set():
                _break_requested.clear()
                self.emit_message("system", "⏸ **Break activated.** Pausing after this sprint completes.\n\nType **resume** or click Resume when ready.")
                state = self.read_state()
                state["phase"]  = "paused"
                state["status"] = "blue"
                self.write_state(state)
                return

            state = self.read_state()
            state["current_sprint"] = i
            self.write_state(state)

            # Check for milestone gate BEFORE the sprint if it's the first of a new milestone
            self._check_milestone_gate(sprint, roadmap)

            # Execute the sprint
            success = self._execute_sprint(sprint, i)

            # Iteration checkpoint
            sprints_per = roadmap.get("sprints_per_iteration", 6)
            if (i + 1) % sprints_per == 0:
                self._iteration_checkpoint(roadmap, i)

        # All sprints done — final DoD check
        self._final_assessment()

    # ── Sprint execution ──────────────────────────────────────────────────────

    def _execute_sprint(self, sprint: dict, index: int) -> bool:
        sprint_id    = sprint["id"]
        objective    = sprint["objective"]
        criteria     = sprint.get("acceptance_criteria", [])
        max_retries  = 2
        yellow_cards = 0

        self.emit_log(f"▶ Sprint {sprint_id}: {sprint['title']}")
        self.set_status("green")

        # Update roadmap sprint status
        self._update_sprint_status(sprint_id, "green")

        for attempt in range(max_retries + 1):
            try:
                result = self._run_sprint_work(sprint, attempt)

                if result["success"]:
                    # Commit and update
                    sha = self.commit_sprint(sprint_id, objective)
                    gitea_url = self.get_gitea_url(sprint_id)
                    self._update_sprint_status(sprint_id, "complete", sha=sha, gitea_url=gitea_url)
                    self._update_ralph_md(sprint, result, sha, gitea_url)
                    self.emit_log(f"✅ Sprint {sprint_id} complete: {sha}")
                    return True

                else:
                    yellow_cards += 1
                    self._update_sprint_status(sprint_id, "yellow")
                    self.emit_message("flag", f"🟡 **Yellow Card #{yellow_cards}** — Sprint {sprint_id}\n\n{result.get('error', 'Sprint did not meet acceptance criteria.')}")

                    if yellow_cards >= 2:
                        self._update_sprint_status(sprint_id, "red")
                        self.set_status("red")
                        learnings = result.get('learnings', 'None')
                        learnings = (learnings[:200] + "...") if len(learnings) > 200 else learnings
                        review_msg = f"🔴 **Human Review Required** — Sprint {sprint_id} has failed twice.\n\n**Issue:** {result.get('error')}\n\n**Learnings so far:** {learnings}\n\nPlease provide direction to continue."
                        direction = self.pause_for_input(review_msg)
                        # Reset yellow cards and retry with human direction
                        yellow_cards = 0
                        sprint["human_direction"] = direction
                        self.set_status("green")

            except Exception as e:
                self.emit_log(f"Sprint {sprint_id} exception: {e}", level="error")
                yellow_cards += 1
                if yellow_cards >= 2:
                    direction = self.pause_for_input(f"🔴 **Sprint {sprint_id} errored twice:** `{e}`\n\nHow should we proceed?")
                    sprint["human_direction"] = direction

        return False

    def _run_sprint_work(self, sprint: dict, attempt: int) -> dict:
        """Ask Claude to execute the sprint work."""
        ralph_context = self.read_ralph_md()
        project       = self.read_project_yaml()
        scope         = project.get("project", {}).get("scope_boundaries", [])

        attempt_note = ""
        if attempt > 0:
            attempt_note = (
                f"\n\n⚠️ This is retry attempt {attempt}. Previous attempt failed. Apply learnings and try a different approach."
                "\n\nPREVIOUS ATTEMPT FAILED: You did not include a ```summary block at the end of your response. "
                "This is mandatory. Your response will be rejected without it. "
                "Do not write bash commands — write file contents directly."
            )
        if sprint.get("human_direction"):
            attempt_note += f"\n\n👤 Human direction: {sprint['human_direction']}"

        system = f"""You are Ralph, an AI development agent executing short focused sprints.

SCOPE BOUNDARIES (do not exceed these without flagging):
{json.dumps(scope, indent=2)}

PREVIOUS LEARNINGS & CONTEXT:
{ralph_context[-3000:] if ralph_context else 'No previous context.'}

You must:
1. Execute ONLY the sprint objective — nothing more
2. Flag scope creep immediately rather than proceeding
3. End with a JSON summary block marked ```summary```

CRITICAL RULES:
- You have no ability to run bash commands or a terminal
- Do not write ```bash blocks — they will not be executed
- Instead write the COMPLETE file contents directly in your response
- You MUST end your response with a ```summary block — without it the sprint fails
- The summary block must be valid JSON with keys: success, deliverable, learnings, scope_creep_detected, error
- If you cannot complete the objective write success: false in the summary with a clear error message — do not omit the summary block
"""

        prompt = f"""Execute this sprint:

Sprint ID: {sprint['id']}
Title: {sprint['title']}
Objective: {sprint['objective']}
Acceptance Criteria: {json.dumps(sprint.get('acceptance_criteria', []))}
{attempt_note}

Work through the objective step by step, then end with:
```summary
{{
  "success": true/false,
  "deliverable": "<what was produced>",
  "learnings": "<key learnings>",
  "scope_creep_detected": false,
  "error": null
}}
```"""

        raw = self.chat(prompt, system=system)

        # Extract summary block
        if "```summary" in raw:
            summary_raw = raw.split("```summary")[1].split("```")[0].strip()
            try:
                return json.loads(summary_raw)
            except json.JSONDecodeError as e:
                log.error(f"_run_sprint_work summary JSON parse failed: {e}. Raw: {summary_raw[:500]}")
                return {
                    "success": False,
                    "error": "Summary block was not valid JSON",
                    "learnings": "Agent returned a summary block but it could not be parsed as JSON. Will retry.",
                }

        # If no summary block, treat as failure
        return {
            "success": False,
            "error": "No summary block returned",
            "learnings": "Agent did not return a parseable summary. Will retry with stricter instructions.",
        }

    # ── Milestone gates ───────────────────────────────────────────────────────

    def _check_milestone_gate(self, sprint: dict, roadmap: dict):
        """If this sprint is the first in a new milestone, check if previous milestone is done."""
        milestone_id = sprint.get("milestone_id")
        if not milestone_id:
            return

        sprints = roadmap.get("sprints", [])
        milestone_sprints = [s for s in sprints if s.get("milestone_id") == milestone_id]

        # Is this the first sprint in this milestone?
        if milestone_sprints and milestone_sprints[0]["id"] != sprint["id"]:
            return

        # Find previous milestone
        milestones = roadmap.get("milestones", [])
        m_ids = [m["id"] for m in milestones]
        current_idx = m_ids.index(milestone_id) if milestone_id in m_ids else -1

        if current_idx <= 0:
            return  # First milestone, no gate needed

        prev_milestone = milestones[current_idx - 1]
        if prev_milestone.get("status") == "complete":
            # Pause at milestone gate
            self.set_status("blue")
            response = self.pause_for_input(
                f"🔵 **Milestone Gate: {prev_milestone['title']} Complete**\n\n"
                f"The previous milestone has been reached. Please review and choose:\n"
                f"- Type **accept** to proceed to {milestones[current_idx]['title']}\n"
                f"- Type **realign** followed by your feedback to adjust the plan"
            )

            if response.lower().startswith("realign"):
                feedback = response[len("realign"):].strip()
                self._realign_from_gate(feedback, milestone_id, roadmap)

            self.set_status("green")

    def _realign_from_gate(self, feedback: str, from_milestone: str, roadmap: dict):
        """User wants to realign — update roadmap based on feedback."""
        self.emit_log("Realigning roadmap from milestone gate feedback...")

        prompt = f"""The user has provided realignment feedback at milestone gate {from_milestone}:

Feedback: {feedback}

Current roadmap:
{json.dumps(roadmap, indent=2)}

Propose an updated roadmap. Return the full updated roadmap JSON.
If the number of milestones changes, flag this clearly in your response before the JSON."""

        raw = self.chat(prompt)

        try:
            if "```" in raw:
                raw_json = raw.split("```")[1]
                if raw_json.startswith("json"):
                    raw_json = raw_json[4:]
                updated = json.loads(raw_json.strip())
            else:
                updated = json.loads(raw)
        except json.JSONDecodeError as e:
            log.error(f"_realign_from_gate JSON parse failed: {e}. Raw: {raw[:500]}")
            self.emit_message("flag", "⚠️ Could not parse realignment response. Continuing with original roadmap.")
            return

        old_count = roadmap.get("total_milestones", 0)
        new_count = updated.get("total_milestones", 0)

        if old_count != new_count:
            confirm = self.pause_for_input(
                f"⚠️ **Roadmap step count changed:** {old_count} → {new_count} milestones.\n\n"
                f"Type **accept** to apply the change or **reject** to keep the current roadmap."
            )
            if confirm.lower() != "accept":
                self.emit_message("system", "Roadmap change rejected — continuing with original plan.")
                return

        self.write_roadmap(updated)
        self.emit_message("system", "✅ Roadmap updated and accepted.")

    # ── Iteration checkpoint ──────────────────────────────────────────────────

    def _iteration_checkpoint(self, roadmap: dict, sprint_index: int):
        """Every N sprints, compare roadmap to progress and propose updates."""
        self.emit_log(f"Iteration checkpoint at sprint {sprint_index}")
        ralph_md = self.read_ralph_md()

        prompt = f"""Perform an iteration checkpoint.

Current roadmap:
{json.dumps(roadmap, indent=2)}

Progress and learnings so far:
{ralph_md[-4000:]}

Compare the original plan to actual progress. Does the roadmap need updating?
If yes, return an updated roadmap JSON. If no changes needed, return {{"no_change": true}}."""

        raw = self.chat(prompt)

        if '"no_change": true' in raw or "no_change" in raw:
            self.emit_log("Iteration checkpoint: roadmap unchanged")
            return

        # Parse updated roadmap
        try:
            if "```" in raw:
                raw_json = raw.split("```")[1]
                if raw_json.startswith("json"):
                    raw_json = raw_json[4:]
                updated = json.loads(raw_json.strip())
            else:
                updated = json.loads(raw)

            old_count = roadmap.get("total_milestones", 0)
            new_count = updated.get("total_milestones", 0)

            if old_count != new_count:
                confirm = self.pause_for_input(
                    f"📊 **Iteration Checkpoint — Roadmap Change Proposed**\n\n"
                    f"Milestone count: {old_count} → {new_count}\n\n"
                    f"Type **accept** to apply or **reject** to keep current roadmap."
                )
                if confirm.lower() != "accept":
                    return

            self.write_roadmap(updated)
            self.emit_message("system", "✅ Roadmap updated at iteration checkpoint.")

        except json.JSONDecodeError as e:
            log.error(f"_iteration_checkpoint JSON parse failed: {e}. Raw: {raw[:500]}")
            self.emit_log(f"Checkpoint parse error (invalid JSON): {e}", level="warning")
        except Exception as e:
            self.emit_log(f"Checkpoint parse error: {e}", level="warning")

    # ── Final DoD assessment ──────────────────────────────────────────────────

    def _final_assessment(self):
        project  = self.read_project_yaml()
        dod      = project.get("project", {}).get("definition_of_done", [])
        ralph_md = self.read_ralph_md()

        self.emit_log("Running final Definition of Done assessment...")

        prompt = f"""Perform a final assessment against the Definition of Done.

Definition of Done:
{json.dumps(dod, indent=2)}

Project work completed:
{ralph_md}

For each DoD criterion, assess if it has been met. Return JSON:
{{
  "overall_pass": true/false,
  "criteria": [
    {{"criterion": "...", "met": true/false, "evidence": "..."}}
  ],
  "summary": "..."
}}"""

        raw = self.chat(prompt)
        raw = raw.strip()
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        if not raw:
            log.error("_final_assessment: empty response from Claude")
            self.set_status("red", "error")
            self.pause_for_input(
                "🔴 **DoD Assessment Failed to Parse**\n\n"
                "The agent received an empty response. "
                "Type **retry** to attempt again or **complete** to mark the project done."
            )
            return

        try:
            assessment = json.loads(raw)
        except json.JSONDecodeError as e:
            log.error(f"_final_assessment JSON parse failed: {e}. Raw: {raw[:500]}")
            self.set_status("red", "error")
            self.pause_for_input(
                "🔴 **DoD Assessment Failed to Parse**\n\n"
                "The agent could not parse the definition of done assessment. "
                "Type **retry** to attempt again or **complete** to mark the project done."
            )
            return

        if assessment.get("overall_pass"):
            self.set_status("green", "complete")
            self.emit_message("complete", f"🎉 **Project Complete!**\n\n{assessment['summary']}")
            self._push_to_external()
        else:
            failed = [c for c in assessment["criteria"] if not c["met"]]
            self.set_status("red", "error")
            direction = self.pause_for_input(
                f"🔴 **DoD Assessment Failed**\n\n"
                f"Unmet criteria:\n" +
                "\n".join(f"- {c['criterion']}" for c in failed) +
                f"\n\nHow would you like to proceed?"
            )

    def _push_to_external(self):
        external = os.getenv("EXTERNAL_REPO_URL")
        if not external:
            self.emit_log("No external repo configured — skipping push")
            return
        try:
            repo = self.get_repo()
            if "origin" not in [r.name for r in repo.remotes]:
                repo.create_remote("origin", external)
            repo.remotes.origin.push()
            self.emit_log(f"Pushed to external repo: {external}")
        except Exception as e:
            self.emit_log(f"External push failed: {e}", level="error")

    # ── BISMUTH.md update ───────────────────────────────────────────────────────

    def _update_ralph_md(self, sprint: dict, result: dict, sha: str, gitea_url: str):
        existing = self.read_ralph_md()
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

        new_entry = f"""
## Sprint {sprint['id']} — {sprint['title']}
**Completed:** {timestamp}
**Commit:** [{sha}]({gitea_url})
**Deliverable:** {result.get('deliverable', 'N/A')}
**Learnings:** {result.get('learnings', 'None')}
**Scope creep detected:** {result.get('scope_creep_detected', False)}

---
"""
        self.write_ralph_md(existing + new_entry)

    def _update_sprint_status(self, sprint_id: str, status: str, sha: str = None, gitea_url: str = None):
        roadmap = self.read_roadmap()
        for sprint in roadmap.get("sprints", []):
            if sprint["id"] == sprint_id:
                sprint["status"] = status
                if sha:
                    sprint["commit_sha"] = sha
                if gitea_url:
                    sprint["gitea_url"] = gitea_url
                sprint["updated_at"] = datetime.utcnow().isoformat()
                break
        self.write_roadmap(roadmap)
