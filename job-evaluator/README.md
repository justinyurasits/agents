# job-evaluator

An agent that rates a job posting against my criteria. Claude reads the posting and decides which tool to use — rate it, or flag it for review when key information is missing. Python runs the tools and feeds the results back until Claude decides it's done.

Built to learn the agent loop: what Claude decides, what Python does, and what passes between them.

## How it works

```
Python sends: system prompt + tool definitions + messages
      ↓
Claude replies: tool_use (request)  or  end_turn (done)
      ↓
Python runs the requested tool, appends the request + tool_result, sends again
      ↓
...until stop_reason == "end_turn"
```

Tools:
- `evaluate_job` — checks the hard rules in code first (remote, $180K base floor; a posting that fails one is IGNORE), then makes a separate, focused Claude call that answers one yes/no question, and returns `{rating, reasons}`
- `flag_for_review` — plain Python, no model call; returns what's missing

See [docs/SPEC.md](docs/SPEC.md) for the full spec.

## Run it

```bash
cd job-evaluator
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then add your Anthropic API key
python agent.py                     # the built-in sample posting
python agent.py --scenario 6        # a scenario from scenarios/scenarios.json
python agent.py --fault tool_fails  # force one failure on purpose (see faults.py)
python record.py 5                  # record scenario 5 for the page and check it
python record.py --all              # record every scenario
```

`record.py` runs a scenario for real (it needs your API key and makes 2–4 API calls per scenario), saves it to `recordings/scenario-<id>.json`, and checks it against the scenario's `expect` in `scenarios/scenarios.json`: the tools called and the outcome, not Claude's wording. It prints PASS, or MISMATCH with what differed; a mismatched run is still saved, marked `"mismatch": true`. It also regenerates `docs/SCENARIOS.md` from the JSON.

The script prints a line at each point in the loop, labelled with its step id from [docs/STEPS.md](docs/STEPS.md) (e.g. `[send_to_claude]`), so you can follow a run in the terminal. To follow the code itself, start at the top of `agent.py`: it explains how to read the file and maps the whole loop, and writes a trace of the run to `traces/<scenario>-<timestamp>.json` (format: [docs/SPEC.md](docs/SPEC.md), section 7).

## Test it

```bash
cd job-evaluator
source .venv/bin/activate
python -m unittest discover -s tests -v
```

The tests use a fake Claude client, so they make no API calls and need no `.env` or API key. Run them before every PR.

## Status

v0.1 — runs end to end on one test posting. Known gaps are open issues on the board.
