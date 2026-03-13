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

import re
import subprocess
import urllib.request
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

        # Token usage tracking
        self.tokens_used_input      = 0
        self.tokens_used_output     = 0
        self.tokens_this_minute     = 0
        self.tokens_minute_reset    = time.time()
        self.token_limit_session    = int(os.environ.get("TOKEN_LIMIT_SESSION", "500000"))
        self.token_limit_per_minute = int(os.environ.get("TOKEN_LIMIT_PER_MINUTE", "25000"))

    # ── Class-level control methods (callable without instance) ──────────────

    @classmethod
    def request_break(cls):
        _break_requested.set()

    @classmethod
    def deliver_input(cls, message: str):
        log.info(f"deliver_input: queue size before={_input_queue.qsize()}, message='{message[:80]}'")
        _input_queue.put(message)
        log.info(f"deliver_input: queue size after={_input_queue.qsize()}")

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

    def chat(self, user_message: str, system: Optional[str] = None, max_tokens: int = 4096) -> str:
        """Send a message to Claude and return the response text. Retries on rate limit."""
        self.conversation_history.append({"role": "user", "content": user_message})

        # Self-throttle if approaching per-minute token limit
        now = time.time()
        if now - self.tokens_minute_reset > 60:
            self.tokens_this_minute = 0
            self.tokens_minute_reset = now
        if self.tokens_this_minute > self.token_limit_per_minute:
            wait = 60 - (now - self.tokens_minute_reset)
            if wait > 0:
                log.warning(f"Approaching rate limit ({self.tokens_this_minute} tokens this minute), waiting {wait:.0f}s")
                self.emit_log(f"⏳ Self-throttling for {wait:.0f}s to avoid rate limit...", level="warning")
                time.sleep(wait)
            self.tokens_this_minute = 0
            self.tokens_minute_reset = time.time()

        kwargs = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": max_tokens,
            "messages": self.conversation_history,
        }
        if system:
            kwargs["system"] = system

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Run in a real OS thread so httpx doesn't block the eventlet event loop
                response = eventlet.tpool.execute(self.get_client().messages.create, **kwargs)
                reply = response.content[0].text
                self.conversation_history.append({"role": "assistant", "content": reply})
                self.emit_message("assistant", reply)

                # Accumulate token usage
                usage = response.usage
                self.tokens_used_input  += usage.input_tokens
                self.tokens_used_output += usage.output_tokens
                self.tokens_this_minute += usage.input_tokens
                log.info(
                    f"Tokens: +{usage.input_tokens}in +{usage.output_tokens}out | "
                    f"Session total: {self.tokens_used_input}in {self.tokens_used_output}out"
                )

                # Check session budget
                session_total = self.tokens_used_input + self.tokens_used_output
                if session_total > self.token_limit_session:
                    direction = self.pause_for_input(
                        f"⚠️ **Token Budget Reached**\n\n"
                        f"Session has used {session_total:,} tokens "
                        f"(limit: {self.token_limit_session:,}).\n\n"
                        f"Type **continue** to raise the limit by 500,000 tokens and proceed, "
                        f"or **stop** to end the session."
                    )
                    if direction.strip().lower() == "continue":
                        self.token_limit_session += 500_000
                        self.emit_log(f"Token limit raised to {self.token_limit_session:,}")

                return reply
            except anthropic.RateLimitError:
                wait = 60 * (attempt + 1)  # 60s, 120s, 180s
                log.warning(f"Rate limit hit, waiting {wait}s before retry {attempt + 1}/{max_retries}")
                self.emit_log(f"⏳ Rate limit reached — waiting {wait}s before continuing...", level="warning")
                time.sleep(wait)
            except Exception as e:
                log.error(f"API call failed: {e}")
                raise

        raise Exception("Max retries exceeded due to rate limiting")

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
        log.info(f"pause_for_input: waiting on queue (queue size: {_input_queue.qsize()})")

        # Poll with a short timeout so the greenlet yields to the eventlet hub
        # on each iteration — guarantees socket events (chat_message) can be
        # processed even if monkey_patch is not in effect.
        while True:
            try:
                response = _input_queue.get(timeout=1.0)
                break
            except queue.Empty:
                time.sleep(0)   # yield to eventlet hub
                continue

        log.info(f"pause_for_input: received response '{response[:80]}'")
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

            # Ensure working tree reflects the committed state
            try:
                branch = repo.active_branch.name
                repo.git.checkout(branch)
                log.info(f"Checked out {branch} after sprint commit")
            except Exception as ce:
                log.warning(f"Post-commit checkout failed: {ce}")

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

        raw = self.chat(prompt, system=system, max_tokens=2048)

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

        raw = self.chat(prompt, system=system, max_tokens=2048)
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

            # Inter-sprint delay to avoid burst rate limiting
            sprint_delay = int(os.environ.get("SPRINT_DELAY_SECONDS", "10"))
            if sprint_delay > 0 and i < len(sprints) - 1:
                self.emit_log(f"⏱ Waiting {sprint_delay}s before next sprint...")
                time.sleep(sprint_delay)

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
        yellow_cards = 0
        attempt      = 0

        self.emit_log(f"▶ Sprint {sprint_id}: {sprint['title']}")
        self.set_status("green", "running")

        # Update roadmap sprint status
        self._update_sprint_status(sprint_id, "green")

        # Unbounded retry loop: exits only on success, skip, or clean failure.
        # A bounded `for` loop would exhaust its iterations at the exact point
        # pause_for_input() returns, leaving no iteration left to act on the
        # human's direction.  Using while True ensures the next iteration always
        # executes after human review.
        while True:
            try:
                result = self._run_sprint_work(sprint, attempt)

                if result["success"]:
                    sha = self.commit_sprint(sprint_id, objective)
                    gitea_url = self.get_gitea_url(sprint_id)
                    self._update_sprint_status(sprint_id, "complete", sha=sha, gitea_url=gitea_url)
                    self._update_ralph_md(sprint, result, sha, gitea_url)
                    self.emit_log(f"✅ Sprint {sprint_id} complete: {sha}")
                    return True

                yellow_cards += 1
                self._update_sprint_status(sprint_id, "yellow")
                self.emit_message("flag", f"🟡 **Yellow Card #{yellow_cards}** — Sprint {sprint_id}\n\n{result.get('error', 'Sprint did not meet acceptance criteria.')}")

                if yellow_cards >= 2:
                    self._update_sprint_status(sprint_id, "red")
                    self.set_status("red", "running")
                    learnings = result.get('learnings', 'None')
                    learnings = (learnings[:200] + "...") if len(learnings) > 200 else learnings
                    review_msg = (
                        f"🔴 **Human Review Required** — Sprint {sprint_id} has failed twice.\n\n"
                        f"**Issue:** {result.get('error')}\n\n"
                        f"**Learnings so far:** {learnings}\n\n"
                        f"Type **skip** to skip this sprint, or provide direction to retry."
                    )
                    direction = self.pause_for_input(review_msg)
                    if direction.strip().lower() == "skip":
                        self.emit_log(f"Sprint {sprint_id} skipped by user")
                        self._update_sprint_status(sprint_id, "yellow")
                        self.set_status("yellow", "running")
                        return False
                    yellow_cards = 0
                    sprint["human_direction"] = direction
                    self.set_status("green", "running")

            except Exception as e:
                self.emit_log(f"Sprint {sprint_id} exception: {e}", level="error")
                yellow_cards += 1
                if yellow_cards >= 2:
                    direction = self.pause_for_input(
                        f"🔴 **Sprint {sprint_id} errored twice:** `{e}`\n\n"
                        f"Type **skip** to skip this sprint, or provide direction to retry."
                    )
                    if direction.strip().lower() == "skip":
                        self.emit_log(f"Sprint {sprint_id} skipped by user after exception")
                        self._update_sprint_status(sprint_id, "yellow")
                        self.set_status("yellow", "running")
                        return False
                    yellow_cards = 0
                    sprint["human_direction"] = direction
                    self.set_status("green", "running")

            attempt += 1

    # ── File extraction ───────────────────────────────────────────────────────

    def _write_workspace_file(self, filename: str, content: str):
        """Write content to a file under WORKSPACE, creating parent dirs. Rejects unsafe paths."""
        safe = Path(filename)
        if safe.is_absolute() or ".." in safe.parts:
            log.warning(f"Skipping unsafe file path: {filename}")
            return
        target = self.workspace / safe
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        log.info(f"Wrote file: {filename} ({len(content)} bytes)")
        self.emit_log(f"📄 Wrote: {filename} ({len(content)} bytes)")

    def _extract_files_from_response(self, text: str) -> list:
        """
        Parse Claude's response for file blocks and write them to WORKSPACE_PATH.

        Supported formats:

          ### FILE: path/to/file.ext
          ```<optional lang>
          <content>
          ```

          ```lang (filename: path/to/file.ext)
          <content>
          ```

        Returns list of relative file paths written.
        """
        written = []

        # ── Format 1: ### FILE: header ────────────────────────────────────────
        # Remove the summary block (wherever it sits) so it doesn't bleed into file content
        body = re.sub(r'```summary.*?```', '', text, flags=re.DOTALL)

        parts = re.split(r"^### FILE:\s*(.+)$", body, flags=re.MULTILINE)
        # parts = [preamble, filename1, content1, filename2, content2, ...]
        i = 1
        while i + 1 <= len(parts) - 1:
            filename = parts[i].strip()
            raw_content = parts[i + 1]

            # Strip leading/trailing whitespace
            raw_content = raw_content.strip()

            # If content is wrapped in a code fence, peel it off
            if raw_content.startswith("```"):
                lines = raw_content.split("\n")
                lines = lines[1:]  # drop ``` opening line
                # drop trailing ```
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                content = "\n".join(lines)
            else:
                content = raw_content

            if filename and content.strip():
                self._write_workspace_file(filename, content)
                written.append(filename)

            i += 2

        # ── Format 2: ```lang (filename: path) ───────────────────────────────
        fence_fn_re = re.compile(
            r"```\w*\s+\(filename:\s*([^\)]+)\)\n(.*?)```",
            re.DOTALL,
        )
        for match in fence_fn_re.finditer(text):
            filename = match.group(1).strip()
            content = match.group(2)
            if filename not in written and content.strip():
                self._write_workspace_file(filename, content)
                written.append(filename)

        return written

    def _run_sprint_work(self, sprint: dict, attempt: int) -> dict:
        """Ask Claude to execute the sprint work."""
        ralph_context = self.read_ralph_md()
        project       = self.read_project_yaml()
        scope         = project.get("project", {}).get("scope_boundaries", [])

        attempt_note = ""
        if attempt > 0:
            attempt_note = (
                f"\n\n⚠️ This is retry attempt {attempt}. Previous attempt failed. Apply learnings and try a different approach."
                "\n\nPREVIOUS ATTEMPT FAILED: You did not include a ```summary block. "
                "This is mandatory. Write the ```summary block FIRST before any files. "
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
3. Write your ```summary block FIRST before any file contents
4. Then output every file using the FILE block format below

IMPORTANT: Always write your ```summary block FIRST before any file contents.
Structure your response like this:

```summary
{{
  "success": true,
  "deliverable": "description of what was built",
  "learnings": "what worked well",
  "scope_creep_detected": false,
  "error": null
}}
```

Then write your files using ### FILE: filename format.

FILE OUTPUT FORMAT — you MUST use this exact format for every file you create or modify:

### FILE: path/to/filename.ext
```<language>
<complete file contents here>
```

Use this format for EVERY file. This is how your work gets written to disk.
Without this format your changes will be lost and the sprint will fail.

CRITICAL RULES:
- You have no ability to run bash commands or a terminal
- Do NOT write ```bash blocks — they will not be executed
- Write the COMPLETE file contents for every file — no truncation, no "..." placeholders
- You MUST write at least one ### FILE: block — sprints that produce no files fail
- You MUST include a ```summary block — without it the sprint fails
- The summary block must be valid JSON with keys: success, deliverable, learnings, scope_creep_detected, error
- If you cannot complete the objective write success: false in the summary with a clear error message
"""

        prompt = f"""Execute this sprint:

Sprint ID: {sprint['id']}
Title: {sprint['title']}
Objective: {sprint['objective']}
Acceptance Criteria: {json.dumps(sprint.get('acceptance_criteria', []))}
{attempt_note}

Start your response with the summary block, then write your files:

```summary
{{
  "success": true/false,
  "deliverable": "<what was produced>",
  "learnings": "<key learnings>",
  "scope_creep_detected": false,
  "error": null
}}
```

Then for each file you create or modify:

### FILE: path/to/file.ext
```language
<complete file contents>
```"""

        raw = self.chat(prompt, system=system, max_tokens=4096)

        # Extract and write files to workspace
        files_written = self._extract_files_from_response(raw)
        if files_written:
            self.emit_log(f"📁 {len(files_written)} file(s) written: {', '.join(files_written)}")
        else:
            self.emit_log("⚠️ No files extracted from sprint response", level="warning")

        # Extract summary block — search entire response so truncation doesn't hide it
        summary_match = re.search(r'```summary\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if summary_match:
            try:
                result = json.loads(summary_match.group(1))
            except json.JSONDecodeError as e:
                log.error(f"_run_sprint_work summary JSON parse failed: {e}. Raw: {summary_match.group(1)[:500]}")
                return {
                    "success": False,
                    "error": "Summary block was not valid JSON",
                    "learnings": "Agent returned a summary block but it could not be parsed as JSON. Will retry.",
                }

            # A sprint that claims success but wrote nothing to disk has failed
            if result.get("success") and not files_written:
                return {
                    "success": False,
                    "error": "Sprint claimed success but no files were written to disk.",
                    "learnings": (
                        "Agent must output files using the ### FILE: format. "
                        "No file blocks were detected in the response. Will retry with stricter instructions."
                    ),
                }

            # Static validation — run after files land on disk
            if result.get("success") and files_written:
                validation_errors = self._validate_sprint(files_written)
                if validation_errors:
                    return {
                        "success": False,
                        "error": "Static validation failed:\n" + "\n".join(f"• {e}" for e in validation_errors),
                        "learnings": "Fix the validation errors listed above before marking the sprint complete.",
                    }

            return result

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
            # Run smoke test before pausing for human review
            self.set_status("blue")
            smoke = self._smoke_test_milestone(current_idx)
            if smoke and not smoke.get("passed"):
                self.emit_log("Smoke test failed — running fix sprint before gate pause", level="warning")
                self._fix_from_smoke_test(smoke.get("error", "Unknown smoke test failure"))

            # Build gate message with smoke test outcome
            gate_msg = (
                f"🔵 **Milestone Gate: {prev_milestone['title']} Complete**\n\n"
                f"The previous milestone has been reached. Please review and choose:\n"
                f"- Type **accept** to proceed to {milestones[current_idx]['title']}\n"
                f"- Type **realign** followed by your feedback to adjust the plan"
            )
            if smoke and smoke.get("passed"):
                gate_msg += f"\n\n✅ **Smoke test passed** — app is running correctly."
            elif smoke and not smoke.get("passed"):
                gate_msg += f"\n\n⚠️ **Smoke test failed:** {smoke.get('error')}\nA fix sprint was attempted — please verify before accepting."

            response = self.pause_for_input(gate_msg)

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
            project_name = self.read_project_yaml().get("project", {}).get("name", "project")
            self._push_to_github(project_name)
        else:
            failed = [c for c in assessment["criteria"] if not c["met"]]
            self.set_status("red", "error")
            direction = self.pause_for_input(
                f"🔴 **DoD Assessment Failed**\n\n"
                f"Unmet criteria:\n" +
                "\n".join(f"- {c['criterion']}" for c in failed) +
                f"\n\nHow would you like to proceed?"
            )

    def _push_to_github(self, project_name: str):
        """Push workspace to GitHub if token and username are configured."""
        github_token    = os.getenv("GITHUB_TOKEN")
        github_username = os.getenv("GITHUB_USERNAME")
        github_org      = os.getenv("GITHUB_ORG")

        if not github_token or not github_username:
            self.emit_log("GitHub token/username not configured — skipping GitHub push")
            return

        owner      = github_org if github_org else github_username
        repo_name  = project_name.lower().replace(" ", "-")
        remote_url = f"https://{github_token}@github.com/{owner}/{repo_name}.git"
        branch     = os.getenv("DEFAULT_BRANCH", "main")

        try:
            repo = self.get_repo()
            if "origin" not in [r.name for r in repo.remotes]:
                repo.create_remote("origin", remote_url)
            else:
                repo.remotes.origin.set_url(remote_url)

            repo.remotes.origin.push(branch)
            github_url = f"https://github.com/{owner}/{repo_name}"
            self.emit_log(f"Pushed to GitHub: {github_url}")
            self.emit_message("system", f"✓ Pushed to GitHub: {github_url}")
        except Exception as e:
            log.warning(f"GitHub push failed: {e}")
            self.emit_log(f"⚠️ GitHub push failed: {e}", level="warning")
            self.emit_message("flag", f"⚠️ GitHub push failed: {e}")

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

    # ── Static validation ─────────────────────────────────────────────────────

    def _validate_sprint(self, files_written: list) -> list:
        """Run static analysis on files written during a sprint. Returns list of error strings."""
        errors = []
        workspace = self.workspace

        is_node   = (workspace / "package.json").exists()

        for filename in files_written:
            filepath = workspace / filename
            if not filepath.exists():
                errors.append(f"File reported written but does not exist: {filename}")
                continue

            # JS syntax check via node --check (skipped if node not installed in agent container)
            if filename.endswith(".js"):
                try:
                    result = subprocess.run(
                        ["node", "--check", str(filepath)],
                        capture_output=True, text=True
                    )
                    if result.returncode != 0:
                        errors.append(f"Syntax error in {filename}: {result.stderr.strip()}")
                except FileNotFoundError:
                    pass  # node not available in this environment

            # Python syntax check via py_compile
            if filename.endswith(".py"):
                try:
                    result = subprocess.run(
                        ["python", "-m", "py_compile", str(filepath)],
                        capture_output=True, text=True
                    )
                    if result.returncode != 0:
                        errors.append(f"Syntax error in {filename}: {result.stderr.strip()}")
                except FileNotFoundError:
                    pass  # python not on PATH in this environment

            # HTML — check that referenced script/link files exist
            if filename.endswith(".html"):
                content = filepath.read_text(encoding="utf-8", errors="replace")
                for match in re.finditer(r'<script[^>]+src=["\']([^"\']+)["\']', content):
                    ref = match.group(1)
                    if not ref.startswith("http") and not ref.startswith("//"):
                        ref_path = workspace / ref.lstrip("/").replace("/", os.sep)
                        if not ref_path.exists():
                            errors.append(f"Missing script in {filename}: {ref}")
                for match in re.finditer(r'<link[^>]+href=["\']([^"\']+)["\']', content):
                    ref = match.group(1)
                    if not ref.startswith("http") and not ref.startswith("//"):
                        ref_path = workspace / ref.lstrip("/").replace("/", os.sep)
                        if not ref_path.exists():
                            errors.append(f"Missing link in {filename}: {ref}")

            # Node.js — check relative require() targets exist
            if is_node and filename.endswith(".js"):
                content = filepath.read_text(encoding="utf-8", errors="replace")
                for match in re.finditer(r"""require\(['"](\.[^'"]+)['"]\)""", content):
                    ref = match.group(1)
                    base = filepath.parent
                    resolved = (base / ref).resolve()
                    if not resolved.exists() and not resolved.with_suffix(".js").exists():
                        errors.append(f"Unresolved require in {filename}: {ref}")

        if errors:
            self.emit_message("flag",
                f"🔍 Validation: {len(errors)} error(s) found\n" +
                "\n".join(f"  • {e}" for e in errors))
        else:
            self.emit_message("system",
                f"🔍 Validation passed — {len(files_written)} file(s) checked")

        return errors

    # ── Docker smoke test ─────────────────────────────────────────────────────

    def _smoke_test_milestone(self, milestone_num: int) -> Optional[dict]:
        """Spin up the project in Docker and verify it responds on HTTP. Returns result dict."""
        self.emit_message("system", f"🐳 Running milestone {milestone_num} smoke test...")
        workspace = str(self.workspace)

        # Detect project type
        if (self.workspace / "package.json").exists():
            image = "node:20-alpine"
            with open(self.workspace / "package.json") as f:
                pkg = json.load(f)
            start_cmd = pkg.get("scripts", {}).get("start", "node server.js")
            setup_cmd = f"cd /app && npm install --silent && {start_cmd}"
            port = 3000
            project_type = "node"
        elif (self.workspace / "requirements.txt").exists():
            image = "python:3.12-slim"
            setup_cmd = "cd /app && pip install -r requirements.txt -q && python app.py"
            port = 5000
            project_type = "python"
        elif (self.workspace / "index.html").exists() or (self.workspace / "public" / "index.html").exists():
            image = "nginx:alpine"
            setup_cmd = None
            port = 80
            project_type = "static"
        else:
            log.warning("Could not detect project type for smoke test — skipping")
            return None

        container = None
        try:
            import docker as docker_sdk
            client = docker_sdk.from_env()

            # Pull image if not cached
            try:
                client.images.get(image)
            except docker_sdk.errors.ImageNotFound:
                self.emit_log(f"Pulling {image} for smoke test...")
                client.images.pull(image)

            if project_type == "static":
                static_dir = str(self.workspace / "public") if (self.workspace / "public").exists() else workspace
                container = client.containers.run(
                    image, detach=True, remove=False,
                    volumes={static_dir: {"bind": "/usr/share/nginx/html", "mode": "ro"}},
                    ports={f"{port}/tcp": None},
                )
            else:
                container = client.containers.run(
                    image, command=["sh", "-c", setup_cmd],
                    detach=True, remove=False,
                    volumes={workspace: {"bind": "/app", "mode": "rw"}},
                    ports={f"{port}/tcp": None},
                    environment={"PORT": str(port), "NODE_ENV": "test"},
                )

            # Wait up to 30s for port binding
            host_port = None
            for _ in range(30):
                time.sleep(1)
                container.reload()
                if container.status == "exited":
                    logs = container.logs(tail=20).decode(errors="replace")
                    raise Exception(f"Container exited early.\n{logs}")
                bindings = container.ports.get(f"{port}/tcp")
                if bindings:
                    host_port = bindings[0]["HostPort"]
                    break

            if not host_port:
                raise Exception("App did not bind to port within 30s")

            # HTTP health check — up to 10 attempts
            for _ in range(10):
                try:
                    resp = urllib.request.urlopen(f"http://localhost:{host_port}", timeout=3)
                    if resp.status == 200:
                        self.emit_message("system", f"✅ Smoke test passed — app responded on port {host_port}")
                        return {"passed": True, "port": host_port}
                except Exception:
                    time.sleep(1)

            raise Exception("App did not respond to HTTP request within 10s")

        except Exception as e:
            error_msg = str(e)
            log.error(f"Smoke test failed: {error_msg}")
            self.emit_message("flag", f"⚠️ Smoke test failed: {error_msg}")
            return {"passed": False, "error": error_msg}

        finally:
            if container:
                try:
                    container.stop(timeout=3)
                    container.remove()
                except Exception:
                    pass

    def _run_custom_sprint(self, objective: str, custom_prompt: str) -> dict:
        """Lightweight sprint executor for fix sprints — takes a prompt directly."""
        raw = self.chat(custom_prompt, system=(
            "You are Ralph, an AI development agent. Fix the reported issue. "
            "Write your ```summary block FIRST, then output corrected files using ### FILE: format."
        ), max_tokens=4096)

        files_written = self._extract_files_from_response(raw)
        if files_written:
            self.emit_log(f"📁 Fix sprint wrote {len(files_written)} file(s): {', '.join(files_written)}")

        summary_match = re.search(r'```summary\s*(\{.*?\})\s*```', raw, re.DOTALL)
        if summary_match:
            try:
                return json.loads(summary_match.group(1))
            except json.JSONDecodeError:
                pass

        return {"success": False, "error": "No parseable summary from fix sprint"}

    def _fix_from_smoke_test(self, error: str):
        """Run a targeted fix sprint when the smoke test fails at a milestone gate."""
        self.emit_log("Running smoke-test fix sprint...", level="warning")
        prompt = f"""The project failed a smoke test with this error:

{error}

Diagnose and fix the issue. Common causes:
- Missing files referenced in HTML or JS
- Wrong entry point in package.json
- Port not being listened on correctly
- Missing dependencies in package.json or requirements.txt
- CORS issues with external APIs (proxy through server instead)

Fix the issue and output corrected files using ### FILE: format.
Start with a ```summary block."""

        result = self._run_custom_sprint("Fix: smoke test failure", prompt)
        if result.get("success"):
            self.emit_log("Smoke test fix sprint succeeded")
            sha = self.commit_sprint("smoke-fix", "fix: smoke test failures at milestone gate")
            self.emit_log(f"Fix committed: {sha}")
        else:
            log.warning(f"Smoke test fix sprint failed: {result.get('error')}")
            self.emit_message("flag", f"⚠️ Automatic fix sprint did not fully resolve the issue. Manual review recommended.")

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
