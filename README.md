# agents

Agents I'm building to learn how agent loops work — each one small, traced, and documented.

Every agent lives in its own folder with its own code, spec, decision log, build log, and changelog. Work is tracked on the [project board](../../projects) as issues and merged through pull requests.

## Agents

| Agent | What it does | Status |
|---|---|---|
| [job-evaluator](job-evaluator/) | Rates a job posting against my criteria using tool calls; flags postings with missing info | v0.1 — runs end to end |

## How each agent is documented

| File | Purpose |
|---|---|
| `README.md` | What the agent does and how to run it |
| `docs/SPEC.md` | Living spec: purpose, tools, what the model sees, rules, success criteria |
| `docs/DECISIONS.md` | Design log: each decision, the options, the reasoning, and what would change it |
| `docs/BUILD_LOG.md` | Dated working log: what I did, what broke, what I learned |
| `CHANGELOG.md` | What changed in each version |

## How work happens

1. Every change starts as an issue on the board, with acceptance criteria.
2. Work happens on a branch named for the issue.
3. A pull request closes the issue (`Closes #N`), updates the changelog, and logs any decision.
4. Merge moves the card to Done.
