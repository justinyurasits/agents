# job-evaluator — Decision log

One entry per decision. Newest at the bottom. Format: decision, options considered, reasoning, what would change it.

---

## D1 — One repo for all agents, one folder per agent
**Date:** 2026-11-11
**Options:** separate repo per agent · one `agents` repo with a folder per agent
**Decision:** one repo, folder per agent.
**Reasoning:** I'll build many small agents; a new folder costs nothing, and the root README becomes an index that tells one story.
**What would change it:** an agent becomes a flagship piece that needs its own README, releases, and issues — then it moves to its own repo.

## D2 — Repo private until the first README is solid
**Date:** 2026-11-11
**Options:** public from day one · private, flip later
**Decision:** private for now.
**Reasoning:** the public version should read as finished work. Flipping is one click.
**What would change it:** job-evaluator README, spec, and one sample trace are done.

## D3 — One virtual environment per agent
**Date:** 2026-11-11
**Options:** one shared environment at the repo root · one per agent folder
**Decision:** one per agent (`job-evaluator/.venv`).
**Reasoning:** agents will need different packages; isolating them avoids version clashes.
**What would change it:** agents end up sharing nearly all dependencies.

## D4 — Track work on a GitHub Projects board, issue → branch → PR
**Date:** 2026-11-11
**Options:** TODO comments in code · issues only · issues on a board with automation
**Decision:** board with Backlog / Todo / In Progress / Done; issues auto-added; merged PRs move cards to Done.
**Reasoning:** makes the way I work visible, and every change gets acceptance criteria before it gets code.
**What would change it:** —

## D5 — `evaluate_job` uses its own Claude call (inherited, under review)
**Date:** 2026-11-11
**Options:** grade inside the outer Claude call (no tool) · separate focused Claude call inside the tool · deterministic scoring in Python
**Decision:** keep the separate call for now.
**Reasoning:** focused prompt, more reliable JSON, reusable outside the loop. But in a one-job run it adds a call without adding information.
**What would change it:** issue #6 (hard screens into code) may shrink what's left for the model to judge to one criterion.

## D6 — Hard rules currently live in the prompt (open)
**Date:** 2026-11-11
**Status:** open — issue #6.
**Context:** the $180K floor and remote requirement are deterministic but sit in `RUBRIC`. A model can misapply a rule that code can't.
