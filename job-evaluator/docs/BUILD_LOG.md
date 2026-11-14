# job-evaluator — Build log

Dated working log. What I did, what broke, what I learned. Write it the same day.

---

## 2026-11-11 — Repo setup and first run

**Did**

- Walked through the agent loop step by step: tool definitions vs functions, dispatch, `stop_reason`, the messages list as memory, `tool_use_id` pairing, the inner Claude call in `evaluate_job`.
- Created the `agents` repo (private, Python .gitignore), added `job-evaluator/` with `agent.py`, `requirements.txt`, `.env.example`.
- Set up a virtual environment and `.env`; added `load_dotenv()` so the key loads from `.env`.
- Removed compensation from the test job: Claude chose flag_for_review instead of
    evaluate_job (2 API calls instead of 3). No code changed; the tool description
    drove the choice.
- First successful end-to-end run: 3 API calls, evaluate_job requested and dispatched,
  tool_result returned, end_turn.

**Broke**

- Ran `python3 -m venv .venv` and `pip install -r requirements.txt` from the repo root instead of `job-evaluator/`. Error: `Could not open requirements file`. Fix: deleted the root `.venv`, `cd job-evaluator`, recreated it there.
- Note: `(base)` in the prompt is Anaconda's base environment. `(.venv)` takes priority; `conda deactivate` if package errors show up.
- Put my real API key in .env.example (the committed file) and pushed it.
  Fix: revoked the key in the console, new key in .env only, restored the placeholder.
- Misspelled the folder (job_evaluator). Fix: renamed, rebuilt .venv (a venv breaks
  when its folder moves).
- Ran python agent.py from the repo root. Error: "No such file or directory".
- 401 invalid x-api-key. A revoked key was set in the terminal and overrode .env
  (load_dotenv doesn't replace an existing variable), and .env had leading spaces.
  Fix: unset ANTHROPIC_API_KEY, rewrote .env cleanly.
- AttributeError: 'ThinkingBlock' object has no attribute 'text'. Code assumed
  content[0] is text; the model returned a thinking block first.
  Fix: find blocks by type, not position, in evaluate_job and in the exit check.
  Raised max_tokens to 2000.
- NameError: name `______` is not defined. Pasted the fill-in-the-blank template
  literally.

**Learned**

- API key in .env needs to have no leading spaces.
- High level walkthrough of the script, including the tools, the agent loop, and the basic interactions between.

## 2026-11-12 — Product brief, workflow, and the agent hardened

**Did**

- Wrote the product brief: a learning and demo tool, visitors watch real
  recorded runs, no visitor input.
- Picked the run view after four design directions on a canvas: the
  Execution Explorer (D15).
- Set up the workflow: project board, milestones, CLAUDE.md, step list
  (STEPS.md), issues with acceptance criteria, Claude Code working each
  issue as a PR that I review and merge.
- Hardened the agent, one issue at a time: JSON fences (#2), tests (#5),
  tool errors back to Claude (#8), unknown tool (#11), every tool request
  answered (#7), loop cap (#15), cut-off replies (#18).
- Tracing: a plan first, then three PRs (#34–#36), so every run records
  every step, crossing and guard check.
- Wrote the nine scenarios (PR #39): five normal runs, four that break
  the agent on purpose.

**Broke**

- 401 again in a new terminal: VS Code was still carrying the revoked key
  from before .zshrc was cleaned. Fix: load_dotenv(override=True); quit
  and reopen VS Code.
- Debugger "Connection refused": stale session. Fix: full VS Code restart.
- The sample job had been missing its compensation line since a test the
  day before, so the "clean" run had quietly been taking the missing-info
  path. A PR review caught it.
- A save conflict in CHANGELOG.md: an open editor tab with old content
  would have overwritten six entries from merged PRs. Closed the tab
  without saving.

**Learned**

- A run can finish cleanly and still be the wrong run. The sample job lost
  its compensation line, and the "clean" run quietly became the
  missing-info run. Nothing failed, so only a review of what it actually
  did caught it.
- Hardening one issue at a time, each with a test that fails without the
  fix, means every guard has an issue, a PR and a test I can point to.

## 2026-11-13

**Did**

- Moved the hard rules into code (#26, PR #51): Claude extracts remote and
  pay; code applies the $180K floor and the remote rule before any rating
  call. Rules and guards are now different things on the page.
- Unknown stop reasons stop the run (#21, PR #52): fail closed.
- Fault injection (#46) and the recording script, then the first real
  recording: scenario 6, PASS (PR #58).
- Added LEARNINGS.md, and a docs audit that brought every doc in line
  with the code (#62, PR #63).

**Broke**

- Issue #31's fix landed on the wrong branch and reached `main` through an
  unrelated PR.
  - What happened: Claude Code was working on #31 in the main repo folder,
    with its changes not yet committed. In that same folder the branch was
    switched to `main`, then to a new `scenarios-data` branch. Git carries
    uncommitted changes across a branch switch, so the #31 work moved onto
    `scenarios-data`, and Claude Code committed it there without noticing the
    branch had changed.
  - How it reached `main`: the scenarios were committed on top and opened as
    PR #39, which merged with the #31 commit inside it. Claude Code had
    meanwhile rebuilt #31 cleanly in a separate worktree as PR #40, so the
    same change was now in two places.
  - How it was closed out: confirmed the commit that reached `main` was
    identical to #40's (same 9 files, same diff), closed #40 unmerged, and
    rewrote no history. A `git stash` in between reported "No local changes
    to save", because the work was already committed: nothing was lost. The
    D26 approval that only lived in #40 moved to the #32 PR.
  - Fix going forward: Claude Code always works in its own git worktree
    (`../agents-worktrees/<branch>`), never in the main repo folder. Added to
    CLAUDE.md in the #32 PR.

**Built: page v0 (#57, PR #60)**

- First time the whole idea works end to end: the recorded run of scenario 6
  plays in the browser, step by step, from `recordings/scenario-06.json`.
- First version stepped through all 47 events. Watching it, too many were
  passing checks ("Check: pass count"), and a dashed "next" arrow made the
  pass count check look like it sent the request.
- Review changes:
  - Passing checks flash their badge with a one-line explanation, written
    in STEPS.md.
  - Arrows show only what's crossing now.
  - evaluate_job's own Claude call is drawn Tools → Python → Claude, only
    while it happens.
  - Each tab has a one-line description.
  - Each request says what it carries.
  - The four cards are plain sentences.
- Kept 22 steps instead of folding to ~15, then made "Claude says it's done"
  a step too (23). It was hidden as a passing check, but it's routing: the
  reason the loop ends.
- Fonts ship with the page, since it may load nothing but its own files.

**Learned**

- A rule rejecting a posting and a guard catching a failure look alike in
  code, but they mean opposite things: one is the agent working, the other
  is something going wrong. Naming them differently made both the code and
  the page easier to read.
- A mockup is one frame. Making it real meant deciding everything between
  frames, and the one thing that could be misread was: the dashed "next"
  arrow looked like cause and effect.
- Docs drift quietly. By the audit, SPEC still described behavior from
  before two merged PRs. A test that checks a doc against the code is what
  keeps it true.

## 2026-11-14

**Did**

- Added `research_company` (#65, PR #66): stored company facts, and
  researched pay is used by the hard rules and labelled "base estimated
  from stored company data" (D34). Scenario 3 now chains two tools by
  Claude's own choice: research, then rate.
- Recorded all nine scenarios for real (#67, PR #68). Every one PASS.
- Added a CLAUDE.md rule (#69, PR #70): any PR that adds a tool or changes
  a description, schema, prompt or rubric re-runs every scenario, and
  expectations aren't edited just to make a run pass.

**Broke**

- Nothing in the agent. Adding `research_company` changed the path of
  scenarios 2 and 4, which the PR never touched: both now research the
  company before flagging. Re-running every scenario is the only reason it
  showed up.
- A commit landed on local `main` instead of a branch: `<N>` in a command
  was read by zsh as "read from a file called N", so the branch was never
  created. Nothing reached GitHub; the commit was moved to its branch.

**Learned**

- Tool descriptions are intent definitions. Two that overlap leave the
  order to the model. The new order was a good one, but nobody decided it.
- Testing an agent has two layers: unit tests prove the code, recorded
  scenarios prove the behavior. A single PASS shows a path happened, not
  that it always will.
