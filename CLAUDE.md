# CLAUDE.md

Rules for working in this repo. Read this before doing anything.

## What this repo is

Small agents built to learn and show how agent loops work. One folder per agent.
Each agent folder has: agent code, README.md, CHANGELOG.md, and docs/
(SPEC.md, STEPS.md, DECISIONS.md, BUILD_LOG.md).

## How work happens

- Work only from a GitHub issue. Read it first: `gh issue view <N>`.
- Always work in a separate git worktree, never in Justin's main repo
  folder (`~/Documents/agents`): `git worktree add
  ../agents-worktrees/<branch> -b <branch> origin/main`. He may be using
  the main folder at the same time, and a branch switch there carries
  uncommitted work onto the wrong branch.
- Read the agent's docs/SPEC.md and docs/STEPS.md before changing code.
- One issue per branch, one branch per PR.
- Branch name: `issue-<N>-<short-description>`, e.g. `issue-4-strip-json-fences`.
- PR description must include:
  - `Closes #<N>`
  - What changed, in plain English. Justin reviews PRs to learn,
    so explain the why, not just the what.
  - How each acceptance criterion in the issue was checked.
- Never merge. Justin reviews and merges.

## Every PR also updates

- CHANGELOG.md: one line under Unreleased.
- docs/SPEC.md if behavior, tools, or prompts changed.
- docs/STEPS.md if a step was added, removed, or renamed.
- docs/DECISIONS.md if a design choice was made. Add it marked
  **Proposed**; Justin approves it in review.
- Do not write in BUILD_LOG.md. That is Justin's.

## Ask before

- Adding a dependency.
- Changing a tool description, system prompt, or rubric. These change
  what the agent decides. If an issue requires it, call it out at the top
  of the PR.
- Anything not in the issue. Open a new issue instead of expanding scope.

## Never

- Commit `.env` or any API key, or print a key in output or logs.
- Save or log anything a visitor enters in the web app.
- Put deterministic rules (comp floor, location, dedupe) in prompts.
  They belong in code.

## Code conventions

- Python 3.12. Each agent has its own .venv; run commands from the
  agent's folder.
- Find response content blocks by type, never by position (thinking
  blocks can come first).
- Step markers: `# STEP: <step_id>` comments anchor code references
  for the step-by-step page. Don't remove or rename one without
  updating STEPS.md. A marker goes on the line directly above the code.
- Never write line numbers in STEPS.md. `code_refs.py` looks them up
  from the markers when a run is recorded.
- Every guard (a check that stops a crash, a hang, or bad data) gets
  its own step in STEPS.md and a marker on its code.
- agent.py is annotated as a guided tour for Justin; keep it that way in
  every PR that touches it:
  - tag every `print` `# (terminal only)` and every `rec.` / `tracing.`
    line `# (trace only)`;
  - put `# GUARD (E<n> <step_id>): <what it protects against>` above each
    guard's marker, matching STEPS.md;
  - start terminal output with the step id in brackets, e.g. `[run_tools]`;
  - update the map in the module docstring and above `run_agent`, and the
    "what this looks like" examples, when the loop or a data shape changes;
  - explain any new Python idiom in one line where it first appears.
  `tests/test_annotations.py` checks the first three; the last two are on you.
- Before opening a PR, run the agent end to end and include a short
  summary of the output in the PR.
- Before opening a PR, run the tests from the agent's folder
  (`python -m unittest discover -s tests -v`) and include the result
  in the PR.
