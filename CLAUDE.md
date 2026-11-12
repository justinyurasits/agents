# CLAUDE.md

Rules for working in this repo. Read this before doing anything.

## What this repo is

Small agents built to learn and show how agent loops work. One folder per agent.
Each agent folder has: agent code, README.md, CHANGELOG.md, and docs/
(SPEC.md, STEPS.md, DECISIONS.md, BUILD_LOG.md).

## How work happens

- Work only from a GitHub issue. Read it first: `gh issue view <N>`.
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
  updating STEPS.md.
- Before opening a PR, run the agent end to end and include a short
  summary of the output in the PR.
