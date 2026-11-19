"""Build site/numbers.json: the numbers on the page's "How it was built"
section (#81), counted from the repo. Nothing here is typed by hand.

    python build_numbers.py        (build_steps.py runs it too)

Each number, and where it comes from:
  tests        test cases unittest finds in tests/ (browser tests included,
               whether or not Chromium is installed)
  scenarios    entries in scenarios/scenarios.json, by group
  decisions    "## D<n>" entries (and "## D11a") in the decision log at the end of
               design.md, in the design repo (#125), by their Status line:
               Approved, Proposed, another status (e.g. "closed by D28"), or
               none (most early entries were written before the Status line)
  guards       E-steps in docs/STEPS.md, and how many a recording shows caught
  merged_prs   "Merge pull request #" commits in git history: the PRs merged
               before this one. On main (or a detached checkout of it), HEAD
               itself isn't counted when it's a merge: it's the merge of the
               PR whose number this is. On any other branch it is counted: a
               new branch with no commits yet starts at the previous PR's
               merge (#108). So a branch and main after its merge agree.

A test (tests/test_site.py) fails if the committed file and a fresh count
differ: rerun this script in any PR that changes one of these.
"""

import glob
import json
import os
import re
import subprocess
import unittest

import build_steps
from design_repo import design_doc

HERE = os.path.dirname(os.path.abspath(__file__))
NUMBERS_JSON = os.path.join(HERE, "site", "numbers.json")
MERGE = "^Merge pull request #"


def read(*parts):
    with open(os.path.join(HERE, *parts), encoding="utf-8") as f:
        return f.read()


def count_tests():
    return unittest.defaultTestLoader.discover(os.path.join(HERE, "tests"), top_level_dir=HERE).countTestCases()


def count_scenarios():
    scenarios = json.loads(read("scenarios", "scenarios.json"))
    groups = [s["group"] for s in scenarios]
    return {"total": len(scenarios), "normal": groups.count("normal"), "break": groups.count("break")}


def count_decisions():
    # Split the log into entries at each "## D<n>" heading; read each one's Status.
    entries = re.split(r"^## D\d+[a-z]? ", design_doc()[1], flags=re.M)[1:]   # D11a too (#93)
    words = []
    for e in entries:
        line = re.search(r"^\*\*Status:\*\*(.*)$", e, re.M)
        word = re.match(r" \*\*(Approved|Proposed)\*\*", line.group(1)) if line else None
        words.append(word.group(1) if word else ("other" if line else None))
    return {"logged": len(entries), "approved": words.count("Approved"), "proposed": words.count("Proposed"),
            "other_status": words.count("other"), "no_status": words.count(None)}


def count_guards():
    steps = build_steps.parse_steps(read("docs", "STEPS.md"))
    e_steps = {sid for sid, step in steps.items() if step["error"]}
    caught = set()
    for path in glob.glob(os.path.join(HERE, "recordings", "*.json")):
        with open(path, encoding="utf-8") as f:
            caught |= {e["step_id"] for e in json.load(f)["events"] if e["guard"] and e["guard"]["caught"]}
    return {"total": len(e_steps), "demonstrated": len(e_steps & caught)}


def git(*args, cwd=HERE):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def count_merged_prs(cwd=HERE):
    merges = int(git("rev-list", "--count", f"--grep={MERGE}", "HEAD", cwd=cwd))
    head_is_a_merge = re.match(MERGE[1:], git("log", "-1", "--format=%s", cwd=cwd))
    # The branch name: "main", "HEAD" for a detached checkout, or a feature branch.
    on_main = git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd) in ("main", "HEAD")
    return merges - (1 if head_is_a_merge and on_main else 0)


def build():
    return {"tests": count_tests(), "scenarios": count_scenarios(), "decisions": count_decisions(),
            "guards": count_guards(), "merged_prs": count_merged_prs()}


def render(numbers):
    return json.dumps(numbers, indent=2) + "\n"


def main(dest=NUMBERS_JSON):
    numbers = build()
    with open(dest, "w", encoding="utf-8") as f:
        f.write(render(numbers))
    print(f"Wrote {os.path.relpath(dest, HERE)}:")
    print(render(numbers), end="")


if __name__ == "__main__":
    main()
