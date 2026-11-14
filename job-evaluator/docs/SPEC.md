# job-evaluator — Design doc

How the agent works and why. Living document: update it in the same PR as any change to behavior, tools, or prompts. Every statement here should match [`agent.py`](../agent.py) as it is on `main`. If they disagree, the code wins and this doc has a bug.

Issue links point to [the repo's issues](https://github.com/justinyurasits/agents/issues). Decisions (D17, D18, …) are in [DECISIONS.md](DECISIONS.md).

---

## Design principles

The six principles the page demonstrates (D33), and where each one shows in the code or a run:

| Principle | Shown in the code | Watch it |
|---|---|---|
| **The model for judgment, code for rules** | `hard_screens` with `MIN_BASE` and `REQUIRE_REMOTE`, and `RATING_FOR_ANSWER`, in [`agent.py`](../agent.py); the grader's `RUBRIC` asks only the one question that needs judgment (section 6, D28) | Scenario 5: a rule in code rejects the posting before the grader is asked |
| **A guard turns a crash into information the model can act on** | The `try / except` around each tool in `run_agent` (`# STEP: tool_failed`, E1) sends the error back as an `is_error` tool result (section 5, D18) | Scenario 6: the grader's reply is broken, the error goes back to Claude, and Claude retries |
| **Claude decides; Python executes** | `run_agent`: Python calls Claude, reads `stop_reason`, and runs the tools; step 4 (`claude_decides`) has no code because it happens on Anthropic's servers (section 3, [STEPS.md](STEPS.md)) | Any run |
| **The conversation is the memory** | `messages` in `run_agent`: sent whole on every call (`send_to_claude`), and appended at `save_turn` and `results_back` (section 3) | Scenario 1: messages grows from 1 to 3 between the two calls |
| **Tool descriptions steer the agent** | The `description` of each tool in `tools`, sent to Claude #1 on every call (section 4) | Scenario 2: no compensation, so Claude picks `flag_for_review` |
| **Show what happened; label everything else** | `tracing.py` records real runs; `faults.py` marks what it injected (`injected: true`); the page labels its own text "Written for this page" and shows Claude's words only under "Claude's response" (section 7 and 8, D27, D31) | The page itself |

---

## 1. Overview

Given one job posting as text, the agent returns a short written verdict:

- a **rating** (STRONG / WORTH REVIEWING / IGNORE) with reasons, when the posting has enough information, or
- a **flag for manual review**, when key information (compensation, remote status) is missing or unclear.

How a posting is rated (#26). Fixed rules are checked in code, and only the one question that needs judgment goes to the grader:

| Rating | Meaning | Decided by |
|---|---|---|
| IGNORE | not remote, **or** lowest base below $180K | code (`hard_screens`), before any rating call |
| STRONG | passes both, and the grader answers **yes** to "does this role build hands-on AI experience?" | the grader's answer, mapped in code |
| WORTH REVIEWING | passes both, and the grader answers **no** | the grader's answer, mapped in code |

A screen that can't be checked (remote status not given, or pay that isn't a readable yearly salary, like "competitive") is skipped, never failed, and the trace says so.

It's a small, deliberately visible agent. It was built to learn and demonstrate the agent loop, so every step prints a line to the terminal.

**Run it:** `python agent.py` from `job-evaluator/` (setup in [README.md](../README.md)). It evaluates a built-in sample posting (Northwind Labs, remote, $200K–$240K), prints each step and the final answer, and writes a trace file to `traces/` (section 7).

Other ways to run it: `python agent.py --scenario <id>` runs a scenario from `scenarios/scenarios.json` (its posting, and its fault if it has one), and `python agent.py --fault <name>` forces one failure on purpose (see [Faults injected on purpose](#faults-injected-on-purpose)).

**Cost of a typical run:** 3 API calls when the posting gets rated (2 outer + 1 inside `evaluate_job`), 2 when it's flagged (`flag_for_review` makes no API call) or screened out by a hard rule (no grader call). Researching the company first (`research_company`, no API call) adds one outer call: 4 for a researched rating, 3 for research then a flag.

**What `run_agent` can return.** It always returns a string, one of the six kinds below, and callers can only tell them apart by the text:

| Case | Returned string |
|---|---|
| Claude finished (`end_turn`) | Claude's final answer (the reply's first text block) |
| Claude finished but wrote no text (e.g. only a thinking block) | `"Claude finished without writing a final answer."` |
| Claude's reply hit the token limit | `"Claude's reply was cut off (hit the max_tokens limit of 2000)."` |
| 10 passes without finishing | `"Stopped after 10 passes without finishing."` |
| The call to Claude itself failed (network, rate limit, overloaded, bad key) | `"Couldn't get a reply from Claude: <ErrorType> (status <code>). The run stopped."` (no status for network errors) |
| Claude stopped for a reason the agent doesn't handle (e.g. `refusal`) | `"Claude stopped for a reason this agent doesn't handle (stop_reason 'refusal'). The run stopped."` |

What it doesn't handle is in [Known limits](#9-known-limits).

---

## 2. Components

Everything is in one file, [`agent.py`](../agent.py). Top to bottom:

| Piece | What it is |
|---|---|
| `client`, `MODEL` | The Anthropic client (key from `.env`, loaded with `override=True`) and the model, `claude-sonnet-5-5`. |
| `MAX_PASSES = 10` | Most outer API calls per run. See the loop cap guard. |
| `MAX_TOKENS = 2000` | Longest reply Claude may write. Used by **both** API calls. |
| `tools` | The three tool definitions (name, description, input schema) sent to Claude on every outer call. The descriptions are how Claude decides which tool to use. |
| `MIN_BASE = 180_000`, `REQUIRE_REMOTE = True` | The hard rules, as named constants. |
| `lowest_base(text)`, `hard_screens(remote, compensation)` | Pure functions. `lowest_base` reads the lowest yearly base from Claude's compensation text (`"$140,000–$165,000"` → 140000; `"180-220k"` → 180000; `"competitive"`, `"$90/hr"` → `None`). `hard_screens` returns one result per rule: passed, failed, or skipped. |
| `RUBRIC` | System prompt for the grader call inside `evaluate_job`: the one judgment question, plus "Respond with JSON only: `{"answer": "yes" or "no", "reasons": [...]}`". It doesn't mention pay or location. |
| `RATING_FOR_ANSWER` | `{"yes": "STRONG", "no": "WORTH REVIEWING"}`: code, not the grader, turns the answer into the rating. |
| `strip_json_fences(text)` | Removes a surrounding ```` ``` ```` / ```` ```json ```` fence from the grader's reply. Pure string function. |
| `grade_problem(grade)` | A pure function that says what's wrong with the grader's parsed JSON (or `None`). A rule in code, not the prompt. |
| `evaluate_job(...)` | Tool. If the pay is researched (below), uses it and adds `"base estimated from stored company data"` to the reasons. Runs the hard screens first; if one fails, returns `{"rating": "IGNORE", "reasons": [...]}` with no API call. Otherwise makes its **own** Claude call with `RUBRIC` (no tools, no loop), parses the JSON reply, checks it with `grade_problem`, and returns `{"rating", "reasons"}` (or raises `ValueError` naming the problem). |
| `flag_for_review(...)` | Tool. Plain Python, no API call. Returns `{"status": "flagged", "company", "role_title", "missing_info"}`. |
| `research_company(company, role_level)`, `COMPANIES_FILE` | Tool (#65). Plain Python, no API call. Looks the company up in [`data/companies.json`](../data/companies.json), stored demo data (D14), ignoring case. Known: `{"found": true, "company", "size", "stage", "role_level", "typical_base_for_level", "note", "source": "stored demo data"}`; `typical_base_for_level` is the pay for the stored level whose word appears in `role_level` ("principal" in "Principal Product Manager"), or `null` with `levels_on_file`. Unknown: `{"found": false, "source": "stored demo data"}`, a normal result, not an error. |
| `SYSTEM_PROMPT` | Claude #1's system prompt, a constant so the call and the trace use the same text. |
| `run_agent(job_text, recorder=None, fault=None)` | The agent loop (next section). With a `Recorder`, it writes a trace (section 7). With a `Fault`, it fails on purpose in one way. |
| `SAMPLE_JOB`, `choose_run(argv)` | The built-in posting, and the command line (`--scenario`, `--fault`) turned into what to run. |
| `scenario_job_text(scenario)` | A scenario's posting, or its postings joined with a `---` line (`POSTING_SEPARATOR`). Used by `choose_run` and `record.py`. |
| `if __name__ == "__main__"` | Runs `choose_run`, then `run_agent`, and writes the trace. |

Next to it, [`code_refs.py`](../code_refs.py) finds the code each step points to. `agent.py` carries a `# STEP: <step_id>` comment directly above the code for each step in [STEPS.md](STEPS.md), and `code_ref(step_id, source)` returns that code's current line number and full statement (D23). Nothing stores line numbers by hand, so editing `agent.py` can't make a reference go stale.

There are two Claude roles, and they never mix:

- **Claude #1, the agent** (outer calls in `run_agent`): sees the posting and the tools, and decides what to do.
- **Claude #2, the grader** (inner call in `evaluate_job`): sees one job summary and the rubric, and answers yes or no. Only postings that pass the hard screens get this far. Its conversation is thrown away when the tool returns.

Tests live in [`tests/`](../tests/) (standard-library `unittest`, D17). Run them from `job-evaluator/` with `python -m unittest discover -s tests -v`. They use a fake Claude client, so they make no API calls and need no key. The page's browser tests ([`test_browser.py`](../tests/test_browser.py), #84, D38) also need Playwright and Chromium (`requirements-dev.txt`); without them they're skipped.

---

## 3. The loop

The step-by-step walkthrough, written for someone who has never seen an agent, is in **[STEPS.md](STEPS.md)**. This section is the short technical version.

`run_agent` starts with one user message ("Evaluate this job posting: …") and then makes up to `MAX_PASSES` **passes**. A pass is one outer API call plus what follows it:

1. Send the system prompt, `tools`, and the **whole** `messages` list to Claude. Claude keeps no memory between calls; this list is the memory. If the call itself fails with an API error, return a message naming the error. **Done.**
2. Read the reply's `stop_reason`:
   - `end_turn` → return the reply's first **text** block (found by type, because a thinking block can come first), or the no-answer message if it has none. **Done.**
   - `max_tokens` → return the cut-off message. Nothing in the reply is acted on. **Done.**
   - `tool_use` → go on to step 3.
   - anything else (`refusal`, `pause_turn`, …) → return the unhandled-stop message. Nothing in the reply is acted on (D29). **Done.**
3. Append Claude's full reply to `messages` as the assistant turn.
4. Run **every** `tool_use` block in the reply, in order, each inside its own `try / except`.
5. Append **one** user message holding one `tool_result` per request, each carrying that request's `tool_use_id`.
6. Start the next pass.

If all 10 passes are used without `end_turn`, `run_agent` returns the cap message.

Tools run in order, not in parallel. The dispatch is an `if / elif` on the tool name inside the loop (D20).

---

## 4. What Claude sees

| | Claude #1: agent (outer call) | Claude #2: grader (inside `evaluate_job`) |
|---|---|---|
| **System prompt** | `"You help Justin triage job postings. Use the tools provided."` | `RUBRIC` (the one question + "Respond with JSON only: `{"answer": "yes" or "no", "reasons": [...]}`") |
| **Tools** | `evaluate_job`, `flag_for_review`, `research_company` (names, descriptions, input schemas) | none |
| **Messages** | The posting, then every assistant turn and tool result so far | One user message: `Company / Role` lines, then the description. Remote status and pay aren't sent separately: the hard screens already used them (#26). |
| **Limit** | `max_tokens = MAX_TOKENS` (2000) | `max_tokens = MAX_TOKENS` (2000) |

Claude #1 never sees `RUBRIC`. Claude #2 never sees the tool descriptions or the outer conversation.

**Tools as Claude #1 sees them:**

| Tool | Description (when to use it) | Inputs |
|---|---|---|
| `evaluate_job` | "Rate a job posting against Justin's criteria. Use when the posting has enough information to rate: company, role, location/remote status, and compensation." | `company`, `role_title`, `job_description` (required); `location`, `remote` (boolean), `compensation` |
| `flag_for_review` | "Flag a posting for manual review. Use when key information (compensation, remote status) is missing or ambiguous, so the job can't be rated reliably." | `company`, `role_title`, `missing_info` (all required) |
| `research_company` | "Look up stored facts about a company: size, stage, and typical base pay for a role level. Use when a posting doesn't list compensation." | `company`, `role_level` (both required) |

**Tool results as Claude #1 sees them:**

- Success: `content` is the tool's return value as JSON. There's no `is_error` field.
- Failure: `content` is `"<ExceptionType>: <message>"` and `is_error: true`. For example, `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` or `ValueError: Unknown tool 'search_web'. Available tools: evaluate_job, flag_for_review, research_company.`

What Claude does after an error (retry, switch tools, or explain the failure) is Claude's decision, not the code's (D18). In live runs it has retried once and then explained the failure without inventing a rating. That's observed behavior, not a guarantee.

---

## 5. Guards and error handling

A **guard** catches a failure: a crash, a hang, or bad data. Each one is labelled `GUARD (E<n> <step_id>)` in agent.py and has an error step in STEPS.md (E1–E9). In order of their error steps:

| Guard | Step (`GUARD` label in agent.py) | Catches | Does | Issue | Test |
|---|---|---|---|---|---|
| **Tool errors** (`try / except Exception` around each tool) | E1 `tool_failed` | Any exception from a tool: bad JSON from the grader, bad arguments, the grader's own API call failing | Sends `"<Type>: <message>"` back as a `tool_result` with `is_error: true`; the run continues. Ctrl-C still stops the script. | [#8](https://github.com/justinyurasits/agents/issues/8), D18 | [`test_tool_errors.py`](../tests/test_tool_errors.py): `ToolErrorTest` |
| **Unknown tool** (`else` branch of the dispatch) | E2 `unknown_tool` | Claude asks for a tool name that isn't defined | Raises `ValueError("Unknown tool '<name>'. Available tools: …")`, which the tool-errors guard (E1) turns into `is_error`. The list comes from `tools`, so it stays in sync. | [#11](https://github.com/justinyurasits/agents/issues/11), D19 | [`test_tool_errors.py`](../tests/test_tool_errors.py): `UnknownToolTest` |
| **Cut-off reply, main loop** (`stop_reason == "max_tokens"` in `run_agent`) | E3 `reply_cut_off` | Claude #1's reply hit `MAX_TOKENS` | Returns `"Claude's reply was cut off (hit the max_tokens limit of 2000)."` Nothing in the reply runs, not even a tool request. | [#18](https://github.com/justinyurasits/agents/issues/18), D22 | [`test_max_tokens.py`](../tests/test_max_tokens.py): `test_cut_off_main_loop_reply_*` |
| **Loop cap** (`for … in range(1, MAX_PASSES + 1)`) | E4 `pass_cap` | Claude never says `end_turn`, e.g. it keeps retrying a tool that keeps failing | Stops after 10 outer calls and returns `"Stopped after 10 passes without finishing."` The grader's call doesn't count toward the 10. | [#15](https://github.com/justinyurasits/agents/issues/15) | [`test_loop_cap.py`](../tests/test_loop_cap.py): `LoopCapTest` |
| **Cut-off reply, grader** (`stop_reason == "max_tokens"` in `evaluate_job`) | E5 `grader_cut_off` | The grader's reply hit `MAX_TOKENS` | Raises `RuntimeError("The grader's reply was cut off …")` **before** parsing, so Claude gets "cut off" as an `is_error` result, not "invalid JSON". | [#18](https://github.com/justinyurasits/agents/issues/18), D22 | [`test_max_tokens.py`](../tests/test_max_tokens.py): `test_cut_off_grader_reply_is_reported_as_cut_off_not_invalid_json` |
| **Outer API call fails** (`try / except anthropic.APIError` around the call in `run_agent`) | E6 `api_call_failed` | Network error, timeout, rate limit (429), overloaded (529), server error, bad key (401) on Claude #1's call | Returns `"Couldn't get a reply from Claude: <ErrorType> (status <code>). The run stopped."` Only the error's type and status go in the message, never the error text, request, or headers. (The grader's own API errors are already tool errors, #8.) | [#30](https://github.com/justinyurasits/agents/issues/30), D26 | [`test_api_errors.py`](../tests/test_api_errors.py): `OuterApiErrorTest`, `TraceOfApiErrorTest` |
| **No final answer** (`if answer is None` after `end_turn` in `run_agent`) | E7 `no_final_answer` | Claude says `end_turn` but the reply has no text block (only thinking, or empty) | Returns `"Claude finished without writing a final answer."` instead of crashing with `StopIteration`. Several text blocks still return the first. | [#31](https://github.com/justinyurasits/agents/issues/31) | [`test_final_text.py`](../tests/test_final_text.py): `NoTextBlockTest`, `TraceTest` |
| **Grade check** (`grade_problem` + `if problem: raise` in `evaluate_job`) | E8 `invalid_grade` | Grader JSON that parses but isn't an answer: not an object, `answer` missing or not yes / no (any case is accepted), `reasons` missing or not a list of strings | Raises `ValueError` naming exactly what's wrong, which goes back to Claude as an `is_error` tool result (#8). A valid answer becomes `{"rating", "reasons"}`; other keys aren't passed on. | [#32](https://github.com/justinyurasits/agents/issues/32), [#42](https://github.com/justinyurasits/agents/issues/42), [#26](https://github.com/justinyurasits/agents/issues/26) | [`test_grade_validation.py`](../tests/test_grade_validation.py) |
| **Unhandled stop reason** (`if response.stop_reason != "tool_use"` in `run_agent`, after the cut-off check) | E9 `unexpected_stop` | A reply whose `stop_reason` isn't `end_turn`, `max_tokens` or `tool_use`: `refusal`, `stop_sequence`, `pause_turn`, `model_context_window_exceeded` | Returns `"Claude stopped for a reason this agent doesn't handle (stop_reason 'refusal'). The run stopped."` Nothing in the reply runs, not even a tool request, and no further request is sent. Before this, the reply went on to the dispatch, which sent a user message with empty `content` that the API rejects. | [#21](https://github.com/justinyurasits/agents/issues/21), D29 | [`test_unexpected_stop.py`](../tests/test_unexpected_stop.py) |

### Defensive handling (always on, not guards)

These never catch a failure; they prevent one. They run on every reply, the same way whether or not anything was wrong, so they have no `GUARD` label, no error step, and no guard event in the trace.

| Handling | Prevents | Does | Issue | Test |
|---|---|---|---|---|
| **Fence stripping** (`strip_json_fences`, in `evaluate_job`) | A `JSONDecodeError` when the grader wraps its JSON in ```` ``` ```` or ```` ```json ```` fences | Strips the fence before `json.loads` | [#2](https://github.com/justinyurasits/agents/issues/2) | [`test_fences.py`](../tests/test_fences.py): `StripJsonFencesTest`, `EvaluateJobTest` |
| **Find text by type** (`evaluate_job` and the `end_turn` return) | A crash when a thinking block comes before the text block | Picks the first block with `type == "text"`, never `content[0]` | [#4](https://github.com/justinyurasits/agents/issues/4) (exit check). The `evaluate_job` fix came earlier, before issues were used (commit `3fbd8e6`). | [`test_fences.py`](../tests/test_fences.py): `test_each_reply_shape_with_thinking_block_first`. The fake replies in the other test files also put a thinking block first, so every test that checks `run_agent`'s final answer covers the exit check too. |
| **Every tool request answered** (loop over `tool_use` blocks) | The API rejecting the next call when Claude asks for several tools in one reply and one goes unanswered | Runs each one and returns all results in **one** user message with matching `tool_use_id`s. The API rejects the next call if any request goes unanswered. | [#7](https://github.com/justinyurasits/agents/issues/7), D20 | [`test_multiple_tools.py`](../tests/test_multiple_tools.py): `MultipleToolUseTest` |

The tests for fence stripping (#5) and for #7, #8, #11, #15, #18, #30, #31, #32 and #21 were each also run against the code from before the guard or handling existed, to confirm they fail without it. The PRs that added them show that run.

---

## 6. Rules in code vs prompt

The repo's rule (CLAUDE.md) is that **deterministic rules belong in code, not prompts.** A prompt can be ignored or misread; code can't. Judgment calls belong to Claude.

| Rule | Lives in | Should live in | Notes |
|---|---|---|---|
| $180K base floor | Code (`MIN_BASE`, `hard_screens`) | Code | Moved from the prompt in #26. |
| Must be remote | Code (`REQUIRE_REMOTE`, `hard_screens`) | Code | Moved from the prompt in #26. Claude #1 still reads remote status from the posting; code applies the rule. |
| Builds hands-on AI experience | Prompt (`RUBRIC`) | Prompt | Needs judgment. The grader answers yes or no. |
| Answer → rating (yes: STRONG, no: WORTH REVIEWING) | Code (`RATING_FOR_ANSWER`) | Code | #26. |
| Rate vs flag (is enough info present?) | Tool descriptions, decided by Claude #1 | Prompt | Judgment about an unstructured posting. |
| Grader reply format (JSON) | Prompt (`RUBRIC`), parsed and checked in code | Both | The prompt asks for JSON; code strips fences, parses it, and checks the rating and reasons (`grade_problem`, #32). |
| The yes/no answer values | Prompt (`RUBRIC`) **and** code (`RATING_FOR_ANSWER`) | Both | The prompt tells the grader what to answer; the code rejects anything else. |
| Max passes, max tokens | Code (`MAX_PASSES`, `MAX_TOKENS`) | Code | |
| Which tool names exist | Code (`tools` + the dispatch) | Code | |

The floor and remote rules were moved into code by [#26](https://github.com/justinyurasits/agents/issues/26) (D28), which closes D6.

**Researched pay (#65, D34).** When a posting lists no pay, Claude can call `research_company` and pass the stored typical base on to `evaluate_job`. Code, not Claude, decides whether the pay `evaluate_job` received is researched. `run_agent` remembers the pay each `research_company` call found in this run, by company. `evaluate_job` treats its pay as researched when research found pay for the same company and Claude passed that pay (same lowest base) or no readable pay at all; then the hard rules use the researched pay as usual, and the reasons end with `"base estimated from stored company data"`, on IGNORE and on a rating alike. Pay Claude read from the posting is never labelled, and research on one company never labels another's pay.

**Rules are not guards.** A guard (section 5) catches a failure: a crash, a hang, or bad data. A rule applies one of Justin's decisions, and a posting that fails one is the agent working as intended. So the hard screens are a normal step, `hard_screen` (STEPS.md 7a), not an E-step; agent.py labels them `RULE (hard_screen)`, not `GUARD`; and the trace records them as rule events, never as caught guards (section 7).

| Rule | Fails when | Then | Can't be checked when | Test |
|---|---|---|---|---|
| **Remote** (`REQUIRE_REMOTE`) | Claude #1 sent `remote: false` | `evaluate_job` returns `{"rating": "IGNORE", "reasons": ["not remote"]}` with no grader call | `remote` wasn't sent, or isn't true/false: skipped | [`test_hard_screens.py`](../tests/test_hard_screens.py) |
| **Base floor** (`MIN_BASE`) | the lowest base in the range is under $180,000 | same, with `"base below $180K floor"`; both reasons when both fail | the pay isn't a readable yearly salary ("competitive", "$90/hr"): skipped | [`test_hard_screens.py`](../tests/test_hard_screens.py) |

---

## 7. Trace format

Every recorded run writes a **trace**: one JSON event per step, which the page (D15) replays. Built for [#1](https://github.com/justinyurasits/agents/issues/1) in three parts: step markers ([#27](https://github.com/justinyurasits/agents/issues/27)), the recorder and core events ([#28](https://github.com/justinyurasits/agents/issues/28)), and inner calls plus guard events ([#29](https://github.com/justinyurasits/agents/issues/29)). Format decisions: D24 (events), D25 (guards).

### How a trace is made

[`tracing.py`](../tracing.py) has a `Recorder`. `run_agent(job_text, recorder=None, fault=None)` calls it at each step. With no recorder it uses `NullRecorder`, which records nothing, so the agent behaves exactly the same. `python agent.py` records the sample run as scenario `clean` and writes **`traces/<scenario>-<YYYYMMDD-HHMMSS>.json`**. `traces/` is gitignored. Runs used on the page are made by `record.py` and saved to `recordings/`, which is committed (see [Recording scenarios](#recording-scenarios-recordpy)).

### The file

| Key | What |
|---|---|
| `trace_version` | `1` |
| `scenario`, `started_at` | Scenario name; UTC start time |
| `git_commit`, `git_dirty` | The commit that ran, and whether `job-evaluator/` had uncommitted changes. Lets the page link code references to the exact version. |
| `fault` | The injected fault's name, or `null` |
| `model`, `limits` | `claude-sonnet-5-5`; `{"max_passes": 10, "max_tokens": 2000}` |
| `tools` | The full tool definitions, stored once |
| `events` | One per step, in order (below) |
| `result` | `{"ended_by": "end_turn" \| "max_tokens" \| "pass_cap" \| "api_error" \| "no_text" \| "unexpected_stop", "text": …}`: what `run_agent` returned |

### Events

**Every event has every key**, `null` when it doesn't apply: `id` (`e1`, `e2`, …), `seq`, `pass` (`0` = before the loop), `step_id` (from [STEPS.md](STEPS.md)), `actor` (`python`, `claude`, or `tool`), `crossing` (`{from, to, kind}` or `null`), `payload`, `messages_before`, `messages_after`, `code` (`{file, marker, line, lines}` from `code_refs.py`; `null` for `claude_decides`), `parent` (the `tool_call` event an event happened inside, else `null`), `tokens`, `guard`, `injected` (`true` only for what an injected fault did or caused; see below).

| Step | `crossing.kind` | `payload` |
|---|---|---|
| `agent_starts` | — | `job_text` |
| `conversation_setup`, `save_turn`, `results_back` | — | `null`; `messages_before` / `messages_after` hold the conversation before and after (each adds exactly one message) |
| `send_to_claude` | `api_request` (python → claude) | `model`, `max_tokens`, `system`, `tools` (names only), `messages` (as sent) |
| `claude_decides` | `api_response` (claude → python) | `stop_reason`, `content` (every block: thinking, text, tool_use); `tokens` = `{input, output}` |
| `run_tools` | `tool_call` (python → tool) | `tool`, `tool_use_id`, `arguments`. Only for a tool that exists. |
| `inner_grader` | `inner_api_request` (tool → claude) | Same shape as `api_request`, with `system` = `RUBRIC` and `tools` = `[]`. `parent` = the `evaluate_job` tool_call. |
| `inner_grader` | `inner_api_response` (claude → tool) | Same shape as `api_response`, with `tokens`. `parent` = the `evaluate_job` tool_call. |
| `research_company` | — (`actor` = `tool`) | `company`, `role_level`, `found`, `typical_base_for_level`, `source`: the lookup in the stored data. `parent` = the `research_company` tool_call. A company that isn't on file is `found: false`, never a caught guard. |
| `run_tools` | `tool_result` (tool → python) | `tool`, `tool_use_id`, `is_error`, `content`. For an unknown tool, `actor` is `python` and `crossing` is `null`: no tool ran, Python itself answers. |
| `answer_returned` / `reply_cut_off` / `pass_cap` / `api_call_failed` / `no_final_answer` / `unexpected_stop` | — | `ended_by`, `text`: the last event, in the step that matches how the run ended |

Content blocks are stored exactly as the API returned them (`model_dump()`), except that thinking blocks drop their opaque `signature`. Data is converted when the event is recorded, so later changes to `messages` can't alter it.

### Guard events

Every check the loop or a tool makes records a **guard event**, whether or not it caught anything: `actor` = `python`, `crossing` = `null`, and

```json
"guard": {"name": "…", "checked": "…", "value": …, "caught": false, "action": null, "message": null}
```

**`caught` is `true` only when something went wrong.** A caught guard always uses its error-case step from STEPS.md (E1–E9) and says what happened next (`action`) and the message. An uncaught guard uses the step where the check runs.

| Guard | When it's recorded | Step (not caught → caught) | `value` | When caught: `action`, `message` |
|---|---|---|---|---|
| `pass_count` | Start of every pass; and once after the last pass if the cap is hit | `send_to_claude` → `pass_cap` | pass number (11 when caught) | `run_stopped`, the cap message |
| `stop_reason` | Every reply | `check_reply`, or `claude_done` on `end_turn` (never caught; `action: "finish"` on `end_turn`) | the stop reason | — |
| `max_tokens` (main loop) | Every reply that isn't `end_turn` | `check_reply` → `reply_cut_off` | the stop reason | `run_stopped`, the cut-off message |
| `stop_reason_known` | Every reply that isn't `end_turn` or `max_tokens` | `check_reply` → `unexpected_stop` | the stop reason | `run_stopped`, the unhandled-stop message |
| `tool_exists` | Every tool request | `run_tools` → `unknown_tool` | the tool name | `error_sent_to_claude`, the `ValueError` text |
| `max_tokens` (grader) | Every grader reply, with `parent` | `inner_grader` → `grader_cut_off` | the stop reason | `error_raised`, the cut-off text |
| `api_call_succeeded` | Every outer call to Claude | `send_to_claude` → `api_call_failed` | error type when caught | `run_stopped`, the API-error message |
| `tool_succeeded` | Every tool that ran | `run_tools` → `tool_failed` | exception type when caught | `error_sent_to_claude`, `"<Type>: <message>"` |
| `final_text_present` | Every `end_turn` reply | `answer_returned` → `no_final_answer` | `"text"`, or `null` when caught | `run_stopped`, the no-answer message |
| `grade_valid` | Every parsed grader reply, with `parent` | `inner_grader` → `invalid_grade` | the problem when caught | `error_raised`, the problem text |

**Rule events** (#26, D28). A hard rule isn't a guard, so it's never a caught guard: each rule records one normal event at step `hard_screen`, `actor` = `python`, `guard` = `null`, `parent` = the `evaluate_job` tool call, with the outcome in the payload:

```json
"payload": {"rule": "comp_floor", "checked": "lowest base >= MIN_BASE (180000)",
            "value": 140000, "outcome": "failed", "note": "base below $180K floor"}
```

`rule` is `remote` or `comp_floor`; `outcome` is `passed`, `failed` or `skipped`. A skipped rule's `value` is what it couldn't read (e.g. `"competitive"`), and its `note` says it was skipped. When a rule fails, no `inner_grader` events follow.

So a grader that's cut off shows two caught guards in order: `max_tokens` (`grader_cut_off`), then `tool_succeeded` (`tool_failed`) with the same text. An unknown tool shows only `tool_exists`, because no tool ran. A run that hits a guarded stop ends with the caught guard, then the final event.

`evaluate_job` records its grader call through `tracing.active()`, the recorder `run_agent` set for this run. Called outside a run, it records nothing.

**No secrets:** the recorder never sees the API client, request headers, or environment variables, and `write()` refuses to write a trace that contains `sk-ant` anywhere.

### Faults injected on purpose

[`faults.py`](../faults.py) makes the agent fail in one specific way, so the "break the agent" scenarios (6–9) can be recorded on demand (#46, D27). It's off unless asked for: `--fault <name>`, or a scenario whose `fault` field names one. With no fault the agent behaves exactly as normal.

| Fault | What it forces | Caught by |
|---|---|---|
| `tool_fails` | The grader's reply is replaced with broken JSON, **once** | `tool_succeeded` (E1); Claude can retry and succeed |
| `unknown_tool` | Claude's first tool request is renamed to `rate_posting`, **once**, before it's saved, so the conversation stays consistent | `tool_exists` (E2) |
| `runaway_loop` | The grader's reply is broken **every** time, and the pass cap is lowered to **2** | `pass_count` (E4): "Stopped after 2 passes without finishing." |
| `reply_cut_off` | The main call's token limit is lowered to **30** | `max_tokens` (E3), whose message gives the limit actually used |

**Why the cap is lowered for `runaway_loop`:** in every live run where a tool kept failing, real Claude retried once and then stopped on its own. With the cap at 10 it would explain the failure long before reaching the cap; at 2, the cap stops the run right after the retry.

**How it shows in the trace:**
- A **`fault_injected`** event where the fault acts, with `payload: {"fault": …, <what changed>: {"real": …, "injected": …}}` (or `{"normal": …, "injected": …}` for a limit).
- **Tool faults** (`tool_fails`, `unknown_tool`, the grader part of `runaway_loop`): the events the fault causes are `injected: true`. That's the caught guard, the error result, and the `results_back` that adds it to the conversation. Claude's later reactions are real, so they're `false`.
- **Limit faults:** every event made under the lowered limit is `injected: true`. For `reply_cut_off` that's the request, Claude's response, the checks and the end. For `runaway_loop` it's the pass-count checks and the end.
- **Real API responses are recorded as they came back,** never altered: a swapped grader reply shows its real text in `inner_api_response`, and the injected text only in `fault_injected`.

### Recording scenarios (record.py)

[`record.py`](../record.py) makes the runs the page plays (#53, D30): `python record.py <id>` or `python record.py --all`. Each is a **real run** of the scenario's posting(s) and fault exactly as written in `scenarios/scenarios.json`, saved to **`recordings/scenario-<id>.json`** (two digits, e.g. `scenario-05.json`), replacing the previous recording. A scenario id that doesn't exist prints the valid ids and exits (code 2) before anything runs.

The file is the trace (format above) plus two keys:

```json
"mismatch": false,
"check": {"expected": {"tools": ["evaluate_job"], "outcome": "STRONG"},
          "actual":   {"tools": ["evaluate_job"], "outcome": ["STRONG"]},
          "mismatch": false, "differences": []}
```

**What's compared** is the scenario's `expect`, never Claude's wording:

- **Tools:** every tool Claude asked for, in order, including an unknown one, with back-to-back repeats counted once, so a retry doesn't change the path.
- **Outcome:** `stopped` if a guard stopped the run; otherwise one entry per tool that succeeded with a verdict (`evaluate_job`'s rating, or `flagged` for `flag_for_review`), or `no rating` if there was none.
- `expect` can be a list of acceptable results; matching any one is a PASS (scenario 6: a rating after Claude's retry, or no rating after it explains the failure).

It prints PASS, or MISMATCH with each difference (e.g. `tools: expected evaluate_job; got flag_for_review`), and exits 1 if any run mismatched. A mismatched run is still saved, with every step and error, so it's visible rather than lost. Every run also regenerates `docs/SCENARIOS.md` from the JSON, including a "Checked by record.py" line per scenario; a test fails if the committed doc and the JSON ever disagree.

### Terminal output

The `print` lines are still there for following a run live, one line per event. Each starts with the **step id** in brackets, the same id as STEPS.md, the `# STEP:` markers and the trace (#44). In `agent.py` every print is tagged `# (terminal only)`: it shows what's happening and changes nothing.

| Line | When |
|---|---|
| `[conversation_setup] messages has 1 item` | Start |
| `[send_to_claude] pass N: sending N message(s)` | Each outer call |
| `[claude_decides] stop_reason = …`, then one `text:` or `tool_use: id=… name=…` line per text or tool_use block | Each reply (thinking blocks aren't printed) |
| `[claude_done] end_turn → done. Outer calls: N …` | Normal finish |
| `[save_turn] appended assistant turn …` | Before dispatch |
| `[run_tools] dispatching <tool>(**{…})` | Each tool |
| `  [hard_screen] <rule>: <note>` (indented) | Each hard rule, inside `evaluate_job`; first, `pay '<pay>': base estimated from stored company data` when the pay is researched |
| `  [research_company] '<company>', '<role level>': found` / `not on file` (indented) | Each lookup, inside `research_company` |
| `[tool_failed] <tool> raised → <Type>: <message>` | A tool failed (E1) |
| `  [inner_grader] …` (indented) | Inside `evaluate_job`'s grader call |
| `[results_back] appended N tool_result(s) (ids: …[ is_error]) …` | After the tools run |
| `[reply_cut_off] …` / `[pass_cap] …` / `[api_call_failed] …` / `[unexpected_stop] …` | Guarded stops (E3, E4, E6, E9). E7 (no final answer) prints no line of its own. |

---

## 8. The page (site/)

Page v0 ([#57](https://github.com/justinyurasits/agents/issues/57)) replays a recorded run in the Execution Explorer layout (D15). Since [#71](https://github.com/justinyurasits/agents/issues/71) a visitor can pick any of the nine scenarios. It's plain HTML, CSS and JavaScript in [`site/`](../site/): no framework, no build step, no API calls, no key. The design reference is [`design/explorer-d1-mockup.html`](../design/explorer-d1-mockup.html).

**Run it:** from `job-evaluator/`, `python -m http.server 8000`, then open `localhost:8000/site/`. It has to be served (browsers won't `fetch` from a `file://` page), and it's served from `job-evaluator/` so the page can read `../recordings/` and `../scenarios/` without copies.

**What it loads, and nothing else** (a test checks the source has no URLs):

| File | Used for |
|---|---|
| `recordings/scenario-0N.json` | The chosen scenario's events: the map, the four questions, the timeline, the inspector. Fetched when the scenario is picked |
| `site/steps.json` | Each step's title and explanation, and each guard check's one-line explanation, generated from [STEPS.md](STEPS.md) by [`build_steps.py`](../build_steps.py) |
| `scenarios/scenarios.json` | The chooser (each scenario's id, name and group), the intro (`setup`, `watch_for`) and the summary card (`summary`) |
| `site/fonts/` | Inter and JetBrains Mono (SIL Open Font License; the licenses are next to the files) |

**steps.json has one source.** `python build_steps.py` reads STEPS.md and writes `steps` (per step id: `{number, title, text, error}`, the text being the paragraph(s) between `Step id:` and `Code:`) and `checks` (per guard name: the line from STEPS.md's "Checks" section). Edit STEPS.md, rerun the script; a test fails if the two disagree, or if any step or guard in the code or a recording has no explanation.

**Choosing a scenario** (#71, D35). A drop-down in the header lists all nine by name, in two groups (D21): the five normal runs, then the four break-the-agent runs. Picking one fetches its recording, rebuilds the steps, timeline and guard badges, and starts paused at step 1, with no page reload. The URL carries the choice: `?scenario=3` opens scenario 3, and no `scenario` opens scenario 1. Each pick adds a browser history entry, so Back and Forward step through the scenarios you picked. An id that isn't in `scenarios.json` (`?scenario=42`), or a scenario whose recording is missing, shows a one-line message in place of the run; the chooser stays usable.

| Scenario | Page steps |
|---|---|
| 1. Clean run | 14 |
| 2. Missing info | 19 |
| 3. Multi-tool | 21 |
| 4. Two tools at once | 23 |
| 5. Hard screen in code | 13 |
| 6. A tool fails | 23 |
| 7. Unknown tool | 21 |
| 8. Runaway loop stopped | 23 |
| 9. Reply cut off | 7 |

**Intro and summary card** (#75, D37). Under the title, an intro panel shows the scenario's `setup` (what's different about this input) and `watch_for` (the moment worth noticing). An intro never states the outcome. Break-the-agent intros add a "Simulated:" sentence saying what is injected and how. On the last step only, a summary card ("What happened") shows `summary`: what the recording shows happened, the outcome, and why it matters. Both are labelled "Written for this page · not Claude's output", like the step explanations. Tests check that every scenario has all three; that no intro uses an outcome word (a rating, flag, stop, retry); that scenarios with a `fault` say "Simulated:"; and that each summary names its recording's tools and outcome, as `record.actual()` reads them, and no other outcome.

**Events become page steps.** A run has more events than a visitor should step through (47 in scenario 6), so the page groups them (23 steps for scenario 6):

- A guard check that **passes** isn't a step. It's attached to the step after it (the pass count to the request, the reply checks to saving the turn), or, for a check inside a tool, to the tool's step before it (the grader's checks to the grader call). While that step is shown, the guard's badge flashes and its line from `checks` appears in the Python box.
- A guard check that **catches** something is a step of its own, with its E-step explanation.
- Step 9, **Claude says it's done** (`claude_done`), is always a step, though it's recorded as a passing `stop_reason` check: Python reading Claude's "I'm done" is routing, not a check, and it's why the loop ends.
- One hard screen's rule events are one step, and evaluate_job's own call to Claude (request, reply, and a simulated failure if there is one) is one step.
- Everything else is one step per event.

**How each part is driven by the recording:**

- **Execution map.** The box for the step's `actor` is highlighted. The four arrows show only what crosses at this step: the request (message count; on hover, what it carries), Claude's reply (stop reason, tool ID and name), the tool call (tool and first argument), and the tool's result (`result · ` and evaluate_job's rating, flag_for_review's status, or whether research_company found the company; or the error type in red). evaluate_job's own call is drawn only during that call, dashed purple, from Tools through Python to Claude (the call goes out through Python's client), labelled as a separate conversation; its reply tag turns red, labelled "Simulated failure", when a fault replaced the grader's reply. The header counts API calls so far, main and inner.
- **Guard badges** in the Python box: one per guard the run checks. The checks that passed at this step flash, with their one-line explanations; a caught guard stays lit red for the rest of its pass.
- **The four questions** are plain sentences, never code: Executing (the component), Has (what it holds, e.g. "1 message to send", "the stored facts for Marrowstone Logistics", "the 2 results, to add to the conversation in one message"), Because (what the step before did), Next (the next step's title, or where a tool's result goes).
- **Timeline:** every page step, grouped by pass (`START` = pass 0); steps inside a tool are indented; injected ones are tagged "simulated". Click any one to jump.
- **Explanation:** `steps[step_id]` from steps.json, labelled "Written for this page · not Claude's output". On a step that calls Claude, a line built from the request's payload follows it, labelled "from the recording": "This request carries: the system prompt, 2 tools (evaluate_job, flag_for_review), 1 message."
- **Inspector tabs**, each with a one-line description under the tab bar: State change (the messages list before and after; new messages highlighted), Code (the step's `code` and the commit it ran at), Payload (each event's payload, guard and tokens, and the checks that passed), Claude's response.
- **Claude's own words** (text and thinking blocks, the final answer, the grader's real reply) appear only under Claude's response. In Payload they're replaced with a pointer to that tab. Tool requests (names, IDs, arguments) are data and show in both.

**Playback:** starts paused at the first step, and again whenever a scenario is picked; Play / Pause, Back, Next, and 1× / 2× (2.5 s per step at 1×). Arrow keys step, space plays or pauses.

## 9. Known limits

What the code does **not** handle today. Each item is checked against the code, and linked where an issue exists.

- **Reading pay is a heuristic** (`lowest_base`, #26). It assumes US dollars and a yearly salary; it skips hourly, daily, weekly and monthly pay rather than compare it, and ignores numbers under 10,000 (bonus percentages, weeks of leave). A posting quoted in another currency would be compared as if it were dollars.
- **Remote status comes from Claude #1.** The remote screen trusts the `remote` boolean Claude fills in; if Claude leaves it out, the screen is skipped.
- **No retry with a bigger token limit** when a reply is cut off. Out of scope for #18.
- **The cap is fixed in code**, not configurable from outside, and it counts passes, not tokens or dollars. Out of scope for #15.
- **Return values are plain strings.** A caller can only tell "finished", "cut off", and "stopped at the cap" apart by comparing the text (see [Overview](#1-overview)).
- **Tools run one at a time**, in order (D20). Fine with three tools; slow if several grader calls ever happen in one turn.
- **Researched pay is matched by its lowest base** (D34). If a posting's own pay happened to equal the stored figure for that company, after Claude had researched it anyway, it would be labelled estimated. Role levels are matched by one stored word per level ("principal"); a level not on file gets no pay.
- **Stored company data covers only Marrowstone Logistics**, the company scenario 3 needs (#65). Every other company is `found: false`.
