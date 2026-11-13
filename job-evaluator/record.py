"""Record a scenario for the page: run it for real, save it, check it (#53).

    python record.py 5        # run scenario 5, save recordings/scenario-05.json
    python record.py --all    # every scenario, in order

Each run uses the scenario's posting(s) and fault exactly as written in
scenarios/scenarios.json, and nothing else. It's a real run: it needs an API
key in .env and costs API calls (2-4 per scenario).

After the run, the recording is checked against the scenario's `expect`:
the tools called, in order, and the outcome. Claude's wording isn't
compared. The script prints PASS, or MISMATCH with what differed; a
mismatched run is still saved, with "mismatch": true and the differences in
the file, so the page never plays a run that doesn't show what it promises
without that being visible.

Every run also regenerates docs/SCENARIOS.md from scenarios.json, so the
doc always matches the data.

    expect, in scenarios.json (one object, or a list of acceptable ones):
        {"tools": ["evaluate_job"], "outcome": "STRONG"}
    outcome: STRONG, WORTH REVIEWING, IGNORE, flagged, stopped, or
    "no rating" (finished without rating or flagging anything); a list when
    the run handles several postings, e.g. ["STRONG", "flagged"].
"""

import argparse
import json
import os
import sys

import agent
import faults
import tracing

HERE = os.path.dirname(os.path.abspath(__file__))
SCENARIOS_FILE = os.path.join(HERE, "scenarios", "scenarios.json")
RECORDINGS_DIR = os.path.join(HERE, "recordings")
SCENARIOS_MD = os.path.join(HERE, "docs", "SCENARIOS.md")

# Every way a run can end except end_turn is a stop (tracing.END_STEPS).
STOPPED = {"max_tokens", "pass_cap", "api_error", "no_text", "unexpected_stop"}


def load_scenarios(path=SCENARIOS_FILE):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def recording_path(scenario_id, directory=RECORDINGS_DIR):
    return os.path.join(directory, f"scenario-{scenario_id:02d}.json")


# --- what happened, read from the trace ---------------------------------

def actual(trace):
    """What a recorded run did: {"tools": [...], "outcome": [...]}.

    tools: every tool Claude asked for, in order (an unknown tool too), with
    back-to-back repeats counted once, so a retry doesn't change the path.
    outcome: "stopped" if a guard stopped the run; otherwise one entry per
    tool that succeeded with a verdict (evaluate_job's rating, or "flagged"),
    or ["no rating"] if there was none.
    """
    results = [e["payload"] for e in trace["events"]
               if e["step_id"] == "run_tools" and isinstance(e["payload"], dict)
               and "is_error" in e["payload"]]
    tools = []
    for r in results:
        if not tools or tools[-1] != r["tool"]:
            tools.append(r["tool"])

    if trace["result"]["ended_by"] in STOPPED:
        return {"tools": tools, "outcome": ["stopped"]}
    outcome = []
    for r in results:
        if r["is_error"]:
            continue
        if r["tool"] == "evaluate_job":
            outcome.append(json.loads(r["content"])["rating"])
        elif r["tool"] == "flag_for_review":
            outcome.append("flagged")
    return {"tools": tools, "outcome": outcome or ["no rating"]}


def _as_list(value):
    return value if isinstance(value, list) else [value]


def differences(expect, got):
    """What differs between a scenario's `expect` and what the run did, as
    plain sentences; [] means PASS. `expect` may be a list of acceptable
    results: matching any one of them is a PASS."""
    options = _as_list(expect)
    found = []
    for option in options:
        wanted = {"tools": option["tools"], "outcome": _as_list(option["outcome"])}
        diffs = [f"{key}: expected {', '.join(wanted[key]) or 'none'}; "
                 f"got {', '.join(got[key]) or 'none'}"
                 for key in ("tools", "outcome") if wanted[key] != got[key]]
        if not diffs:
            return []
        found.append(diffs)
    if len(options) == 1:
        return found[0]
    return ["matched none of the accepted results: "
            + " | ".join("; ".join(d) for d in found)]


# --- recording -------------------------------------------------------------

def record(scenario, directory=RECORDINGS_DIR, out=print):
    """Run one scenario for real, save its recording, and return the check:
    {"expected", "actual", "mismatch", "differences"}."""
    sid = scenario["id"]
    out(f"\n=== Recording scenario {sid}: {scenario['name']}"
        + (f" (fault: {scenario['fault']})" if scenario["fault"] else ""))
    recorder = tracing.Recorder(scenario=f"scenario-{sid}")
    agent.run_agent(agent.scenario_job_text(scenario), recorder=recorder,
                    fault=faults.Fault(scenario["fault"]))

    got = actual(recorder.to_dict())
    diffs = differences(scenario["expect"], got)
    check = {"expected": scenario["expect"], "actual": got,
             "mismatch": bool(diffs), "differences": diffs}
    path = recorder.write_to(recording_path(sid, directory),
                             extra={"mismatch": bool(diffs), "check": check})
    if diffs:
        out(f"MISMATCH  scenario {sid}: " + " / ".join(diffs))
    else:
        out(f"PASS  scenario {sid}: tools {', '.join(got['tools']) or 'none'}; "
            f"outcome {', '.join(got['outcome'])}")
    out(f"Saved {os.path.relpath(path, HERE)}")
    return check


# --- docs/SCENARIOS.md -------------------------------------------------------

GROUP_HEADINGS = {"normal": "## Normal runs",
                  "break": "## Break the agent (fault injected on purpose, labeled on the page)"}


def _expect_line(expect):
    def one(option):
        tools = ", ".join(option["tools"]) or "none"
        return f"tools {tools}; outcome {', '.join(_as_list(option['outcome']))}"
    return " **or** ".join(one(o) for o in _as_list(expect))


def render_scenarios_md(scenarios):
    """docs/SCENARIOS.md, built from scenarios.json. Pure function."""
    lines = ["# Scenarios", "",
             "The runs the page plays. Generated from `scenarios/scenarios.json`; "
             "edit the JSON, not this file. `python record.py` regenerates it.", "",
             "Every company and posting here is fictional, written for this demo.", ""]
    group = None
    for s in scenarios:
        if s["group"] != group:
            group = s["group"]
            lines += [GROUP_HEADINGS[group], ""]
        lines += [f"### {s['id']}. {s['name']}", "",
                  f"**What the visitor sees:** {s['behavior']}", ""]
        if s["fault"]:
            lines += [f"**Injected fault:** `{s['fault']}`", ""]
        postings = _as_list(s["posting"])
        for n, posting in enumerate(postings, start=1):
            if len(postings) > 1:
                lines += [f"**Posting {n}:**", ""]
            lines += ["```text", posting, "```", ""]
        if s["company_facts"]:
            lines += ["**Stored company facts:**", ""]
            lines += [f"- {key.replace('_', ' ').capitalize()}: {value}"
                      for key, value in s["company_facts"].items()]
            lines += [""]
        lines += [f"**Expected tools:** {', '.join(s['expected_tools']) or 'none (no tool runs)'}", "",
                  f"**Expected outcome:** {s['expected_outcome']}", "",
                  f"**Checked by record.py:** {_expect_line(s['expect'])}", ""]
    return "\n".join(lines)


def write_scenarios_md(scenarios, path=SCENARIOS_MD):
    with open(path, "w", encoding="utf-8") as f:
        f.write(render_scenarios_md(scenarios))


# --- command line ------------------------------------------------------------

def main(argv=None, scenarios_file=SCENARIOS_FILE, directory=RECORDINGS_DIR,
         docs_path=SCENARIOS_MD, out=print):
    """Returns the exit code: 0 if every run passed, 1 on any mismatch,
    2 for a scenario id that doesn't exist (nothing is run)."""
    parser = argparse.ArgumentParser(description="Record scenarios for the page.")
    parser.add_argument("scenario", nargs="?", type=int, help="the scenario id to record")
    parser.add_argument("--all", action="store_true", help="record every scenario")
    args = parser.parse_args(argv)
    if (args.scenario is None) == (not args.all):
        parser.error("give one scenario id, or --all")

    scenarios = load_scenarios(scenarios_file)
    ids = [s["id"] for s in scenarios]
    if not args.all and args.scenario not in ids:
        out(f"No scenario {args.scenario}. Valid ids: {', '.join(map(str, ids))}.")
        return 2

    write_scenarios_md(scenarios, docs_path)
    chosen = scenarios if args.all else [s for s in scenarios if s["id"] == args.scenario]
    checks = [record(s, directory, out) for s in chosen]
    if args.all:
        failed = [s["id"] for s, c in zip(chosen, checks) if c["mismatch"]]
        out(f"\n{len(chosen) - len(failed)} of {len(chosen)} passed"
            + (f"; mismatches: {', '.join(map(str, failed))}" if failed else ""))
    return 1 if any(c["mismatch"] for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
