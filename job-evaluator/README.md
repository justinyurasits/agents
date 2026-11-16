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
- `research_company` — plain Python, no model call; looks up stored demo facts about a company (`data/companies.json`), including typical base pay for a role level, for postings with no pay listed

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

The script prints a line at each point in the loop, labelled with its step id from [docs/STEPS.md](docs/STEPS.md) and where that step's code is (e.g. `[send_to_claude agent.py:<line>]`), so you can follow a run in the terminal and jump to the code that printed each line. In VS Code's terminal, Cmd/Ctrl-click the `agent.py:<line>`. The line numbers are looked up from the `# STEP:` markers each run, so they stay right as the code changes. To follow the code itself, start at the top of `agent.py`: it explains how to read the file and maps the whole loop, and writes a trace of the run to `traces/<scenario>-<timestamp>.json` (format: [docs/SPEC.md](docs/SPEC.md), section 7).

## See a run on the page

```bash
cd job-evaluator
python build_steps.py               # after editing docs/STEPS.md or agent.py: rebuild site/steps.json (and site/numbers.json)
python build_numbers.py             # recount the numbers on the page; needed in every PR (see CLAUDE.md)
python make_preview.py              # remake site/preview.png, the link-preview image (needs requirements-dev.txt)
python -m http.server 8000          # then open localhost:8000/site/
```

The page (`site/`) explains what an agent is and how this one works, then replays any of the nine recorded scenarios step by step (pick one from the list, or open `/site/?scenario=3`): who's executing, what crossed between Claude, Python and the tools, and what changed in the conversation. It makes no API calls. See [docs/SPEC.md](docs/SPEC.md), section 8.

## Test it

```bash
cd job-evaluator
source .venv/bin/activate
python -m unittest discover -s tests -v
```

The tests use a fake Claude client, so they make no API calls and need no `.env` or API key. Run them before every PR.

### Browser tests

`tests/test_browser.py` loads the page in a real browser (headless Chromium, through Playwright for Python) and checks all nine scenarios: Claude's words appear only under "Claude's response", searched in the State change, Code and Payload tabs at every step (D31, D38), every request's tool definitions match the recording (#114), every check and rule is a card worded from STEPS.md, with its real E-number and its code (#115, #118), every scenario plays to its last step with no console errors and no `undefined` on screen, and `?scenario=` and Back work. The tests start their own local server. One-time setup:

```bash
pip install -r requirements-dev.txt     # the agent's requirements, plus Playwright
python -m playwright install chromium   # the browser (about 100 MB, stored outside the repo)
```

Without Playwright or Chromium, these four tests are skipped with the reason and everything else still runs. A PR that touches `site/` needs them run, not skipped.

## Status

Version 0.1.0 was tagged in the changelog; everything since is under Unreleased. The agent runs every scenario in `scenarios/scenarios.json`. Its guards, hard rules and fault injection are built, and every step is traced. `record.py` records and checks scenarios: all nine are recorded (`recordings/`), and page v0 replays any of them. Next is the full page (D33). Known gaps are in [docs/SPEC.md](docs/SPEC.md#9-known-limits) and open issues on the board.
