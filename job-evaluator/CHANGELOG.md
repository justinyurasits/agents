# Changelog — job-evaluator

Each merged PR adds a line under Unreleased. Cut a version when a set of changes is worth naming.

## Unreleased

- Strip markdown code fences (` ```json `) from the rating reply before parsing it, so `evaluate_job` no longer crashes when Claude fences its JSON (#2).
- Find response text by block type, not position (handles thinking blocks).
- Raise max_tokens to 2000 on both calls.
- Fix the final-answer check in `run_agent` to pick the text block by type, so a thinking block before the answer no longer crashes the agent (#4).
- Add `tests/` with fence-parsing tests for `strip_json_fences` and `evaluate_job`; no API calls, no key needed (#5).
- When a tool raises, send the error back to Claude as a `tool_result` with `is_error: true` instead of crashing; the run still finishes (#8).
- An unknown tool name now returns a clear `is_error` result naming the tool and listing the real ones, instead of a confusing `UnboundLocalError` or the previous tool's stale result (#11).
- Run every tool Claude asks for in one reply, not just the first, and send all the results back in one message (#7).
- Cap the agent loop at `MAX_PASSES = 10` outer API calls; if Claude never finishes, return "Stopped after 10 passes without finishing." instead of looping forever (#15).
- Handle replies cut off by the token limit (`MAX_TOKENS = 2000`, one constant for both calls): the main loop stops with a clear message, and a cut-off grader reply is reported as cut off rather than as invalid JSON (#18).
- Rewrite docs/SPEC.md as the agent's design doc (overview, components, loop, what Claude sees, guards table, rules in code vs prompt, trace placeholder, known limits); fix the run instructions in agent.py's docstring and drop the nonexistent candidate profile from STEPS.md step 1 (#23).
- Add `# STEP: <step_id>` markers to agent.py and `code_refs.py` to look up each step's code and current line number; STEPS.md gets step ids, four error-case steps (tool fails, unknown tool, reply cut off, too many passes), and no more hard-coded line numbers (#27).
- Record a trace of each run: `tracing.Recorder` writes one event per step of the outer loop (API request and response with tokens, tool calls and results, messages before and after) to `traces/<scenario>-<timestamp>.json`; `run_agent` takes an optional recorder and behaves the same without one (#28).
- Trace `evaluate_job`'s grader call (with `parent` = its tool call) and every guard check (pass count, stop reason, max_tokens in the loop and the grader, tool exists, tool succeeded); add step E5 `grader_cut_off`; every event has `injected: false` (#29).
- When the call to Claude itself fails (network, timeout, rate limit, overloaded, server error, bad key), stop the run and return a message naming the error type and status instead of crashing; new step E6 `api_call_failed` and an `api_call_succeeded` guard in the trace (#30).
- Restore compensation in the sample job. Used a fictional company.

## 0.1.0 — 2026-11-11

- First version: agent loop with `evaluate_job` and `flag_for_review` tools, step-by-step trace printed to the terminal.
- Load the API key from `.env`.
- Strip markdown code fences (```json) from the rating reply before parsing it, so `evaluate_job` no longer crashes when Claude fences its JSON (#2).
