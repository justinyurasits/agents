"""Build site/steps.json from docs/STEPS.md, so the page's explanations have
one source (#57).

    python build_steps.py

STEPS.md is the only place a step's title and explanation are written. This
script reads it and writes the same text as JSON for the page to load. Edit
STEPS.md, then rerun this; never edit steps.json by hand. A test fails if the
two ever disagree.

What it reads, for each step in STEPS.md:

    ### 7. Python runs the tool Claude asked for      <- number and title

    Step id: `run_tools`                              <- the key in steps.json

    Python finds each tool request in Claude's ...    <- the explanation:
    function with the details Claude filled in. ...      every line up to
    Code: `# STEP: run_tools` in agent.py (...)       <- "Code:" (not shown)

What it writes:

    {"source": "docs/STEPS.md", "steps": {
        "run_tools": {"number": "7", "title": "Python runs the tool Claude asked for",
                      "text": "Python finds each tool request ...", "error": false}, ...}}

"error" is true for the steps under "When something goes wrong" (E1, E2, ...).

It also reads the one-line explanation of each guard's check, from the
"Checks" section at the end of STEPS.md:

    - `pass_count`: Checks this run hasn't hit the 10-pass limit.

and writes them as "checks": {"pass_count": "Checks this run ..."}. The page
shows that line when a check passes (a passing check isn't a step).
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS_MD = os.path.join(HERE, "docs", "STEPS.md")
STEPS_JSON = os.path.join(HERE, "site", "steps.json")

# "### 7. Title" or "#### 7a. Title" or "### E1. Title"
HEADING = re.compile(r"^#{3,4} ([0-9A-Za-z]+)\. (.+?)\s*$")
STEP_ID = re.compile(r"^Step id: `([a-z][a-z0-9_]*)`\s*$")
SECTION = re.compile(r"^## (.+?)\s*$")
# "- `pass_count`: Checks this run hasn't hit the 10-pass limit."
CHECK = re.compile(r"^- `([a-z][a-z0-9_]*)`: (.+?)\s*$")


def parse_steps(markdown):
    """Every step in STEPS.md text, as {step_id: {number, title, text, error}}.

    The explanation is the paragraph(s) between the "Step id:" line and the
    "Code:" line; lines in a paragraph are joined with spaces, paragraphs with
    a blank line.
    """
    steps = {}
    section = ""
    heading = None      # (number, title) of the step being read
    step_id = None
    paragraphs = None   # list of lists of lines, once the step id is found

    def finish():
        if step_id is None:
            return
        if step_id in steps:
            raise ValueError(f"step id {step_id!r} appears twice in STEPS.md")
        text = "\n\n".join(" ".join(p) for p in paragraphs if p)
        steps[step_id] = {"number": heading[0], "title": heading[1], "text": text,
                          "error": "WRONG" in section.upper()}

    for line in markdown.splitlines():
        if (m := SECTION.match(line)):      # ":=" assigns and tests in one go
            finish()
            section, heading, step_id, paragraphs = m.group(1), None, None, None
        elif (m := HEADING.match(line)):
            finish()
            heading, step_id, paragraphs = (m.group(1), m.group(2)), None, None
        elif heading and step_id is None and (m := STEP_ID.match(line)):
            step_id, paragraphs = m.group(1), [[]]
        elif paragraphs is not None:
            if line.startswith("Code:"):
                finish()
                heading, step_id, paragraphs = None, None, None
            elif line.strip():
                paragraphs[-1].append(line.strip())
            elif paragraphs[-1]:
                paragraphs.append([])
    finish()
    return steps


def parse_checks(markdown):
    """Each guard's one-line explanation, from the "Checks" section:
    {guard_name: line}."""
    checks = {}
    in_checks = False
    for line in markdown.splitlines():
        if (m := SECTION.match(line)):
            in_checks = m.group(1).upper().startswith("CHECKS")
        elif in_checks and (m := CHECK.match(line)):
            if m.group(1) in checks:
                raise ValueError(f"check {m.group(1)!r} appears twice in STEPS.md")
            checks[m.group(1)] = m.group(2)
    return checks


def build(markdown):
    """The steps.json document for this STEPS.md text."""
    return {"source": "docs/STEPS.md",
            "generated_by": "build_steps.py: edit docs/STEPS.md, then rerun it",
            "steps": parse_steps(markdown),
            "checks": parse_checks(markdown)}


def render(markdown):
    """steps.json as text, exactly as it's written to disk."""
    return json.dumps(build(markdown), indent=2, ensure_ascii=False) + "\n"


def main(src=STEPS_MD, dest=STEPS_JSON):
    with open(src, encoding="utf-8") as f:
        text = render(f.read())
    with open(dest, "w", encoding="utf-8") as f:
        f.write(text)
    data = json.loads(text)
    print(f"Wrote {os.path.relpath(dest, HERE)}: {len(data['steps'])} steps and "
          f"{len(data['checks'])} checks from {os.path.relpath(src, HERE)}")


if __name__ == "__main__":
    main()
