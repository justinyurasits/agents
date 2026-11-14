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
- When Claude finishes with no text in its reply (e.g. only thinking), return "Claude finished without writing a final answer." instead of crashing with `StopIteration`; new step E7 `no_final_answer` and a `final_text_present` guard in the trace (#31).
- Add the scenario set: `scenarios/scenarios.json` (nine fictional scenarios, 5 normal + 4 break-the-agent, D21) and `docs/SCENARIOS.md` (PR #39).
- Check the grader's JSON before returning it: a rating outside STRONG / WORTH REVIEWING / IGNORE, missing or non-list `reasons`, or JSON that isn't an object becomes an `is_error` tool result naming the problem; new step E8 `invalid_grade` and a `grade_valid` guard in the trace (#32).
- Accept the grader's rating in any case (`"strong"`, `"Worth Reviewing"`) and return it in uppercase (#42).
- Annotate agent.py as a guided tour: a map of the loop, `(terminal only)` / `(trace only)` tags on every print and recording line, a `GUARD (E<n> …)` label on every guard, examples of what `messages` and content blocks look like, and notes on Python idioms. Terminal output now uses step ids (`[send_to_claude]`) instead of `[step N]` (#44).
- Add fault injection (`faults.py`; `python agent.py --fault <name>` or `--scenario <id>`): tool_fails, unknown_tool, runaway_loop (pass cap lowered to 2) and reply_cut_off, each recorded as `fault_injected` with `injected: true` on its effects; cut-off and cap messages now give the limit actually used (#46).
- Restore compensation in the sample job. Used a fictional company.
- Scenario 8's visitor text now says the cap was lowered only for the demo, and that in real runs Claude usually stops retrying on its own (#49).
- Move the $180K floor and the remote rule from the grader's prompt into code: `evaluate_job` screens first and returns IGNORE without a rating call; the grader now answers only "does this role build hands-on AI experience?" (yes → STRONG, no → WORTH REVIEWING). The screens are a normal step, `hard_screen` ("Code checks your hard rules"), recorded as rule events, not guards; agent.py labels rules `RULE (<step_id>)` and guards `GUARD (E<n> …)`, checked by `test_annotations.py` (#26).
- Stop the run when Claude's reply has a stop reason the agent doesn't handle (e.g. `refusal`), instead of sending an empty tool-results message the API rejects. New guard step E9 `unexpected_stop` (#21).
- Add `record.py`: runs a scenario for real, saves it to `recordings/scenario-<id>.json`, checks the tools and outcome against the scenario's new `expect` field, prints PASS or MISMATCH (a mismatch is still saved, marked), and regenerates SCENARIOS.md from the JSON. `agent.py --scenario 4` now joins its two postings instead of passing a list (#53).
- Add the first recording, `recordings/scenario-06.json`: scenario 6, the tool fails and the agent recovers (PR #58).
- Add `design/explorer-d1-mockup.html`, the design reference for page v0 (PR #59).
- Add page v0 in `site/`: replays `recordings/scenario-06.json` in the Execution Explorer layout (map, guard badges, four questions, timeline, explanation, inspector tabs, playback). It steps through 23 page steps, not 47 events: passing guard checks flash their badge with a one-line explanation instead, while caught checks and step 9 (Claude says it's done) stay steps. Explanations and check lines come from `site/steps.json`, generated from STEPS.md (new "Checks" section) by the new `build_steps.py`; Inter and JetBrains Mono ship in `site/fonts/` (#57).
- Docs audit: BRIEF.md lists the nine scenarios and the six-section page, and its Decided list covers every approved decision; D22–D25 and D27 marked Approved; new D33 (page structure); SPEC.md gets a Design principles section, the E-step for each guard, a separate "Defensive handling (always on, not guards)" table for fence stripping, finding text by type and answering every tool request, and fixes to the return values, the loop and the terminal output; BRIEF's "Design principle" heading becomes "The four questions (page design rule)"; both READMEs' status and docs tables updated; every scenario gets `"summary": null` (#62).
- Add the `research_company` tool: looks up stored demo facts about a company (`data/companies.json`, moved out of scenarios.json), including typical base pay for the role level; an unknown company is `found: false`, not an error. When `evaluate_job` gets the researched pay, the hard rules apply as usual and the reasons say "base estimated from stored company data". New step 7c `research_company`. Scenario 3 now passes; scenarios 2 and 4 now research the company with no pay listed first, so their expected tools include `research_company` (#65).

## 0.1.0 — 2026-11-11

- First version: agent loop with `evaluate_job` and `flag_for_review` tools, step-by-step trace printed to the terminal.
- Load the API key from `.env`.
- Strip markdown code fences (```json) from the rating reply before parsing it, so `evaluate_job` no longer crashes when Claude fences its JSON (#2).
