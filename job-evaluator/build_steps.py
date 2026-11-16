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

It also reads two tables at the end of STEPS.md (#115). "Checks": one row
per guard check and the step it runs at,

    | `pass_count` | `send_to_claude` | `pass_cap` | Checks this run hasn't ... |

written as "checks": [{"check": "pass_count", "runs_at": ["send_to_claude"],
"caught_as": "pass_cap", "text": "Checks this run ..."}, ...] ("none" in
"Caught as" becomes null). And "Rules": one row per hard rule,

    | `comp_floor` | Salary floor | The lowest base ... | Code rates it IGNORE ... |

written as "rules": {"comp_floor": {"name": "Salary floor", "text": ...,
"fails": ...}}. The page builds each check's card from these and the steps.
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
# A table row: "| a | b | c |" -> ["a", "b", "c"]. A row of dashes is the header's underline.
ROW = re.compile(r"^\|(.+)\|\s*$")
CODE = re.compile(r"`([a-z][a-z0-9_]*)`")


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


def table_rows(markdown, section):
    """The body rows of the table in the "## <section>" part of STEPS.md, as
    lists of cell texts (the header row and its underline are skipped)."""
    rows, inside, seen_header = [], False, False
    for line in markdown.splitlines():
        if (m := SECTION.match(line)):
            inside, seen_header = m.group(1).upper().startswith(section), False
        elif inside and (m := ROW.match(line)):
            cells = [c.strip() for c in m.group(1).split("|")]
            if set("".join(cells)) <= set("-: "):
                continue                    # the |---|---| underline
            if not seen_header:
                seen_header = True          # the first row names the columns
                continue
            rows.append(cells)
    return rows


def parse_checks(markdown):
    """Each guard check, from the "Checks" table: a list of
    {check, runs_at, caught_as, text}, one per check and place it runs."""
    checks = []
    for check, runs_at, caught_as, text in table_rows(markdown, "CHECKS"):
        row = {"check": CODE.fullmatch(check).group(1), "runs_at": CODE.findall(runs_at),
               "caught_as": None if caught_as == "none" else CODE.fullmatch(caught_as).group(1),
               "text": text}
        for other in checks:
            if other["check"] == row["check"] and set(other["runs_at"]) & set(row["runs_at"]):
                raise ValueError(f"check {row['check']!r} at {row['runs_at']} appears twice in STEPS.md")
        checks.append(row)
    return checks


def parse_rules(markdown):
    """Each hard rule, from the "Rules" table: {rule: {name, text, fails}}."""
    rules = {}
    for rule, name, text, fails in table_rows(markdown, "RULES"):
        rule = CODE.fullmatch(rule).group(1)
        if rule in rules:
            raise ValueError(f"rule {rule!r} appears twice in STEPS.md")
        rules[rule] = {"name": name, "text": text, "fails": fails}
    return rules


def build(markdown):
    """The steps.json document for this STEPS.md text."""
    return {"source": "docs/STEPS.md",
            "generated_by": "build_steps.py: edit docs/STEPS.md, then rerun it",
            "steps": parse_steps(markdown),
            "checks": parse_checks(markdown),
            "rules": parse_rules(markdown)}


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
          f"{len(data['checks'])} checks and {len(data['rules'])} rules from {os.path.relpath(src, HERE)}")


if __name__ == "__main__":
    main()
    # The page's other generated file: the numbers in "How it was built" (#81).
    import build_numbers   # here, not at the top: build_numbers imports this file
    build_numbers.main()
