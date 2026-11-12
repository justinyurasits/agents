# Changelog — job-evaluator

Each merged PR adds a line under Unreleased. Cut a version when a set of changes is worth naming.

## Unreleased

- Strip markdown code fences (```` ```json ````) from the rating reply before parsing it, so `evaluate_job` no longer crashes when Claude fences its JSON (#2).
- Find response text by block type, not position (handles thinking blocks).
- Raise max_tokens to 2000 on both calls.
- Fix the final-answer check in `run_agent` to pick the text block by type, so a thinking block before the answer no longer crashes the agent (#4).
- Add `tests/` with fence-parsing tests for `strip_json_fences` and `evaluate_job`; no API calls, no key needed (#5).
- When a tool raises, send the error back to Claude as a `tool_result` with `is_error: true` instead of crashing; the run still finishes (#8).

## 0.1.0 — 2026-11-11

- First version: agent loop with `evaluate_job` and `flag_for_review` tools, step-by-step trace printed to the terminal.
- Load the API key from `.env`.
