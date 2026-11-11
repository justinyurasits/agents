# Changelog — job-evaluator

Each merged PR adds a line under Unreleased. Cut a version when a set of changes is worth naming.

## Unreleased

## 0.1.0 — 2026-11-11

- First version: agent loop with `evaluate_job` and `flag_for_review` tools, step-by-step trace printed to the terminal.
- Load the API key from `.env`.

## 2026-11-11 — Repo setup and first run

**Did**

- Walked through the agent loop step by step: tool definitions vs functions, dispatch,
  stop_reason, the messages list as memory, tool_use_id pairing, the inner Claude call
  in evaluate_job.
- Created the `agents` repo (private, Python .gitignore) with job-evaluator/.
- Set up a virtual environment and .env; added load_dotenv().
- First successful end-to-end run: 3 API calls, evaluate_job requested and dispatched,
  tool_result returned, end_turn.

**Broke**

- Created the venv and ran pip from the repo root, not job-evaluator/.
  Error: "Could not open requirements file". Fix: deleted root .venv, recreated it in
  job-evaluator/.
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
- **Next**

- Test: remove compensation from the test job and see which tool Claude picks.
- Set up the project board; write issues #1–8 with acceptance criteria.
- Take issue #1 (markdown fences) through branch → PR → merge.

- **Unreleased**
- Find response text by block type, not position (handles thinking blocks).
- Raise max_tokens to 2000 on both calls.
