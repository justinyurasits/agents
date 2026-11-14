# job-evaluator — Build log

Dated working log. What I did, what broke, what I learned. Write it the same day.

---

## 2026-11-11 — Repo setup and first run

**Did**

- Walked through the agent loop step by step: tool definitions vs functions, dispatch, `stop_reason`, the messages list as memory, `tool_use_id` pairing, the inner Claude call in `evaluate_job`.
- Created the `agents` repo (private, Python .gitignore), added `job-evaluator/` with `agent.py`, `requirements.txt`, `.env.example`.
- Set up a virtual environment and `.env`; added `load_dotenv()` so the key loads from `.env`.
- - Removed compensation from the test job: Claude chose flag_for_review instead of
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
- NameError: name '**\_\_**' is not defined. Pasted the fill-in-the-blank template
  literally.

**Learned**

- API key in .env needs to have no leading spaces.
- High level walkthrough of the script, including the tools, the agent loop, and the basic interactions between.

## 2026-11-12

- 401 again in a new terminal: VS Code was still carrying the revoked key from
  before .zshrc was cleaned. Fix: load_dotenv(override=True); quit and reopen VS Code.
- Debugger "Connection refused": stale session. Fix: full VS Code restart.

## **Learned** _(write in your own words)_

- **Next**

- First successful run; check `git status` shows no `.env`.
- Set up the project board and write issues #1–8 with acceptance criteria.
- Take issue #1 through the full branch → PR → merge loop.
- I deleted the compensation from the job and the code was running without that all day.

## 2026-11-13

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

**Learned** _(draft, rewrite in your own words)_

- A mockup is one frame. Making it real meant deciding everything between
  frames.
- If a picture can be misread, it will be: the "next" arrow looked like cause
  and effect.
- What the trace records and what a person needs to see are different lists.
  Choosing the steps is a teaching decision, not a data one.

