# job-evaluator — Design doc

How the agent works and why. Living document: update it in the same PR as any change to behavior, tools, or prompts. Every statement here should match [`agent.py`](../agent.py) as it is on `main`. If they disagree, the code wins and this doc has a bug.

Issue links point to [the repo's issues](https://github.com/justinyurasits/agents/issues). Decisions (D17, D18, …) are in [DECISIONS.md](DECISIONS.md).

---

## 1. Overview

Given one job posting as text, the agent returns a short written verdict:

- a **rating** (STRONG / WORTH REVIEWING / IGNORE) with reasons, when the posting has enough information, or
- a **flag for manual review**, when key information (compensation, remote status) is missing or unclear.

Rating criteria, as written in the grader's prompt (`RUBRIC`):

| Rating | Meaning |
|---|---|
| STRONG | remote, $180K+ base, **and** builds Justin's AI consulting practice |
| WORTH REVIEWING | meets two of the three |
| IGNORE | meets one or none |

It's a small, deliberately visible agent. It was built to learn and demonstrate the agent loop, so every step prints a line to the terminal.

**Run it:** `python agent.py` from `job-evaluator/` (setup in [README.md](../README.md)). It evaluates a built-in sample posting (Northwind Labs, remote, $200K–$240K), prints each step and the final answer, and writes a trace file to `traces/` (section 7).

**Cost of a typical run:** 3 API calls when the posting gets rated (2 outer + 1 inside `evaluate_job`), 2 when it's flagged (`flag_for_review` makes no API call).

**What `run_agent` can return.** It always returns a string. There are three kinds, and callers can only tell them apart by the text:

| Case | Returned string |
|---|---|
| Claude finished (`end_turn`) | Claude's final answer (the reply's first text block) |
| Claude's reply hit the token limit | `"Claude's reply was cut off (hit the max_tokens limit of 2000)."` |
| 10 passes without finishing | `"Stopped after 10 passes without finishing."` |

The cases where it raises an exception instead of returning are in [Known limits](#8-known-limits).

---

## 2. Components

Everything is in one file, [`agent.py`](../agent.py). Top to bottom:

| Piece | What it is |
|---|---|
| `client`, `MODEL` | The Anthropic client (key from `.env`, loaded with `override=True`) and the model, `claude-sonnet-5-5`. |
| `MAX_PASSES = 10` | Most outer API calls per run. See the loop cap guard. |
| `MAX_TOKENS = 2000` | Longest reply Claude may write. Used by **both** API calls. |
| `tools` | The two tool definitions (name, description, input schema) sent to Claude on every outer call. The descriptions are how Claude decides which tool to use. |
| `RUBRIC` | System prompt for the grader call inside `evaluate_job`: the criteria above plus "Respond with JSON only". |
| `strip_json_fences(text)` | Removes a surrounding ```` ``` ```` / ```` ```json ```` fence from the grader's reply. Pure string function. |
| `evaluate_job(...)` | Tool. Makes its **own** Claude call with `RUBRIC` (no tools, no loop), parses the JSON reply, and returns it as a dict. |
| `flag_for_review(...)` | Tool. Plain Python, no API call. Returns `{"status": "flagged", "company", "role_title", "missing_info"}`. |
| `SYSTEM_PROMPT` | Claude #1's system prompt, a constant so the call and the trace use the same text. |
| `run_agent(job_text, recorder=None)` | The agent loop (next section). With a `Recorder`, it writes a trace (section 7). |
| `if __name__ == "__main__"` | The sample posting and the call to `run_agent`. |

Next to it, [`code_refs.py`](../code_refs.py) finds the code each step points to. `agent.py` carries a `# STEP: <step_id>` comment directly above the code for each step in [STEPS.md](STEPS.md), and `code_ref(step_id, source)` returns that code's current line number and full statement (D23). Nothing stores line numbers by hand, so editing `agent.py` can't make a reference go stale.

There are two Claude roles, and they never mix:

- **Claude #1, the agent** (outer calls in `run_agent`): sees the posting and the tools, and decides what to do.
- **Claude #2, the grader** (inner call in `evaluate_job`): sees one job summary and the rubric, and returns a rating. Its conversation is thrown away when the tool returns.

Tests live in [`tests/`](../tests/) (standard-library `unittest`, D17). Run them from `job-evaluator/` with `python -m unittest discover -s tests -v`. They use a fake Claude client, so they make no API calls and need no key.

---

## 3. The loop

The step-by-step walkthrough, written for someone who has never seen an agent, is in **[STEPS.md](STEPS.md)**. This section is the short technical version.

`run_agent` starts with one user message ("Evaluate this job posting: …") and then makes up to `MAX_PASSES` **passes**. A pass is one outer API call plus what follows it:

1. Send the system prompt, `tools`, and the **whole** `messages` list to Claude. Claude keeps no memory between calls; this list is the memory.
2. Read the reply's `stop_reason`:
   - `end_turn` → return the reply's first **text** block (found by type, because a thinking block can come first). **Done.**
   - `max_tokens` → return the cut-off message. Nothing in the reply is acted on. **Done.**
   - anything else → treated as a tool request. [Known limits](#8-known-limits) covers what that means for unexpected stop reasons.
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
| **System prompt** | `"You help Justin triage job postings. Use the tools provided."` | `RUBRIC` (criteria + "Respond with JSON only: `{"rating": "...", "reasons": [...]}`") |
| **Tools** | `evaluate_job`, `flag_for_review` (names, descriptions, input schemas) | none |
| **Messages** | The posting, then every assistant turn and tool result so far | One user message: `Company / Role / Location / Remote / Compensation` lines, then the description. Fields Claude #1 didn't fill in are sent as `Unknown`. |
| **Limit** | `max_tokens = MAX_TOKENS` (2000) | `max_tokens = MAX_TOKENS` (2000) |

Claude #1 never sees `RUBRIC`. Claude #2 never sees the tool descriptions or the outer conversation.

**Tools as Claude #1 sees them:**

| Tool | Description (when to use it) | Inputs |
|---|---|---|
| `evaluate_job` | "Rate a job posting against Justin's criteria. Use when the posting has enough information to rate: company, role, location/remote status, and compensation." | `company`, `role_title`, `job_description` (required); `location`, `remote` (boolean), `compensation` |
| `flag_for_review` | "Flag a posting for manual review. Use when key information (compensation, remote status) is missing or ambiguous, so the job can't be rated reliably." | `company`, `role_title`, `missing_info` (all required) |

**Tool results as Claude #1 sees them:**

- Success: `content` is the tool's return value as JSON. There's no `is_error` field.
- Failure: `content` is `"<ExceptionType>: <message>"` and `is_error: true`. For example, `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` or `ValueError: Unknown tool 'search_web'. Available tools: evaluate_job, flag_for_review.`

What Claude does after an error (retry, switch tools, or explain the failure) is Claude's decision, not the code's (D18). In live runs it has retried once and then explained the failure without inventing a rating. That's observed behavior, not a guarantee.

---

## 5. Guards and error handling

Every check in `agent.py` that exists to keep a run from crashing, hanging, or acting on bad data:

| Guard | Catches | Does | Issue | Test |
|---|---|---|---|---|
| **Fence stripping** (`strip_json_fences`, in `evaluate_job`) | Grader wraps its JSON in ```` ``` ```` or ```` ```json ```` fences | Strips the fence before `json.loads` | [#2](https://github.com/justinyurasits/agents/issues/2) | [`test_fences.py`](../tests/test_fences.py): `StripJsonFencesTest`, `EvaluateJobTest` |
| **Find text by type** (`evaluate_job` and the `end_turn` return) | A thinking block before the text block | Picks the first block with `type == "text"`, never `content[0]` | [#4](https://github.com/justinyurasits/agents/issues/4) (exit check). The `evaluate_job` fix came earlier, before issues were used (commit `3fbd8e6`). | [`test_fences.py`](../tests/test_fences.py): `test_each_reply_shape_with_thinking_block_first`. The fake replies in the other test files also put a thinking block first, so every test that checks `run_agent`'s final answer covers the exit check too. |
| **Tool errors** (`try / except Exception` around each tool) | Any exception from a tool: bad JSON from the grader, bad arguments, the grader's own API call failing | Sends `"<Type>: <message>"` back as a `tool_result` with `is_error: true`; the run continues. Ctrl-C still stops the script. | [#8](https://github.com/justinyurasits/agents/issues/8), D18 | [`test_tool_errors.py`](../tests/test_tool_errors.py): `ToolErrorTest` |
| **Unknown tool** (`else` branch of the dispatch) | Claude asks for a tool name that isn't defined | Raises `ValueError("Unknown tool '<name>'. Available tools: …")`, which the tool-errors guard turns into `is_error`. The list comes from `tools`, so it stays in sync. | [#11](https://github.com/justinyurasits/agents/issues/11), D19 | [`test_tool_errors.py`](../tests/test_tool_errors.py): `UnknownToolTest` |
| **Every tool request answered** (loop over `tool_use` blocks) | Several tool requests in one reply | Runs each one and returns all results in **one** user message with matching `tool_use_id`s. The API rejects the next call if any request goes unanswered. | [#7](https://github.com/justinyurasits/agents/issues/7), D20 | [`test_multiple_tools.py`](../tests/test_multiple_tools.py): `MultipleToolUseTest` |
| **Loop cap** (`for … in range(1, MAX_PASSES + 1)`) | Claude never says `end_turn`, e.g. it keeps retrying a tool that keeps failing | Stops after 10 outer calls and returns `"Stopped after 10 passes without finishing."` The grader's call doesn't count toward the 10. | [#15](https://github.com/justinyurasits/agents/issues/15) | [`test_loop_cap.py`](../tests/test_loop_cap.py): `LoopCapTest` |
| **Cut-off reply, main loop** (`stop_reason == "max_tokens"` in `run_agent`) | Claude #1's reply hit `MAX_TOKENS` | Returns `"Claude's reply was cut off (hit the max_tokens limit of 2000)."` Nothing in the reply runs, not even a tool request. | [#18](https://github.com/justinyurasits/agents/issues/18), D22 | [`test_max_tokens.py`](../tests/test_max_tokens.py): `test_cut_off_main_loop_reply_*` |
| **Cut-off reply, grader** (`stop_reason == "max_tokens"` in `evaluate_job`) | The grader's reply hit `MAX_TOKENS` | Raises `RuntimeError("The grader's reply was cut off …")` **before** parsing, so Claude gets "cut off" as an `is_error` result, not "invalid JSON". | [#18](https://github.com/justinyurasits/agents/issues/18), D22 | [`test_max_tokens.py`](../tests/test_max_tokens.py): `test_cut_off_grader_reply_is_reported_as_cut_off_not_invalid_json` |

The tests for fence stripping (#5) and for #7, #8, #11, #15 and #18 were each also run against the code from before the guard existed, to confirm they fail without it. The PRs that added them show that run.

---

## 6. Rules in code vs prompt

The repo's rule (CLAUDE.md) is that **deterministic rules belong in code, not prompts.** A prompt can be ignored or misread; code can't. Judgment calls belong to Claude.

| Rule | Lives in | Should live in | Notes |
|---|---|---|---|
| $180K base floor | Prompt (`RUBRIC`) | **Code** | Breaks the repo rule today. See below. |
| Must be remote | Prompt (`RUBRIC`) | **Code** | Same. |
| Builds the consulting practice | Prompt (`RUBRIC`) | Prompt | Needs judgment. |
| Rate vs flag (is enough info present?) | Tool descriptions, decided by Claude #1 | Prompt | Judgment about an unstructured posting. |
| Grader reply format (JSON) | Prompt (`RUBRIC`), parsed in code | Both | The prompt asks for JSON; code strips fences and parses it. The *contents* aren't checked (see Known limits). |
| Max passes, max tokens | Code (`MAX_PASSES`, `MAX_TOKENS`) | Code | |
| Which tool names exist | Code (`tools` + the dispatch) | Code | |

**The floor and remote rules are tracked as D6** ("Hard rules currently live in the prompt (open)"). D6, and the previous version of this doc, point to "issue #6". **But #6 is a pull request (the #4 fix), not an issue.** No open issue currently tracks moving these rules into code.

---

## 7. Trace format

Every recorded run writes a **trace**: one JSON event per step, which the page (D15) replays. Built for [#1](https://github.com/justinyurasits/agents/issues/1) in three parts: step markers ([#27](https://github.com/justinyurasits/agents/issues/27)), the recorder and core events ([#28](https://github.com/justinyurasits/agents/issues/28)), and inner calls plus guard events ([#29](https://github.com/justinyurasits/agents/issues/29)). Format decisions: D24 (events), D25 (guards).

### How a trace is made

[`tracing.py`](../tracing.py) has a `Recorder`. `run_agent(job_text, recorder=None)` calls it at each step. With no recorder it uses `NullRecorder`, which records nothing, so the agent behaves exactly the same. `python agent.py` records the sample run as scenario `clean` and writes **`traces/<scenario>-<YYYYMMDD-HHMMSS>.json`**. `traces/` is gitignored except `traces/recorded/`, where runs used on the page are copied on purpose.

### The file

| Key | What |
|---|---|
| `trace_version` | `1` |
| `scenario`, `started_at` | Scenario name; UTC start time |
| `git_commit`, `git_dirty` | The commit that ran, and whether `job-evaluator/` had uncommitted changes. Lets the page link code references to the exact version. |
| `model`, `limits` | `claude-sonnet-5-5`; `{"max_passes": 10, "max_tokens": 2000}` |
| `tools` | The full tool definitions, stored once |
| `events` | One per step, in order (below) |
| `result` | `{"ended_by": "end_turn" \| "max_tokens" \| "pass_cap", "text": …}`: what `run_agent` returned |

### Events

**Every event has every key**, `null` when it doesn't apply: `id` (`e1`, `e2`, …), `seq`, `pass` (`0` = before the loop), `step_id` (from [STEPS.md](STEPS.md)), `actor` (`python`, `claude`, or `tool`), `crossing` (`{from, to, kind}` or `null`), `payload`, `messages_before`, `messages_after`, `code` (`{file, marker, line, lines}` from `code_refs.py`; `null` for `claude_decides`), `parent` (the `tool_call` event an event happened inside, else `null`), `tokens`, `guard`, `injected` (always `false` until the simulated-failure switch exists).

| Step | `crossing.kind` | `payload` |
|---|---|---|
| `agent_starts` | — | `job_text` |
| `conversation_setup`, `save_turn`, `results_back` | — | `null`; `messages_before` / `messages_after` hold the conversation before and after (each adds exactly one message) |
| `send_to_claude` | `api_request` (python → claude) | `model`, `max_tokens`, `system`, `tools` (names only), `messages` (as sent) |
| `claude_decides` | `api_response` (claude → python) | `stop_reason`, `content` (every block: thinking, text, tool_use); `tokens` = `{input, output}` |
| `run_tools` | `tool_call` (python → tool) | `tool`, `tool_use_id`, `arguments`. Only for a tool that exists. |
| `inner_grader` | `inner_api_request` (tool → claude) | Same shape as `api_request`, with `system` = `RUBRIC` and `tools` = `[]`. `parent` = the `evaluate_job` tool_call. |
| `inner_grader` | `inner_api_response` (claude → tool) | Same shape as `api_response`, with `tokens`. `parent` = the `evaluate_job` tool_call. |
| `run_tools` | `tool_result` (tool → python) | `tool`, `tool_use_id`, `is_error`, `content`. For an unknown tool, `actor` is `python` and `crossing` is `null`: no tool ran, Python itself answers. |
| `answer_returned` / `reply_cut_off` / `pass_cap` | — | `ended_by`, `text`: the last event, in the step that matches how the run ended |

Content blocks are stored exactly as the API returned them (`model_dump()`), except that thinking blocks drop their opaque `signature`. Data is converted when the event is recorded, so later changes to `messages` can't alter it.

### Guard events

Every check the loop or a tool makes records a **guard event**, whether or not it caught anything: `actor` = `python`, `crossing` = `null`, and

```json
"guard": {"name": "…", "checked": "…", "value": …, "caught": false, "action": null, "message": null}
```

**`caught` is `true` only when something went wrong.** A caught guard always uses its error-case step from STEPS.md (E1–E5) and says what happened next (`action`) and the message. An uncaught guard uses the step where the check runs.

| Guard | When it's recorded | Step (not caught → caught) | `value` | When caught: `action`, `message` |
|---|---|---|---|---|
| `pass_count` | Start of every pass; and once after the last pass if the cap is hit | `send_to_claude` → `pass_cap` | pass number (11 when caught) | `run_stopped`, the cap message |
| `stop_reason` | Every reply | `check_reply`, or `claude_done` on `end_turn` (never caught; `action: "finish"` on `end_turn`) | the stop reason | — |
| `max_tokens` (main loop) | Every reply that isn't `end_turn` | `check_reply` → `reply_cut_off` | the stop reason | `run_stopped`, the cut-off message |
| `tool_exists` | Every tool request | `run_tools` → `unknown_tool` | the tool name | `error_sent_to_claude`, the `ValueError` text |
| `max_tokens` (grader) | Every grader reply, with `parent` | `inner_grader` → `grader_cut_off` | the stop reason | `error_raised`, the cut-off text |
| `tool_succeeded` | Every tool that ran | `run_tools` → `tool_failed` | exception type when caught | `error_sent_to_claude`, `"<Type>: <message>"` |

So a grader that's cut off shows two caught guards in order: `max_tokens` (`grader_cut_off`), then `tool_succeeded` (`tool_failed`) with the same text. An unknown tool shows only `tool_exists`, because no tool ran. A run that hits a guarded stop ends with the caught guard, then the final event.

`evaluate_job` records its grader call through `tracing.active()`, the recorder `run_agent` set for this run. Called outside a run, it records nothing.

**No secrets:** the recorder never sees the API client, request headers, or environment variables, and `write()` refuses to write a trace that contains `sk-ant` anywhere.

### Terminal output

The `print` lines are still there for following a run live, one line per event. Its `[step N]` numbers are an older numbering that matches neither STEPS.md nor the step markers; the trace from #1 uses step ids instead.

| Line | When |
|---|---|
| `[step 1] messages has 1 item` | Start |
| `[step 2]` / `[step 9] outer API call, sending N message(s)` | Each outer call (2 = first, 9 = later) |
| `[step 4/10] stop_reason = …`, then one `text:` or `tool_use: id=… name=…` line per text or tool_use block | Each reply (thinking blocks aren't printed) |
| `[step 5] appended assistant turn …` | Before dispatch |
| `[step 6] dispatching <tool>(**{…})`, and `[step 6] <tool> raised → <Type>: <message>` on failure | Each tool |
| `  [step 7] …` (indented) | Inside `evaluate_job`'s grader call |
| `[step 8] appended N tool_result(s) (ids: …[ is_error]) …` | After the tools run |
| `[step 11] end_turn → done. Outer calls: N …` | Normal finish |
| `[stop] max_tokens → …` / `[cap] 10 outer calls without end_turn → stopping.` | Guarded stops |

---

## 8. Known limits

What the code does **not** handle today. Each item is checked against the code, and linked where an issue exists.

- **Unexpected `stop_reason`** (e.g. `refusal`). Anything other than `end_turn` or `max_tokens` goes to the tool dispatch. With no tool requests in the reply, an empty user message is sent; the API will most likely reject it, and the run fails with an API error. This comes from reading the code; it hasn't been reproduced live. → [#21](https://github.com/justinyurasits/agents/issues/21)
- **API errors on the outer call aren't caught.** A network error, rate limit, or bad key on Claude #1's call raises out of `run_agent`. The same errors on the *grader's* call are caught, because that call runs inside a tool. → [#30](https://github.com/justinyurasits/agents/issues/30)
- **`end_turn` with no text block** would raise `StopIteration` from the final `next(...)`. Not seen in practice. → [#31](https://github.com/justinyurasits/agents/issues/31)
- **The grader's JSON isn't validated.** Whatever object the grader returns is passed on as the result. A missing `rating`, or a value other than the three ratings, isn't caught. → [#32](https://github.com/justinyurasits/agents/issues/32)
- **Hard rules live in the prompt** ($180K floor, remote). See [section 6](#6-rules-in-code-vs-prompt). No issue yet.
- **No retry with a bigger token limit** when a reply is cut off. Out of scope for #18.
- **The cap is fixed in code**, not configurable from outside, and it counts passes, not tokens or dollars. Out of scope for #15.
- **Return values are plain strings.** A caller can only tell "finished", "cut off", and "stopped at the cap" apart by comparing the text (see [Overview](#1-overview)).
- **Tools run one at a time**, in order (D20). Fine with two tools; slow if several grader calls ever happen in one turn.
