# agents

<!-- standard: design/_template/repo/CLAUDE.md v1.4
     Sections 1–6 are the standard: copy them unchanged, filling in only the <angle brackets>.
     Section 7 is this repository's own. To change a standard rule here, say so under
     "Overrides" in section 7, with the reason. -->

## 1. What this is

Small agents built to learn, and to show, how agent loops work, one folder per agent. The
first is the job evaluator, with a page that replays its recorded runs step by step.
Status: active.

## 2. Design

The design docs for this repository are in the `design` repository, cloned next to this
one, at `../design/agents/job-evaluator/`. Pull it before planning. In a git worktree,
`../design` means next to the main checkout, not next to the worktree.

Before proposing work, read in this order (skip any the project doesn't have yet):

1. `../design/agents/brief.md`: why it exists and for whom
2. `../design/agents/product-spec.md`: what the product must do, by capability ID
3. `../design/agents/architecture.md` and `principles.md`: how the parts fit, and
   the rules every design decision follows
4. `../design/agents/job-evaluator/brief.md` and `spec.md`: who this component is for,
   and what it must do
5. `../design/agents/job-evaluator/design.md`: how it works, and the decision log
6. `../design/agents/job-evaluator/<slice>-design.md`: the build design for the slice
   the issue belongs to
7. `../design/agents/job-evaluator/plan.md`: the milestones still ahead

- **Design leads, code follows.** If the work needs a change to what the product does,
  to a requirement or to the architecture, stop and propose the change. Once Justin
  approves it, make it in the Claude Doc (synced files) or in a pull request in `design`
  (repo-authored files), and build against it after it's merged. Never put a design
  change in this repository's pull request, and don't build ahead of the design.
- **When the design is silent, ask.** Don't improvise behavior, copy or scope.
- **When the design and this repository disagree, say so.** Don't guess which is right.
- A synced design file starts with a header naming its Claude Doc. If the two differ,
  the Claude Doc is current.

## 3. How work happens

- **The issue is the plan.** Work only from a GitHub issue, and read it first
  (`gh issue view <N>`). The issue authorizes the work; the spec and design constrain
  how it's done. If they conflict, stop and say so. With no issue, write the work up as
  a proposed issue and wait.
- One issue, one branch, one pull request. Branch name: `issue-<N>-<short-description>`.
- Anything outside the issue gets a new issue. Don't widen the scope.
- Never commit to `main`. Never merge: Justin reviews and merges.

## 4. Checks

- Run the checks listed in section 7 before opening a pull request, and paste the
  results into it.
- A failure is never ignored. Either the change is wrong or the check is; say which.
- Never change an expected result to make a check pass. Report the mismatch and stop.

## 5. Every pull request

Fill in `.github/pull_request_template.md`:

- `Closes #<N>`, and what changed and why, in plain English.
- How each acceptance criterion in the issue was checked.
- **Decisions (proposed):** choices made while coding: the decision, the options, why,
  and what would change it. Merging the pull request approves them.
- **Build notes:** what you did, what broke, what it taught.

## 6. Roll-up, ask before, never

**Roll-up.** Ask "Roll up to design?" when a pull request you opened is merged, when an
issue or milestone is done, and about every ten turns of work since you last asked.

- On yes: collect Decisions and Build notes from pull requests merged since the last
  roll-up (the latest "Roll-up:" line in the component's `build-log.md`). Propose
  decisions for the `design.md` decision log and findings for `build-log.md`, ending with
  the line `Roll-up: <repo> #<first>–#<last>`. For files synced from Claude Docs, add
  them as suggestions in the Claude Doc if you have the Docs connector; otherwise give
  Justin the text to paste. For repo-authored files, open a pull request in `design`.
- Every roll-up also checks for drift. For each synced file in the component and its
  project, compare the `rev` in its `sync-manifest.yaml` with the Claude Doc's current
  revision, and offer a sync pull request in `design` for any doc that has moved ahead.
  Without the Docs connector, list those docs and their links from `../design/DOCS.md`
  and ask Justin to check them.
- On no: don't ask again for another ten turns.
- Nothing enters the design record until Justin approves it.

**Ask before:**

- adding a dependency
- changing a prompt, tool description, rubric, or anything else that changes what a
  model decides
- anything not in the issue

**Never:**

- read, print or edit `.env`. Secrets live only there; `.env.example` holds key names only
- commit secrets, API keys or real customer data
- rewrite git history

## 7. This repository

- **Layout:**
  - `job-evaluator/`: the first agent. `agent.py` (the loop, annotated as a guided
    tour), `record.py` (records scenarios), `site/` (the replay page), `tests/`,
    `scenarios/`, `recordings/`, `data/`, `CHANGELOG.md`, `README.md`.
  - `job-evaluator/docs/`: only the docs generated from code: `STEPS.md` (the steps,
    their markers and E-steps) and `SCENARIOS.md` (written by `record.py`). The design
    docs (brief, design and decision log, build log, principles) are in the design repo.
  - `.github/pull_request_template.md`: the pull request template from section 5.
- **Finding the design repo:** `design_path()` in `job-evaluator/design_repo.py` is the
  one lookup the tests and `build_numbers.py` use: `$DESIGN_DIR` if set, else `design/`
  next to the main checkout (found with `git rev-parse --git-common-dir`, so a worktree
  finds it too). If it isn't there, the doc tests fail with "clone justinyurasits/design
  next to agents". From a worktree, read section 2's `../design/` paths from beside the
  main checkout (`~/code/design`), not from beside the worktree.
- **Run:** from `job-evaluator/`, with its `.venv` active:
  `python agent.py` (the sample posting), `python agent.py --scenario <n>`,
  `python record.py <n>` or `--all` (real API calls), and
  `python -m http.server 8000`, then `localhost:8000/site/` for the page.
- **Checks:** before opening a pull request:
  - Run the agent end to end and put a short summary of its output in the PR.
  - Run the tests from `job-evaluator/`: `python -m unittest discover -s tests -v`.
  - If the PR touches `site/`, run them with Playwright and Chromium installed
    (`pip install -r requirements-dev.txt`, then `python -m playwright install
    chromium`) and paste the browser tests' result (`tests/test_browser.py`). A skipped
    browser suite doesn't count.
  - If the PR adds or removes a tool, or changes a tool description, tool schema, system
    prompt or rubric, call that out at the top of the PR, re-run every scenario
    (`python record.py --all`) and paste every PASS or MISMATCH line. A tool's
    description can change which tool Claude picks in scenarios the PR never touched.
    Don't change a scenario's expected tools or outcome to make it pass, unless the
    issue says that path should change.
  - `record.py` overwrites the recordings. Restore them before committing
    (`git restore recordings/ docs/SCENARIOS.md`) unless the issue asks for new ones.
  - `CHANGELOG.md`: one line under Unreleased. `docs/STEPS.md` if a step was added,
    removed or renamed.
  - Last, after the other changes: `python build_numbers.py` rebuilds
    `site/numbers.json` (tests, decisions, merged PRs), and
    `test_committed_numbers_json_matches_the_repo` fails until it's rerun.
- **Conventions:**
  - Python 3.12. Each agent has its own `.venv`; run commands from the agent's folder.
  - Never print a key in output or logs. Never save or log anything a visitor enters in
    the web app.
  - Deterministic rules (comp floor, location, dedupe) belong in code, never in prompts.
  - Find response content blocks by type, never by position (thinking blocks can come
    first).
  - Step markers: `# STEP: <step_id>` comments anchor code references for the page.
    A marker goes on the line directly above the code. Don't remove or rename one
    without updating STEPS.md. Never write line numbers in STEPS.md: `code_refs.py`
    looks them up from the markers.
  - Every guard (a check that catches a failure: a crash, a hang, or bad data) gets its
    own E-step under "When something goes wrong" in STEPS.md and a marker on its code.
  - Every rule (a check that applies one of Justin's decisions, like the $180K floor) is
    a normal step in the flow, not an E-step: a rule rejecting a posting is the agent
    working as intended. It gets a marker too.
  - `agent.py` is annotated as a guided tour for Justin; keep it that way in every PR
    that touches it:
    - tag every `say(...)` (and the one `print`, inside `say`) `# (terminal only)` and
      every `rec.` / `tracing.` line `# (trace only)`;
    - put `# GUARD (E<n> <step_id>): <what it protects against>` above each guard's
      marker, matching STEPS.md, and `# RULE (<step_id>): <what it decides>` above each
      rule's marker;
    - print terminal output only through `say("<step_id>", text)`, which starts each
      line with the step id and the file:line of its code, e.g.
      `[run_tools agent.py:<line>]`. The line is looked up from the step's `# STEP:`
      marker when the agent starts; never type a line number;
    - update the map in the module docstring and above `run_agent`, and the "what this
      looks like" examples, when the loop or a data shape changes;
    - explain any new Python idiom in one line where it first appears.
      `tests/test_annotations.py` checks the first three; the last two are on you.
- **Overrides:** None. One addition: always work in a separate git worktree, never in
  Justin's main folder (`~/code/agents`):
  `git worktree add ../agents-worktrees/<branch> -b <branch> origin/main`, which puts it
  in `~/code/agents-worktrees/`. He may be using the main folder at the same time, and a
  branch switch there carries uncommitted work onto the wrong branch.
