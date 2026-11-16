# CLAUDE.md

Rules for working in this repo. Read this before doing anything.

## What this repo is

Small agents built to learn and show how agent loops work. One folder per agent.
Each agent folder has: agent code, README.md, CHANGELOG.md, and docs/
(BRIEF.md, SPEC.md, STEPS.md, SCENARIOS.md, DECISIONS.md, BUILD_LOG.md).

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
- job-evaluator/site/numbers.json: run `python build_numbers.py` from
  job-evaluator/ last, after your other changes. It counts tests,
  decisions and merged PRs, so almost every PR changes it, and
  `test_committed_numbers_json_matches_the_repo` fails until it's rerun.
- The agent's docs/BUILD_LOG.md: add this PR to today's dated section
  (Did / Broke / Learned), creating the section if needed. Write it in the
  PR, don't just suggest it; Justin edits it in review.
- LEARNINGS.md (repo root): add an entry, with its source, when the PR
  taught something general about agents, testing or building with a coding
  agent.

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
- Every guard (a check that catches a failure: a crash, a hang, or bad
  data) gets its own E-step under "When something goes wrong" in
  STEPS.md and a marker on its code.
- Every rule (a check that applies one of Justin's decisions, like the
  $180K floor) is a normal step in the flow, not an E-step: a rule
  rejecting a posting is the agent working as intended. It gets a marker
  too.
- agent.py is annotated as a guided tour for Justin; keep it that way in
  every PR that touches it:
  - tag every `say(...)` (and the one `print`, inside `say`) `# (terminal
    only)` and every `rec.` / `tracing.` line `# (trace only)`;
  - put `# GUARD (E<n> <step_id>): <what it protects against>` above each
    guard's marker, matching STEPS.md, and `# RULE (<step_id>): <what it
decides>` above each rule's marker;
  - print terminal output only through `say("<step_id>", text)`, which
    starts each line with the step id and the file:line of its code, e.g.
    `[run_tools agent.py:<line>]`. The line is looked up from the step's
    `# STEP:` marker when the agent starts; never type a line number;
  - update the map in the module docstring and above `run_agent`, and the
    "what this looks like" examples, when the loop or a data shape changes;
  - explain any new Python idiom in one line where it first appears.
    `tests/test_annotations.py` checks the first three; the last two are on you.
- Before opening a PR, run the agent end to end and include a short
  summary of the output in the PR.
- Before opening a PR, run the tests from the agent's folder
  (`python -m unittest discover -s tests -v`) and include the result
  in the PR.
  - If a PR touches `site/`, run them with Playwright and Chromium
    installed (`pip install -r requirements-dev.txt`, then
    `python -m playwright install chromium`) and paste the browser
    tests' result (`tests/test_browser.py`) into the PR. A skipped
    browser suite doesn't count.
  - If a PR adds or removes a tool, or changes a tool description, tool
    schema, system prompt, or rubric, re-run every scenario before opening
    it (in job-evaluator: `python record.py --all`) and paste every PASS or
    MISMATCH line into the PR. A tool's description can change which tool
    Claude picks in scenarios the PR never touched.
  - Don't change a scenario's expected tools or outcome to make it pass,
    unless the issue says that path should change. Otherwise report the
    mismatch and stop.
  - record.py overwrites the recordings. Restore them before committing
    (`git restore recordings/ docs/SCENARIOS.md`) unless the issue asks
    for new ones.
