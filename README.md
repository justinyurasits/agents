# agents

Agents I'm building to learn how agent loops work — each one small, traced, and documented.

Every agent lives in its own folder with its own code, spec, decision log, build log, and changelog. Work is tracked on the [project board](../../projects) as issues and merged through pull requests.

## Agents

| Agent | What it does | Status |
|---|---|---|
| [job-evaluator](job-evaluator/) | Rates a job posting against my criteria using tool calls; flags postings with missing info | Agent, guards and tracing built; scenario 6 recorded and replayed by page v0; full page next |

## How each agent is documented

| File | Purpose |
|---|---|
| `README.md` | What the agent does and how to run it |
| `docs/BRIEF.md` | Product brief: what it's for, who it's for, what's on the page |
| `docs/SPEC.md` | Design doc: how the agent works and why (loop, tools, what the model sees, guards, rules, trace format, the page) |
| `docs/STEPS.md` | Every step of a run in plain English, as the page shows it; the source of the page's explanations |
| `docs/SCENARIOS.md` | The prepared scenarios, generated from `scenarios/scenarios.json` |
| `docs/DECISIONS.md` | Design log: each decision, the options, the reasoning, and what would change it |
| `docs/BUILD_LOG.md` | Dated working log: what I did, what broke, what I learned |
| `CHANGELOG.md` | What changed in each version |

Across all agents, [`LEARNINGS.md`](LEARNINGS.md) collects what building them has taught me.

## How work happens

1. Every change starts as an issue on the board, with acceptance criteria.
2. Work happens on a branch named for the issue.
3. A pull request closes the issue (`Closes #N`), updates the changelog, and logs any decision.
4. Merge moves the card to Done.
