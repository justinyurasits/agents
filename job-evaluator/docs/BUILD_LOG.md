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

**Broke**

- Ran `python3 -m venv .venv` and `pip install -r requirements.txt` from the repo root instead of `job-evaluator/`. Error: `Could not open requirements file`. Fix: deleted the root `.venv`, `cd job-evaluator`, recreated it there.
- Note: `(base)` in the prompt is Anaconda's base environment. `(.venv)` takes priority; `conda deactivate` if package errors show up.

## 2026-11-12

- 401 again in a new terminal: VS Code was still carrying the revoked key from
  before .zshrc was cleaned. Fix: load_dotenv(override=True); quit and reopen VS Code.
- Debugger "Connection refused": stale session. Fix: full VS Code restart.

## **Learned** _(write in your own words)_

- **Next**

- First successful run; check `git status` shows no `.env`.
- Set up the project board and write issues #1–8 with acceptance criteria.
- Take issue #1 through the full branch → PR → merge loop.
