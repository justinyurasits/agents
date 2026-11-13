# job-evaluator — Decision log

One entry per decision. Newest at the bottom. Format: decision, options considered, reasoning, what would change it.

---

## D1 — One repo for all agents, one folder per agent

**Date:** 2026-11-11
**Options:** separate repo per agent · one `agents` repo with a folder per agent
**Decision:** one repo, folder per agent.
**Reasoning:** I'll build many small agents; a new folder costs nothing, and the root README becomes an index that tells one story.
**What would change it:** an agent becomes a flagship piece that needs its own README, releases, and issues — then it moves to its own repo.

## D2 — Repo private until the first README is solid

**Date:** 2026-11-11
**Options:** public from day one · private, flip later
**Decision:** private for now.
**Reasoning:** the public version should read as finished work. Flipping is one click.
**What would change it:** job-evaluator README, spec, and one sample trace are done.

## D3 — One virtual environment per agent

**Date:** 2026-11-11
**Options:** one shared environment at the repo root · one per agent folder
**Decision:** one per agent (`job-evaluator/.venv`).
**Reasoning:** agents will need different packages; isolating them avoids version clashes.
**What would change it:** agents end up sharing nearly all dependencies.

## D4 — Track work on a GitHub Projects board, issue → branch → PR

**Date:** 2026-11-11
**Options:** TODO comments in code · issues only · issues on a board with automation
**Decision:** board with Backlog / Todo / In Progress / Done; issues auto-added; merged PRs move cards to Done.
**Reasoning:** makes the way I work visible, and every change gets acceptance criteria before it gets code.
**What would change it:** —

## D5 — `evaluate_job` uses its own Claude call (inherited, under review)

**Date:** 2026-11-11
**Options:** grade inside the outer Claude call (no tool) · separate focused Claude call inside the tool · deterministic scoring in Python
**Decision:** keep the separate call for now.
**Reasoning:** focused prompt, more reliable JSON, reusable outside the loop. But in a one-job run it adds a call without adding information.
**What would change it:** issue #6 (hard screens into code) may shrink what's left for the model to judge to one criterion.

## D6 — Hard rules currently live in the prompt (open)

**Date:** 2026-11-11
**Status:** open — issue #6.
**Context:** the $180K floor and remote requirement are deterministic but sit in `RUBRIC`. A model can misapply a rule that code can't.

## D8 — Primary audience: people evaluating my work

**Date:** 2026-11-12
**Options:** job seekers as primary users · hiring managers/clients as primary viewers
**Decision:** built for people evaluating me; the working tool is the hook.
**Reasoning:** the point is showing how an agent works. The trace view stays central;
it stays a demo I don't have to maintain as a consumer product.
**What would change it:** real organic usage from job seekers.

## D9 — Candidate profile is a form, not a resume upload

**Date:** 2026-11-12
**Decision:** fields for target titles, comp floor, work mode, must-haves, deal-breakers,
top strengths; a sample profile preloaded.
**Reasoning:** no document parsing, no storing personal data.
**What would change it:** users consistently want resume-level matching.

## D10 — Live runs on a capped demo key; data stays in the session

**Date:** 2026-11-12
**Decision:** a separate API key with a hard monthly spend cap, a per-visitor run limit,
and an optional field for visitors to use their own key. Nothing a visitor enters
is saved or logged.
**Reasoning:** anyone can try it; worst-case cost is the cap.
**What would change it:** cap hit regularly → raise it or require own keys.

## D11 — Streamlit, hosted on Streamlit Community Cloud

**Date:** 2026-11-12
**Options:** Streamlit · Gradio on Hugging Face Spaces · custom web app
**Decision:** Streamlit.
**Reasoning:** pure Python on top of the existing agent; free hosting from the
GitHub repo; built-in status and expander components fit a step-by-step trace.
**What would change it:** a UI need Streamlit can't meet.

## D11 — FastAPI server + custom web page

**Date:** 2026-11-12
**Options:** Streamlit · Gradio on Hugging Face Spaces · FastAPI + custom HTML/JS page
**Decision:** FastAPI + custom page.
**Reasoning:** the audience is people judging my work, so the step-by-step view has
to look deliberate. The agent stays in Python; FastAPI streams step events to a page
that renders each one live with an explanation, the real line of code, and the data.
**What would change it:** hosting cost or complexity outweighs the polish.

## D12 — Recorded scenarios only; static page on GitHub Pages

**Date:** 2026-11-12
**Supersedes:** D9 (profile form), D10 (capped live key), D11 (FastAPI)
**Decision:** v1 runs only prepared scenarios. Each is run for real locally,
its step events saved, and played back by a static page hosted on GitHub Pages.
**Reasoning:** the brief says no visitor input and must never fail in a live
demo. Recorded real runs give zero cost, no failure risk, and pacing control.
**What would change it:** a strong reason to let visitors run live — then
add a FastAPI live mode post-v1.

## D13 — Seven scenarios, error handling forced with labeled switches

**Date:** 2026-11-12
**Decision:** clean run, missing info, multi-tool, tool fails and recovers,
two tools in one reply, hard screen in code, runaway loop stopped. Failures
are triggered by a visible "simulated failure" switch, never hidden.
**Reasoning:** each M2/M3 fix becomes something a visitor can watch, and
links back to the issue that built it.
**What would change it:** the page feels like a test suite → cut to five.

## D14 — research_company uses stored company data

**Date:** 2026-11-12
**Decision:** company facts are pulled once and stored in the repo; the tool
reads from that file. Labeled on the page as stored data.
**Reasoning:** recorded runs must be repeatable; no live web dependency.
**What would change it:** a live mode post-v1 could use real search.

## D15 — Run view: Execution Explorer, linear map

**Date:** 2026-11-12
**Options:** A Instrument · B Lanes · C Ledger · D1 Explorer linear · D2 Explorer triangle
**Decision:** D1. Claude | Python | Tools across the top; data shown on every
arrow; a tool's own Claude call drawn as a separate path underneath; compact
four questions; timeline; inspector with State change / Code / Payload /
Claude's response.
**Reasoning:** keeps the architecture visible the whole run, and makes the
boundary crossings the thing you watch. Three boxes read cleaner than the
triangle or a fourth box.
**What would change it:** first-time viewers can't explain who decides and
who executes after one run.

## D16 — Build scenario 4 end to end before the other six

**Date:** 2026-11-12
**Decision:** one vertical slice first (record → trace → page) on the
tool-failure scenario, then add the rest.
**Reasoning:** proves the trace format and the page on the hardest case
before multiplying it by seven.

## D17 — Tests use the standard library's unittest, not pytest

**Status:** **Approved** (issue #5, PR #9)
**Date:** 2026-11-12
**Options:** `pytest` · `unittest` (standard library)
**Decision:** `unittest`. Run from `job-evaluator/` with
`python -m unittest discover -s tests -v`.
**Reasoning:** no new dependency, so nothing to add to requirements.txt and
no approval needed. For a handful of tests the two are about equal; `subTest`
covers the "same check, several inputs" case that pytest's parametrize would.
Tests swap `agent.client` for a fake and skip the `.env` load, so they make no
API calls and run without a key.
**What would change it:** enough tests that pytest's fixtures, parametrize,
or clearer failure output start saving real time. pytest also runs
unittest-style tests unchanged, so switching later costs little.

## D18 — Tool exceptions go back to Claude as is_error tool_results

**Status:** **Approved** (issue #8, PR #12)
**Date:** 2026-11-12
**Options:** let the exception crash the run · catch it and stop the run with
an error message · catch it and send it to Claude as an `is_error` tool_result
**Decision:** send it to Claude. `run_agent` wraps the tool call in
`try / except Exception`; on failure the tool_result content is
`"<ExceptionType>: <message>"` with `is_error: true`.
**Reasoning:** what to do after a failure (retry, switch tools, tell the user)
is a judgment call, so it belongs to Claude. Python's job is to report the
failure faithfully. `except Exception` catches every tool failure but still
lets Ctrl-C (`KeyboardInterrupt`) stop the script. The exception type is
included because it says what kind of failure it was (`JSONDecodeError` vs
`TypeError` for bad arguments) at almost no cost.
**What would change it:** a tool whose error messages could contain something
Claude shouldn't see (a key, a visitor's input), in which case send a generic
message and log the detail locally. Or retries running away, which a loop
cap (out of scope for #8) would handle.

## D19 — Unknown tool: raise inside the dispatch, list the real tools

**Status:** **Approved** (issue #11, PR #13)
**Date:** 2026-11-12
**Options:** add an `else` that raises · switch to a name → function dict ·
check the name before the `try`
**Decision:** an `else` branch that raises
`ValueError("Unknown tool '<name>'. Available tools: <names>.")`. It's inside
the `try` from #8 (D18), so it becomes an `is_error` tool_result with no new
error-handling code.
**Reasoning:** smallest change that fixes both cases in #11. `result` can
never be left unset or stale, because every branch either sets it or raises.
Listing the available tools tells Claude what it _can_ call, so it can recover
on the next turn. The names come from the `tools` list, so adding a tool
updates the message automatically.
**What would change it:** more tools, at which point a name → function dict
replaces the `if / elif` chain and the `else` becomes a dict lookup miss.

## D20 — Several tool_use blocks: run in order, inline, one result message

**Status:** **Approved** (issue #7, PR #14)
**Date:** 2026-11-12
**Options:** run tools in parallel · run them in order · move dispatch into a
`run_tool()` helper · keep it inline in `run_agent`
**Decision:** a `for` loop in `run_agent` over every `tool_use` block, run in
order. Each block gets its own `try / except` (D18), and all results go back
in one user message, each with its `tool_use_id`.
**Reasoning:** in order is simpler to read and to trace, and the issue says
it's enough. Parallel only pays off when tools are slow and independent.
Keeping it inline means the step page still points at one block of code in
the loop. Per-block error handling means one failing tool can't stop the
others from getting a result, which the API requires.
**What would change it:** slow tools (several inner Claude calls per turn)
making runs noticeably slow → run them in parallel. The dispatch growing
past a screenful → move it into a helper.

## D21 — Scenario set: 5 normal runs + 4 "break the agent" runs

**Date:** 2026-11-12
**Supersedes:** D13
**Decision:** normal runs (clean, missing info, multi-tool, two tools at once,
hard screen) and break-the-agent runs (tool fails, unknown tool, runaway loop,
reply cut off). Faults are injected and labeled. The page explains each
guard as it exists in the app and why it's there; no before/after comparison.
**Reasoning:** error handling is the most convincing part of the demo, and
each break scenario maps to a guard already built (#8, #11, loop cap, max_tokens).
**What would change it:** time pressure → cut normal runs 4 and 5 first.

## D22 — A cut-off reply is never acted on

**Status:** **Proposed** (issue #18)
**Date:** 2026-11-12
**Options:** dispatch any complete-looking tool requests in a cut-off reply ·
stop and act on nothing
**Decision:** stop. In the main loop, a `max_tokens` reply ends the run with
"Claude's reply was cut off (hit the max_tokens limit of 2000)." In
`evaluate_job`, a `max_tokens` grader reply raises a "cut off" error *before*
parsing, so it reaches Claude as an `is_error` tool_result (D18).
**Reasoning:** a reply that hit the limit is unfinished by definition, and
there's no reliable way to tell whether a tool request in it was finished.
Running a tool on half-written input is worse than stopping. Checking
`stop_reason` before parsing names the real cause; parsing first would report
"invalid JSON" and hide it.
**What would change it:** cut-offs happening in normal use. Then raise
`MAX_TOKENS` or retry with a bigger limit (out of scope for #18).

## D23 — Code references come from step markers, found with `ast`

**Status:** **Proposed** (issue #27)
**Date:** 2026-11-13
**Options:** hand-written line numbers in STEPS.md · a start and end marker
around each block · one marker above the code, with the code's extent found
by parsing
**Decision:** one `# STEP: <step_id>` comment directly above the code.
`code_refs.py` reads the source, finds the marker, and uses Python's `ast`
module to take the outermost statement (or `except` clause) starting on the
next line, so a multi-line call or a whole `if` / `for` block comes back
complete. Step 9 (`claude_done`) shares step 5's marker, and step 4
(`claude_decides`) has no code. A missing or duplicated marker, or a marker
not directly above code, raises an error.
**Reasoning:** hand-written line numbers in STEPS.md went stale on almost
every PR. One marker per step is the least to maintain, and `ast` knows where
a statement ends better than a hand-placed end marker would. Failing loudly
on a broken marker means a wrong reference shows up as a test failure, not
on the page.
**What would change it:** a step that needs to point at part of a statement,
or at code spread over several places. Then add an explicit end marker.

## D24 — Trace format: one flat event per step, every key always present

**Status:** **Proposed** (issue #28)
**Date:** 2026-11-13
**Options:** nested events (a pass containing its steps) · flat list of events
· only the keys that apply on each event · every key on every event
**Decision:** a flat, ordered list of events. Each event has every key
(`id, seq, pass, step_id, actor, crossing, payload, messages_before,
messages_after, code, parent, tokens, guard, injected`), `null` where one
doesn't apply. Grouping (by pass, or under a tool call) comes from `pass` and
`parent`. Run-level facts (model, limits, full tool definitions, git commit)
are stored once at the top. SDK blocks are stored via `model_dump()`; thinking
keeps its text and drops `signature`. Data is serialized when the event is
recorded. `run_agent` takes an optional recorder; `NullRecorder` makes
recording a no-op.
**Reasoning:** a flat list is what the page replays step by step, and the
timeline can group it however it likes. Fixed keys mean the page never checks
whether a key exists. Storing `git_commit` lets code references link to the
exact version that ran. The full `messages[]` is repeated in each request and
before/after copy (decision F on #1): simple, and still small at 10 passes.
**What would change it:** traces getting slow to load on the page. Then store
each message once and refer to it by index.
