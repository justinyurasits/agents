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
             "pass_cap": "pass_cap"}


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


def _git_commit():
    """(short commit, has uncommitted changes) for the code that ran, or
    (None, None) outside a git checkout."""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=here,
                                capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=here,
                               capture_output=True, text=True, check=True).stdout.strip()
        return commit, bool(dirty)
    except (OSError, subprocess.CalledProcessError):
        return None, None


class NullRecorder:
    """Records nothing. Used when run_agent gets no recorder."""

    pass_number = 0

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


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

    # --- building events ----------------------------------------------

    def _code(self, step_id):
        if step_id not in self._refs:
            self._refs[step_id] = code_refs.code_ref(step_id, self.source)
        return self._refs[step_id]

    def event(self, step_id, actor, kind=None, frm=None, to=None, payload=None,
              before=None, after=None, tokens=None, guard=None, parent=None):
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
            "injected": False,
        }
        self.events.append(event)
        return event["id"]

    # --- one method per kind of step (called from run_agent) ------------

    def start(self, job_text, model, max_tokens, max_passes, system, tools):
        self.run = {"model": model, "max_tokens": max_tokens,
                    "max_passes": max_passes, "system": system, "tools": tools}
        return self.event("agent_starts", "python", payload={"job_text": job_text})

    def messages_changed(self, step_id, before, after):
        return self.event(step_id, "python", before=before, after=after)

    def api_request(self, messages):
        payload = {"model": self.run["model"], "max_tokens": self.run["max_tokens"],
                   "system": self.run["system"],
                   "tools": [t["name"] for t in self.run["tools"]],
                   "messages": messages}
        return self.event("send_to_claude", "python", "api_request", "python", "claude",
                          payload=payload)

    def api_response(self, response):
        usage = getattr(response, "usage", None)
        tokens = ({"input": usage.input_tokens, "output": usage.output_tokens}
                  if usage is not None else None)
        return self.event("claude_decides", "claude", "api_response", "claude", "python",
                          payload={"stop_reason": response.stop_reason,
                                   "content": response.content},
                          tokens=tokens)

    def reply_checked(self, stop_reason):
        # Step 9 (claude_done) is this same check on the pass where Claude
        # finishes (decision A on #1).
        step_id = "claude_done" if stop_reason == "end_turn" else "check_reply"
        return self.event(step_id, "python", payload={"stop_reason": stop_reason})

    def tool_call(self, tool_block):
        return self.event("run_tools", "python", "tool_call", "python", "tool",
                          payload={"tool": tool_block.name, "tool_use_id": tool_block.id,
                                   "arguments": tool_block.input})

    def tool_result(self, tool_block, outcome):
        return self.event("run_tools", "tool", "tool_result", "tool", "python",
                          payload={"tool": tool_block.name, "tool_use_id": tool_block.id,
                                   "is_error": bool(outcome.get("is_error")),
                                   "content": outcome["content"]})

    def end(self, ended_by, text):
        self.result = {"ended_by": ended_by, "text": text}
        return self.event(END_STEPS[ended_by], "python", payload=self.result)

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
            "tools": to_json(self.run.get("tools")),
            "events": self.events,
            "result": self.result,
        }

    def write(self, directory=None):
        """Write traces/<scenario>-<timestamp>.json and return its path.

        Refuses (raises ValueError, writes nothing) if "sk-ant" appears
        anywhere in the trace.
        """
        text = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
        if SECRET_MARKER in text:
            raise ValueError(f"trace contains {SECRET_MARKER!r}; not writing it")
        if directory is None:
            directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), "traces")
        os.makedirs(directory, exist_ok=True)
        stamp = self.started.strftime("%Y%m%d-%H%M%S")
        path = os.path.join(directory, f"{self.scenario}-{stamp}.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        return path
