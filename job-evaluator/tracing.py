"""Record what happens in a run, one event per step, as a trace file.

The page (D15) replays traces; it shows only what was recorded here.
Event format: docs/SPEC.md, "Trace format". Decision: D24.

    rec = Recorder(scenario="clean")
    final = run_agent(job, recorder=rec)
    path = rec.write()            # traces/clean-20261113-150211.json

run_agent(job, recorder=None) uses NullRecorder, which records nothing,
so the agent behaves exactly the same with or without a trace.

Never recorded: the API client, request headers, or environment variables.
write() refuses to write a file that contains "sk-ant" anywhere.
"""

import datetime
import json
import os
import subprocess

import code_refs

TRACE_VERSION = 1
SECRET_MARKER = "sk-ant"

# Every event has every one of these keys (null when it doesn't apply).
EVENT_KEYS = ("id", "seq", "pass", "step_id", "actor", "crossing", "payload",
              "messages_before", "messages_after", "code", "parent", "tokens",
              "guard", "injected")

CROSSING_KINDS = ("api_request", "api_response", "tool_call", "tool_result",
                  "inner_api_request", "inner_api_response")

# How a run ended → the step that shows it.
END_STEPS = {"end_turn": "answer_returned",
             "max_tokens": "reply_cut_off",
             "pass_cap": "pass_cap",
             "api_error": "api_call_failed",
             "no_text": "no_final_answer",
             "unexpected_stop": "unexpected_stop"}


def to_json(obj):
    """Turn SDK objects (content blocks, messages) into plain JSON data.

    SDK blocks use model_dump(), so the trace holds exactly what the API
    returned. Thinking blocks keep their text but drop `signature` (an
    opaque string the page can't use); redacted thinking drops its data.
    """
    if hasattr(obj, "model_dump"):
        data = obj.model_dump(mode="json", exclude_none=True)
    elif isinstance(obj, dict):
        data = {k: to_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [to_json(v) for v in obj]
    elif obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    elif hasattr(obj, "__dict__"):          # e.g. SimpleNamespace test fakes
        data = {k: to_json(v) for k, v in vars(obj).items()}
    else:
        return str(obj)
    if isinstance(data, dict):
        if data.get("type") == "thinking":
            data.pop("signature", None)
        elif data.get("type") == "redacted_thinking":
            data.pop("data", None)
    return data


# Files record.py writes itself. Changes to them don't change the code that
# ran, so they don't make a run "dirty" (#99): otherwise every scenario after
# the first in `record.py --all` was marked dirty by the recordings before it.
# ":!path" is git's pathspec for "everything except this".
NOT_CODE = [":!recordings", ":!docs/SCENARIOS.md"]


def _git_commit(here=None):
    """(short commit, has uncommitted changes) for the code that ran, or
    (None, None) outside a git checkout. here: the folder to check, which
    defaults to the one this file is in (job-evaluator/)."""
    here = here or os.path.dirname(os.path.abspath(__file__))
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=here,
                                capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", ".", *NOT_CODE], cwd=here,
                               capture_output=True, text=True, check=True).stdout.strip()
        return commit, bool(dirty)
    except (OSError, subprocess.CalledProcessError):
        return None, None


class NullRecorder:
    """Records nothing. Used when run_agent gets no recorder."""

    pass_number = 0

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


# The recorder for the run in progress. run_agent sets it, so code inside a
# tool (evaluate_job's own Claude call) can record without a new parameter.
_active = NullRecorder()


def activate(recorder):
    global _active
    _active = recorder


def active():
    return _active


class Recorder:
    """Collects events for one run and writes them to a trace file."""

    def __init__(self, scenario="adhoc", source=None, now=None, git=None):
        self.scenario = scenario
        # Read agent.py once, so every code reference matches the code
        # that actually ran.
        self.source = source if source is not None else code_refs.load_source()
        self._now = now or (lambda: datetime.datetime.now(datetime.timezone.utc))
        self.started = self._now()
        self.git_commit, self.git_dirty = git if git is not None else _git_commit()
        self.events = []
        self.pass_number = 0          # 0 = before the loop starts
        self.run = {}                 # model, limits, system, tools
        self.result = None
        self._refs = {}
        self._call = None             # event id of the tool_call in progress
        self._tool_exists = None
        # Injected faults (faults.py, #46). A tool fault opens a short scope:
        # its effects (caught guard, error result, results_back) are marked
        # injected; Claude's later reactions are real and are not. A limit
        # fault marks every event made under the lowered limit.
        self.fault = None
        self._inject_scope = False
        self._inject_tokens = False
        self._inject_passes = False

    # --- building events ----------------------------------------------

    def _code(self, step_id):
        if step_id not in self._refs:
            self._refs[step_id] = code_refs.code_ref(step_id, self.source)
        return self._refs[step_id]

    def event(self, step_id, actor, kind=None, frm=None, to=None, payload=None,
              before=None, after=None, tokens=None, guard=None, parent=None,
              injected=False):
        """Add one event. Data is converted to JSON immediately, so later
        changes to `messages` can't alter an event already recorded."""
        seq = len(self.events) + 1
        event = {
            "id": f"e{seq}",
            "seq": seq,
            "pass": self.pass_number,
            "step_id": step_id,
            "actor": actor,
            "crossing": {"from": frm, "to": to, "kind": kind} if kind else None,
            "payload": to_json(payload),
            "messages_before": to_json(before),
            "messages_after": to_json(after),
            "code": self._code(step_id),
            "parent": parent,
            "tokens": tokens,
            "guard": guard,
            "injected": bool(injected or self._inject_scope),
        }
        self.events.append(event)
        return event["id"]

    # --- one method per kind of step (called from run_agent) ------------

    def start(self, job_text, model, max_tokens, max_passes, system, tools, fault=None):
        self.fault = fault
        self.run = {"model": model, "max_tokens": max_tokens,
                    "max_passes": max_passes, "system": system, "tools": tools}
        return self.event("agent_starts", "python", payload={"job_text": job_text})

    def messages_changed(self, step_id, before, after):
        event_id = self.event(step_id, "python", before=before, after=after)
        if step_id == "results_back":
            self._inject_scope = False    # the fault's error is now in the conversation
        return event_id

    # --- injected faults (faults.py, #46) ----------------------------------

    def fault_injected(self, step_id, change):
        """Record that the run's fault just changed something, and what.
        Opens the injected scope for a tool fault."""
        self._inject_scope = True
        return self.event(step_id, "python", payload={"fault": self.fault, **change},
                          parent=self._call, injected=True)

    def limits_injected(self, normal_passes, passes, normal_tokens, tokens):
        """At the start of a run: record any limit the fault lowered."""
        if passes != normal_passes:
            self._inject_passes = True
            self.event("send_to_claude", "python", injected=True,
                       payload={"fault": self.fault,
                                "max_passes": {"normal": normal_passes, "injected": passes}})
        if tokens != normal_tokens:
            self._inject_tokens = True
            self.event("send_to_claude", "python", injected=True,
                       payload={"fault": self.fault,
                                "max_tokens": {"normal": normal_tokens, "injected": tokens}})

    def api_request(self, messages):
        payload = {"model": self.run["model"], "max_tokens": self.run["max_tokens"],
                   "system": self.run["system"],
                   "tools": [t["name"] for t in self.run["tools"]],
                   "messages": messages}
        return self.event("send_to_claude", "python", "api_request", "python", "claude",
                          payload=payload, injected=self._inject_tokens)

    def api_response(self, response):
        # The call returned a reply, so the API-call guard didn't catch
        # anything. (A failed call is recorded by end("api_error").)
        self.guard("send_to_claude", "api_call_succeeded",
                   "client.messages.create returned a reply", None, False,
                   injected=self._inject_tokens)
        usage = getattr(response, "usage", None)
        tokens = ({"input": usage.input_tokens, "output": usage.output_tokens}
                  if usage is not None else None)
        return self.event("claude_decides", "claude", "api_response", "claude", "python",
                          payload={"stop_reason": response.stop_reason,
                                   "content": response.content},
                          tokens=tokens, injected=self._inject_tokens)

    # --- guards -----------------------------------------------------------
    # Every check the loop or a tool makes records a guard event, whether or
    # not it caught anything. `caught` is true only when something went
    # wrong; then the event uses the error-case step (STEPS.md, E1–E9).

    def guard(self, step_id, name, checked, value, caught,
              action=None, message=None, parent=None, injected=False):
        return self.event(step_id, "python", parent=parent, injected=injected,
                          guard={"name": name, "checked": checked, "value": value,
                                 "caught": caught, "action": action, "message": message})

    def pass_started(self, number):
        self.pass_number = number
        limit = self.run["max_passes"]
        return self.guard("send_to_claude", "pass_count", f"pass <= MAX_PASSES ({limit})",
                          number, False, injected=self._inject_passes)

    def reply_checked(self, stop_reason):
        """The stop_reason check, and the max_tokens check when the code
        reaches it. A cut-off reply is recorded by end("max_tokens")."""
        # Step 9 (claude_done) is this same check on the pass where Claude
        # finishes (decision A on #1).
        finished = stop_reason == "end_turn"
        self.guard("claude_done" if finished else "check_reply", "stop_reason",
                   'stop_reason == "end_turn"', stop_reason, False,
                   action="finish" if finished else None, injected=self._inject_tokens)
        if not finished and stop_reason != "max_tokens":
            self.guard("check_reply", "max_tokens", 'stop_reason == "max_tokens"',
                       stop_reason, False, injected=self._inject_tokens)
            # Only tool_use goes on to the tools; anything else is recorded
            # by end("unexpected_stop") as the caught guard (#21).
            if stop_reason == "tool_use":
                self.guard("check_reply", "stop_reason_known", 'stop_reason == "tool_use"',
                           stop_reason, False, injected=self._inject_tokens)

    def tool_checked(self, tool_block):
        """Before dispatch: does the tool exist? If so, record the call.
        (An unknown tool is recorded by tool_finished, once its error exists.)"""
        names = [t["name"] for t in self.run["tools"]]
        self._tool_exists = tool_block.name in names
        self._call = None
        if self._tool_exists:
            self.guard("run_tools", "tool_exists", "tool name is defined",
                       tool_block.name, False)
            self._call = self.event(
                "run_tools", "python", "tool_call", "python", "tool",
                payload={"tool": tool_block.name, "tool_use_id": tool_block.id,
                         "arguments": tool_block.input})

    def tool_finished(self, tool_block, outcome):
        failed = bool(outcome.get("is_error"))
        payload = {"tool": tool_block.name, "tool_use_id": tool_block.id,
                   "is_error": failed, "content": outcome["content"]}
        if not self._tool_exists:
            # No tool ran: Python itself answers with the error.
            self.guard("unknown_tool", "tool_exists", "tool name is defined",
                       tool_block.name, True, action="error_sent_to_claude",
                       message=outcome["content"])
            return self.event("run_tools", "python", payload=payload)
        self.guard("tool_failed" if failed else "run_tools", "tool_succeeded",
                   f"{tool_block.name} returned without raising",
                   outcome["content"].split(":")[0] if failed else None, failed,
                   action="error_sent_to_claude" if failed else None,
                   message=outcome["content"] if failed else None)
        self._call = None
        return self.event("run_tools", "tool", "tool_result", "tool", "python",
                          payload=payload)

    # --- evaluate_job's own Claude call (parent = its tool_call) -----------

    def inner_api_request(self, system, messages):
        payload = {"model": self.run["model"], "max_tokens": self.run["max_tokens"],
                   "system": system, "tools": [], "messages": messages}
        return self.event("inner_grader", "tool", "inner_api_request", "tool", "claude",
                          payload=payload, parent=self._call)

    def inner_api_response(self, response):
        usage = getattr(response, "usage", None)
        tokens = ({"input": usage.input_tokens, "output": usage.output_tokens}
                  if usage is not None else None)
        return self.event("inner_grader", "claude", "inner_api_response", "claude", "tool",
                          payload={"stop_reason": response.stop_reason,
                                   "content": response.content},
                          tokens=tokens, parent=self._call)

    # --- rules (#26, D28) ------------------------------------------------
    # A rule applies one of Justin's decisions; it isn't a guard. Failing it
    # is the agent working as intended, so it's a normal event (no `guard`,
    # no `caught`) at a normal step, with the outcome in the payload.

    def rule_checked(self, rule):
        """One hard rule in evaluate_job, before the rating call. `outcome`
        is passed, failed or skipped; a skipped rule's value is what it
        couldn't read (e.g. "competitive")."""
        return self.event("hard_screen", "python", parent=self._call,
                          payload={"rule": rule["name"], "checked": rule["checked"],
                                   "value": rule["value"], "outcome": rule["outcome"],
                                   "note": rule["note"]})

    def company_looked_up(self, company, role_level, result):
        """research_company's lookup in the stored company data (#65): what
        Claude asked for and what was found. A company that isn't on file is
        a normal answer (found: false), not a caught guard."""
        return self.event("research_company", "tool", parent=self._call,
                          payload={"company": company, "role_level": role_level,
                                   "found": result["found"],
                                   "typical_base_for_level": result.get("typical_base_for_level"),
                                   "source": result["source"]})

    def grader_checked(self, stop_reason):
        caught = stop_reason == "max_tokens"
        message = (f"The grader's reply was cut off (hit the max_tokens limit "
                   f"of {self.run['max_tokens']}).") if caught else None
        return self.guard("grader_cut_off" if caught else "inner_grader", "max_tokens",
                          'stop_reason == "max_tokens"', stop_reason, caught,
                          action="error_raised" if caught else None,
                          message=message, parent=self._call)

    def grade_checked(self, problem):
        caught = problem is not None
        return self.guard("invalid_grade" if caught else "inner_grader", "grade_valid",
                          "rating is one of the three and reasons is a list of strings",
                          problem, caught, action="error_raised" if caught else None,
                          message=problem, parent=self._call)

    # --- the end of the run ---------------------------------------------

    def end(self, ended_by, text, value=None):
        if ended_by == "api_error":
            self.guard("api_call_failed", "api_call_succeeded",
                       "client.messages.create returned a reply", value, True,
                       action="run_stopped", message=text)
        elif ended_by in ("end_turn", "no_text"):
            # Claude finished: did it write a final answer?
            missing = ended_by == "no_text"
            self.guard("no_final_answer" if missing else "answer_returned",
                       "final_text_present", "the reply has a text block",
                       None if missing else "text", missing,
                       action="run_stopped" if missing else None,
                       message=text if missing else None)
        elif ended_by == "max_tokens":
            self.guard("reply_cut_off", "max_tokens", 'stop_reason == "max_tokens"',
                       "max_tokens", True, action="run_stopped", message=text,
                       injected=self._inject_tokens)
        elif ended_by == "unexpected_stop":
            self.guard("unexpected_stop", "stop_reason_known", 'stop_reason == "tool_use"',
                       value, True, action="run_stopped", message=text,
                       injected=self._inject_tokens)
        elif ended_by == "pass_cap":
            limit = self.run["max_passes"]
            self.guard("pass_cap", "pass_count", f"pass <= MAX_PASSES ({limit})",
                       limit + 1, True, action="run_stopped", message=text,
                       injected=self._inject_passes)
        caused_by_fault = ((ended_by == "max_tokens" and self._inject_tokens)
                           or (ended_by == "pass_cap" and self._inject_passes))
        self.result = {"ended_by": ended_by, "text": text}
        activate(NullRecorder())
        return self.event(END_STEPS[ended_by], "python", payload=self.result,
                          injected=caused_by_fault)

    # --- output -----------------------------------------------------------

    def to_dict(self):
        return {
            "trace_version": TRACE_VERSION,
            "scenario": self.scenario,
            "started_at": self.started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_commit": self.git_commit,
            "git_dirty": self.git_dirty,
            "model": self.run.get("model"),
            "limits": {"max_passes": self.run.get("max_passes"),
                       "max_tokens": self.run.get("max_tokens")},
            "fault": self.fault,
            "tools": to_json(self.run.get("tools")),
            "events": self.events,
            "result": self.result,
        }

    def write(self, directory=None):
        """Write traces/<scenario>-<timestamp>.json and return its path.

        Refuses (raises ValueError, writes nothing) if "sk-ant" appears
        anywhere in the trace.
        """
        if directory is None:
            directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), "traces")
        stamp = self.started.strftime("%Y%m%d-%H%M%S")
        return self.write_to(os.path.join(directory, f"{self.scenario}-{stamp}.json"))

    def write_to(self, path, extra=None):
        """Write the trace to exactly `path` (replacing any file there), with
        `extra` keys added at the top level (record.py adds its check, #53).
        Same refusal as write() if "sk-ant" appears anywhere."""
        text = json.dumps({**self.to_dict(), **(extra or {})}, indent=2, ensure_ascii=False)
        if SECRET_MARKER in text:
            raise ValueError(f"trace contains {SECRET_MARKER!r}; not writing it")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        return path
