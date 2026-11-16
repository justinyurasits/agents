"""Find the code a step points to, from `# STEP: <step_id>` markers.

A marker is a comment on the line directly above the code it labels:

        # STEP: send_to_claude
        response = client.messages.create(
            ...
        )

`code_ref("send_to_claude", source)` returns where that code is *right now*:
its line number and the whole statement (a multi-line call, or an `if` /
`for` / `except` block with its body). Line numbers are never written down
anywhere; they're looked up from the source each time, so editing agent.py
can't make a reference go stale.

Pure Python, no API calls: it only reads source text.
"""

import ast
import os
import re
import textwrap

AGENT_FILE = "agent.py"
AGENT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), AGENT_FILE)

MARKER = re.compile(r"^\s*# STEP: ([a-z][a-z0-9_]*)\s*$")

# Steps that share another step's code (decision A on #1): step 9 is the
# stop-reason check from step 5, on the pass where Claude says end_turn.
SHARED = {"claude_done": "check_reply"}

# Steps with no code at all: Claude decides on Anthropic's servers.
NO_CODE = {"claude_decides"}


class MarkerError(Exception):
    """A marker is missing, duplicated, or not directly above code."""


def load_source(path=AGENT_PATH):
    """Read agent.py once, so every reference in a run comes from the same
    version of the code."""
    with open(path, encoding="utf-8") as f:
        return f.read()


def find_markers(source):
    """Map each step_id to the line number of its marker comment.

    Raises MarkerError if the same step_id is marked twice.
    """
    markers = {}
    for number, text in enumerate(source.splitlines(), start=1):
        match = MARKER.match(text)
        if not match:
            continue
        step_id = match.group(1)
        if step_id in markers:
            raise MarkerError(f"marker {step_id!r} appears twice "
                              f"(lines {markers[step_id]} and {number})")
        markers[step_id] = number
    return markers


def _statement_at(tree, line):
    """The outermost statement (or except clause) that starts on `line`."""
    found = [node for node in ast.walk(tree)
             if isinstance(node, (ast.stmt, ast.excepthandler))
             and node.lineno == line]
    return max(found, key=lambda n: n.end_lineno, default=None)


def code_ref(step_id, source, file=AGENT_FILE):
    """Where a step's code is: {file, marker, line, lines}, or None for a
    step with no code (claude_decides).

    `marker` is the marker actually used (claude_done uses check_reply's).
    `line` is the first line of the code, 1-based. `lines` is the full
    statement, with its shared indentation removed.

    Raises MarkerError if the marker is missing or isn't directly above a
    statement.
    """
    if step_id in NO_CODE:
        return None
    marker = SHARED.get(step_id, step_id)

    markers = find_markers(source)
    if marker not in markers:
        raise MarkerError(f"no '# STEP: {marker}' marker in {file}")

    line = markers[marker] + 1
    node = _statement_at(ast.parse(source), line)
    if node is None:
        raise MarkerError(f"marker {marker!r} on line {markers[marker]} "
                          f"isn't directly above a statement")

    raw = source.splitlines()[node.lineno - 1:node.end_lineno]
    lines = textwrap.dedent("\n".join(raw)).split("\n")
    return {"file": file, "marker": marker, "line": node.lineno, "lines": lines}


# The terminal (#120): claude_decides has no code of its own, but its lines
# describe the reply that send_to_claude's call just returned, so they point
# at that call.
TERMINAL_SHARED = {"claude_decides": "send_to_claude"}


def terminal_labels(source, file=AGENT_FILE):
    """The label each terminal line starts with, by step id, e.g.
    {"send_to_claude": "[send_to_claude agent.py:<line>]", ...}.

    The number is the first line of the step's code (code_ref's `line`, just
    below its marker), looked up from `source` each time, so it's never
    typed anywhere. `file:line` is the form VS Code's terminal makes
    clickable.
    """
    labels = {}
    for step_id in [*find_markers(source), *SHARED, *TERMINAL_SHARED]:
        ref = code_ref(TERMINAL_SHARED.get(step_id, step_id), source, file)
        labels[step_id] = f"[{step_id} {ref['file']}:{ref['line']}]"
    return labels
