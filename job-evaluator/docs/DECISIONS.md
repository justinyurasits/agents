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
**Status:** closed by D28 (issue #26). ("#6" was a PR, not an issue; #26 is the issue.)
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

**Status:** **Approved** (issue #18, PR #22)
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

**Status:** **Approved** (issue #27, PR #34)
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

**Status:** **Approved** (issue #28, PRs #35 and #37)
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

## D25 — Guard events: every check recorded, "caught" means something went wrong

**Status:** **Approved** (issue #29, PRs #36 and #37)
**Date:** 2026-11-13
**Options:** record only guards that catch something · record every check
**Decision:** every check records a guard event,
`{name, checked, value, caught, action, message}`. `caught` is `true` only
when something went wrong; then the event uses the guard's own error-case
step (STEPS.md E1–E5). The stop_reason check is never "caught": it records
`action: "finish"` on `end_turn`. An unknown tool is caught by `tool_exists`
alone: no `tool_call` or `tool_succeeded` event, because no tool ran, and its
`tool_result` has `actor: python` and no crossing. The grader's own
max_tokens check got its own step (E5 `grader_cut_off`). `evaluate_job` finds
the run's recorder through `tracing.active()`.
**Reasoning:** the page should show that each check happened, not only when
it fired. That's the point of D21's "break the agent" runs. Reserving
`caught` for failures keeps "Claude finished" from reading like an error.
Recording an unknown tool without a tool crossing keeps the trace truthful:
nothing reached a tool. A module-level active recorder avoids adding a
recorder parameter to every tool function.
**What would change it:** tools that run in parallel (D20), where one global
"active recorder" and "current tool call" no longer work; then pass the
recorder and parent explicitly.

## D26 — A failed call to Claude stops the run with the error's type only

**Status:** **Approved** (issue #30, PR #38)
**Date:** 2026-11-13
**Options:** let the exception crash the run · retry · stop and return a
message (with the error's text, or with only its type and status)
**Decision:** catch `anthropic.APIError` around Claude #1's call. Stop the
run and return `"Couldn't get a reply from Claude: <ErrorType> (status
<code>). The run stopped."` No retries beyond the SDK's own. The trace
records an `api_call_succeeded` guard on every call (caught on failure, step
E6 `api_call_failed`) and ends with `ended_by: "api_error"`.
**Reasoning:** with no reply there's nothing for Claude to decide, so unlike
a tool error (D18) it can't go back to Claude: stopping with a clear message
is the only safe move. The SDK already retries connection errors, 429s and
5xx twice by default (`max_retries=2`), so the agent adds none (out of scope
for #30). The message leaves out the error's text because it comes from
outside the program; the type and status say what happened without risking
an echoed key or header.
**What would change it:** failures that a retry after a longer wait would fix
in practice (e.g. repeated 529s during a demo). Then add a retry with backoff,
which is a separate decision.

## D27 — Fault injection: real responses kept, injected effects labelled, cap lowered for the runaway demo

**Status:** **Approved** (issue #46, PR #47)
**Date:** 2026-11-13
**Options:** fake the failures in a test client · inject them into real runs ·
for the runaway loop: keep the cap at 10, nudge Claude with "temporary,
retry" errors, override Claude's end_turn, or lower the cap
**Decision:** inject into real runs, from `faults.py`, only when asked
(`--fault`, or a scenario's `fault`). Record every change as a
`fault_injected` event showing the real and the injected value, keep real API
responses unaltered, and mark `injected: true` exactly on what the fault does
or causes (tool faults: until the error is back in the conversation; limit
faults: everything made under the lowered limit). `unknown_tool` renames the
request before it's saved, so the conversation stays consistent.
`runaway_loop` lowers the cap to 2 for that run. All four choices made in chat
on #46.
**Reasoning:** BRIEF's truthfulness rule: recorded runs are real and
simulated failures are labelled. Real Claude retries a failing tool once and
then stops on its own (#8, #18, #29 live runs), so a cap of 10 would never be
reached; overriding its end_turn would replace a real decision, and nudging
might still not reach 10. Lowering the cap keeps every Claude decision real
and the cap demo reliable.
**What would change it:** Claude starting to retry more than once, which
would make the lowered cap unnecessary or need to be higher.

## D28 — Hard screens in code; the grader answers one yes/no question

**Status:** **Approved** (issue #26, PR #51)
**Date:** 2026-11-13
**Options:** screen in `run_agent` before Claude is called · screen inside
`evaluate_job` after Claude #1 extracts the details · keep the rules in the
prompt
**Decision:** screen inside `evaluate_job`, before the rating call (as #26
asks). `remote: false` fails the remote screen; a lowest base below
`MIN_BASE` fails the comp screen. A screen that can't be checked (remote not
given; pay that isn't a readable yearly salary) is **skipped, never failed**,
so missing data never rejects a posting. Every failed screen is listed in
`reasons`. The grader answers only "does this role build hands-on AI
experience?" as `{"answer": "yes"|"no", "reasons": [...]}`, and code maps it
(yes → STRONG, no → WORTH REVIEWING); other keys aren't passed on. The grader
no longer gets the Location / Remote / Compensation lines, since the screens
already used them.
**Guards vs rules** (Justin's review of PR #51): a **guard** catches a
failure (a crash, a hang, bad data) and gets an E-step under "When something
goes wrong". A **rule** applies one of Justin's decisions; a posting that
fails one is the agent working as intended, so a rule is a **normal step**.
The hard screens are a rule: step `hard_screen` (STEPS.md 7a, "Code checks
your hard rules"), labelled `RULE (hard_screen)` in agent.py, not `GUARD`.
CLAUDE.md and `test_annotations.py` now enforce both labels.
**Trace:** each rule (`remote`, `comp_floor`) records one normal event at
step `hard_screen`, with the `evaluate_job` tool call as its parent and
`{rule, checked, value, outcome, note}` as its payload (`outcome`: passed,
failed or skipped). Never a guard event, so `caught: true` still means only
that something went wrong (D25). A skipped rule's `value` is the text it
couldn't read (e.g. `"competitive"`).
**Reasoning:** CLAUDE.md: deterministic rules belong in code. Reading pay in
code is a heuristic (SPEC, Known limits), so it errs toward skipping:
wrongly rejecting a good posting is worse than sending one more posting to the
grader.
**What would change it:** postings whose pay `lowest_base` misreads (other
currencies, unusual formats); then extract a number in Claude #1's tool input
instead of parsing text.

## D29 — A stop reason the agent doesn't handle stops the run

**Status:** **Approved** (issue #21, PR #52)
**Date:** 2026-11-13
**Options:** list each unhandled stop reason and stop on those · stop on
anything that isn't `tool_use` · handle some (e.g. resume after `pause_turn`)
**Decision:** after the `end_turn` and `max_tokens` checks, anything other
than `tool_use` stops the run with "Claude stopped for a reason this agent
doesn't handle (stop_reason '…'). The run stopped." Nothing in the reply is
acted on, even a tool request, and no further request is sent. Only the stop
reason goes in the message, not any text Claude wrote.
**Reasoning:** same as D22: the run must always finish, and it shouldn't act
on a reply it doesn't understand. Checking for "not `tool_use`" rather than a
list means a stop reason the API adds later is stopped too; the SDK already
lists one (`model_context_window_exceeded`) the issue didn't mention.
Resuming after `pause_turn` is out of scope (#21); this agent uses no server
tools, so it shouldn't occur.
**What would change it:** the agent starting to use server tools (then
`pause_turn` needs a resume), or wanting to show Claude's refusal text.

## D30 — How a recording is checked against its scenario

**Status:** **Approved** (issue #53, PR #54)
**Date:** 2026-11-13
**Options:** parse the prose `expected_tools` / `expected_outcome` · add a
machine-readable `expect` to each scenario · compare the exact tool sequence
or count retries once · for multiple postings, run them separately or together
**Decision:** each scenario in `scenarios.json` gets an `expect`
(`{"tools": [...], "outcome": ...}`), next to the prose, which stays for the
page. Outcome is one of STRONG, WORTH REVIEWING, IGNORE, `flagged`, `stopped`,
`no rating`, or a list when the run handles several postings. `expect` may be
a list of acceptable results (scenario 6). Back-to-back calls to the same tool
count once. Several postings are sent together in one run, joined with a
`---` line, which also fixes `agent.py --scenario 4` (it passed the list as
text). SCENARIOS.md shows the `expect` as a "Checked by record.py" line. The
first three choices made in chat on #53.
**Reasoning:** parsing prose is fragile, since a wording edit would silently
change the check. Retries vary between real runs (scenarios 6 and 8), so an
exact count would mismatch on Claude's choice rather than on a wrong path.
Scenario 6 promises "retries or explains", so both are a PASS.
**What would change it:** the page needing a finer check (e.g. the number of
retries), or postings that must be evaluated in separate runs.

## D31 — Page v0: how the page is served, and what it shows where

**Status:** **Approved** (issue #57, PR #60 review)
**Date:** 2026-11-13
**Options:** put the page at the repo root or in `job-evaluator/site/` · copy
the recording into `site/` or read it where it is · load Inter and JetBrains
Mono from Google Fonts, ship the font files, or use them only when installed ·
show Claude's words wherever they occur, or only under "Claude's response"
**Decision:** the page lives in `job-evaluator/site/` and is served from
`job-evaluator/`, so it reads `../recordings/` and `../scenarios/` directly,
with no copies to keep in sync; it also loads `scenarios/scenarios.json` for the
scenario's name. The fonts ship with the page in `site/fonts/` (woff2, Latin,
the weights the design uses, with their OFL licenses). Claude's prose (text,
thinking, final answer, the grader's reply) appears only under "Claude's
response"; in Payload it's replaced with a pointer to that tab. Tool requests
(names, IDs, arguments) count as data and show in both. The map caption and the
three box descriptions from the mockup are kept as fixed text, labelled
"Written for this page"; step explanations come only from steps.json. The first
version listed every event in the timeline; the review replaced that with page
steps (D32).
**Reasoning:** the issue requires no requests except the page's own files,
which rules out Google Fonts; shipping the files keeps the design's fonts
without breaking that. Keeping Claude's words in one place makes it plain what
Claude wrote and what the page wrote. All approved in review on PR #60.
**What would change it:** GitHub Pages (M5) serving only `site/` (then the
recording is copied in at publish time).

## D32 — What counts as a step on the page

**Status:** **Approved** (issue #57, PR #60 review)
**Date:** 2026-11-13
**Options:** one step per event · hide passing guard checks · also group
events that belong together (the rules of one hard screen; evaluate_job's own
call) · also fold whole STEPS.md steps together (e.g. save the turn into
Claude's decision) to reach ~15
**Decision:** a passing guard check isn't a step: it's attached to the step
after it, or, inside a tool, to the tool's step before it, and while that step
is shown its badge flashes with a one-line explanation. The lines live in a new
"Checks" section of STEPS.md, built into steps.json with the step explanations.
A caught check stays a step. So does step 9, "Claude says it's done", though
it's recorded as a passing `stop_reason` check: it's routing, not a check. One
hard screen's rule events are one step, and evaluate_job's own call to Claude
(request, reply, any simulated failure) is one step. No further folding:
scenario 6 has 23 steps. The "This request carries" line is shown for
evaluate_job's own call too, not only the main loop's request. Justin chose
no fold, and step 9 as a step, in review.
**Reasoning:** saving the turn and adding results back are what make "the
conversation is the memory" visible, and the hard rules step is scenario 5's
principle, so none of them is folded away. Step 9 is one of Claude's two
decisions in the run and the reason the loop ends; the run can't finish without
showing it. Putting the check lines in STEPS.md keeps one source for every
explanation the page shows.
**What would change it:** other scenarios playing too long, or another guard
event that is really routing (it would join step 9 as an always-shown step).

## D33 — Page structure: one page, six sections, a "Watch it" button on every claim

**Status:** **Approved** (issue #62)
**Date:** 2026-11-13
**Decision:** one page with a header bar linking to six sections: Hero + run,
How it works, Design principles, Guardrails, How it was built, Footer.
Principles and guardrails each have a "Watch it" button that loads and plays
the matching scenario. Each run ends with a labeled summary card. I'm named
in the hero and footer.
**Reasoning:** learners want to watch; people evaluating my work want to see
how I think. One page serves the learner first and rewards the reader who
scrolls. "Watch it" turns every claim into something provable by pressing Play.
**What would change it:** the first-visitor test shows people never scroll
past the run view.

## D34 — Researched pay: code recognises it; no change to evaluate_job's inputs

**Status:** **Approved** (issue #65, PR #66)
**Date:** 2026-11-14
**Options:** add a field to evaluate_job's input schema so Claude says the
pay was researched · let code remember what research_company found in this
run and recognise it · key stored pay by exact role title, or by a seniority
word in the level Claude sends
**Decision:** code. `run_agent` keeps the pay each `research_company` call
found, by company (lowercase). `evaluate_job` gets it as a keyword argument
Claude can't set, and treats its pay as researched when research found pay for
the same company and Claude passed that pay (same lowest base) or none it
could read; in that case it uses the researched pay for the hard rules and adds
"base estimated from stored company data" to the reasons. Stored pay in
`data/companies.json` is keyed by a seniority word ("principal") matched in
the level Claude sends. `scenarios.json` names a scenario's company
(`stored_company`) instead of holding its facts, and SCENARIOS.md shows the
facts from `data/companies.json`.
**Reasoning:** the only thing Claude sees change is the new tool, with the
description from the issue; evaluate_job's schema stays as it was. Whether pay
is an estimate is a fact about where it came from, which code knows for
certain; asking Claude to declare it would put a rule in the model's hands
(CLAUDE.md). A seniority word matches the role levels Claude actually sends
("Principal Product Manager", "Principal PM").
**What would change it:** postings whose listed pay could equal the stored
figure (then the label could be wrong), or companies with several levels that
share a word (then key by full level).

## D35 — Scenario chooser: a drop-down in the header; each pick is a history entry

**Status:** **Approved** (issue #71, PR #72)
**Date:** 2026-11-14
**Options:** a native drop-down (`<select>`) · a row of nine buttons · a
side list · picking replaces the URL (Back leaves the page) or adds to the
browser history (Back returns to the previous pick)
**Decision:** a native `<select>` next to the playback controls, with two
labelled groups ("Normal runs", "Break the agent", D21). Each pick pushes
`?scenario=N` onto the history, so Back and Forward move between picks. No
`scenario` in the URL opens scenario 1 without changing the URL. An unknown id
or a missing recording hides the run and shows one line; the chooser stays.
**Reasoning:** a native drop-down is keyboard- and screen-reader-ready and
fits on a phone; nine buttons wouldn't fit the header. Visitors expect Back to
undo their last click, and "Watch it" buttons (D33) will use the same URL.
**What would change it:** the hero section (D33) needs the scenarios visible
at once, e.g. as cards; then the chooser becomes those cards, same URL.

## D36 — Page structure: eight sections, principles after the run

**Status:** **Approved** (issue #78, PR #86 review)
**Date:** 2026-11-14
**Supersedes:** D33's section list. D33's "Watch it" buttons, the summary
card at the end of a run (D37), and naming me in the hero and footer stay.
**Decision:** one page, a header bar linking to eight sections in this order:
1. **Hero:** what this is in one line, who built it, and a **Watch it run**
   button that jumps to the run view.
2. **What's an agent:** three sentences, a small loop diagram, and "Claude
   decides; Python executes".
3. **How this agent works:** the four parts (Python, Claude, the tools, the
   grader), the loop, and the tools with one line each on when they're
   used. Watch it buttons for scenarios 1, 3 and 4.
4. **Scenarios:** nine cards (#79).
5. **The run view:** the Execution Explorer (D15).
6. **Design principles:** principle → feature → Watch it (#80). This replaces
   D33's separate Guardrails section: guards are listed as features under
   the principle they serve.
7. **How it was built** (#81).
8. **Footer** (#81).

What D33 changes:
- D33's "How it works" becomes two sections, What's an agent and How this
  agent works.
- The run view is its own section, after the scenarios.
- Principles come after the run, because they point at scenarios.
- A "Watch it" button loads its scenario at step 1 and scrolls to the run.
  It starts paused, like every run (D33 said "loads and plays").

**Reasoning:** a first-time visitor needs "what's an agent" before the run
means anything. Someone evaluating the work wants the principles once they've
seen a run, and the cards give them a way into any scenario.
**What would change it:** the first-visitor test shows people skip the text
and go straight to the run. Then the run view moves up, under the hero.

## D37 — Scenario intro and summary card: where they sit, and what they may say

**Status:** **Approved** (issue #75, PR #77)
**Date:** 2026-11-14
**Options:** what's simulated as its own field · as a "Simulated:" sentence in
`setup` · the summary card inside the inspector · full width above it
**Decision:** the intro is a full-width panel under the title, always visible
while a run is shown. The summary card is full width between the four
questions and the timeline, visible only on the last step. What's simulated is
a "Simulated:" sentence at the end of `setup`, not a new field: the issue
asked for two intro lines. The rules are tests, not just guidance: no outcome
words in an intro, and each summary must name the recording's tools and
outcome.
**Reasoning:** the intro is what a first-time visitor reads before pressing
Play, so it sits above the map. The summary is the payoff, so it sits where
the eye lands after the last step, above the details. A test catches a summary
that goes stale when a scenario is re-recorded with a different path.
**What would change it:** the scenario cards (#79) show `setup` on each
card; then the intro panel may shrink to just "Watch for". Or a re-recording of scenario 6 that
explains the failure instead of retrying, which would need a new summary.

## D38 — Browser tests: Playwright in a dev requirements file, skipped when missing

**Status:** **Approved** (issue #84, PR #85 review)
**Date:** 2026-11-14
**Options:** add Playwright to `requirements.txt` · a separate
`requirements-dev.txt` · check every tab in the "Claude's words" test, or only
what the page shows by default
**Decision:**
- Playwright (pinned, 1.65.2) goes in a new `requirements-dev.txt`, which
  includes `requirements.txt`. Someone who only runs the agent doesn't need a
  browser.
- `tests/test_browser.py` is plain `unittest`. It starts its own local server
  and skips with a one-line reason when Playwright or Chromium is missing.
- The "Claude's words" check (D31) searches the State change, Code and
  Payload tabs at every step, along with everything else on the page. A tab
  that fails to draw, or a console error, fails the check, so it can't
  search the wrong tab by mistake.
- **One exemption, in Payload only:** the content of a tool_result. A tool's
  result is data, even when it carries the grader's reasons inside
  evaluate_job's rating. The test removes exactly the recorded
  tool_result content strings from Payload's text before searching. Nothing
  else on any tab is exempt.
- Claude often repeats its input: a line of the posting, or the
  job_description it passed to evaluate_job. A piece of Claude's words that
  also appears in the posting, in what Python sends Claude (system prompt,
  tool definitions, user messages other than tool results), or in Claude's
  tool request arguments (data, D31) isn't searched for. It would match the
  input, not a leak. Between 92% and 100% of each scenario's pieces are still
  searched.
- The tests read the page's state through `window.explorer`, which the page
  already exposes for checking by hand.
**Reasoning:** the page's rules (D31, every scenario plays) were checked by
hand on each PR and a gap slipped through (#76). A dev file keeps the agent's
install small; skipping keeps a fresh checkout's tests green while CLAUDE.md
makes a skipped suite not count for a `site/` PR.
**What would change it:** a CI runner with Chromium (then the suite always
runs). A new tab, which gets added to the searched tabs. Claude's words
reaching a tool_result through some new path (then the exemption needs
narrowing).

## D39 — Scenario cards: tool paths worked out from the recordings, by pass

**Status:** **Approved** (issue #79, PR #89 review)
**Date:** 2026-11-14
**Options:** the path from each scenario's expected tools, typed into
scenarios.json · from the recording, generated at build time · from the
recording, worked out in the browser
**Decision:**
- Each card's path is worked out in the browser from its recording: every
  tool result Python sent back, grouped by pass. Tools in one pass are joined
  with "+", passes with "→", and a failed tool is followed by "→ error". So
  scenario 4 reads `evaluate_job + research_company → flag_for_review` and
  scenario 6 reads `evaluate_job → error → evaluate_job`.
- A run that calls no tool (scenario 9) says "no tools called".
- The page fetches all nine recordings when it loads, once each, and the run
  view reuses them.
- A card's own words never state the rating. This loosens #79's "cards never
  state the outcome" (PR #89 review). Its own words are the setup line and
  the "Simulated failure" tag. The full path stays, including paths that end
  in `flag_for_review` (scenarios 2 and 4): it's the card's most useful line.
  The names of scenarios 8 and 9 ("Runaway loop stopped", "Reply cut off")
  stay too: for a break-the-agent scenario, the failure is the premise, not
  the ending.
**Reasoning:** the recording is what happened, so the path can't drift from
it. Expected tools can't show an error or two tools in one pass, and a build
step would add a generated file to keep in sync. A browser test compares each
path with one worked out separately in Python.
**What would change it:**
- The nine recordings get large enough to slow the first load. They're about
  820 KB together, uncompressed. Then the paths move to a generated file.
- First-visitor tests show the paths spoil the runs. Then the path could
  stop before the last tool.

## D40 — Which principle each guard serves

**Status:** **Approved** (issue #80, PR #90)
**Date:** 2026-11-14
**Decision:** every guard (E-step) is listed once, under the principle it
serves:
- **Errors go back to the model as information:** E1 `tool_failed`
  (scenario 6), E5 `grader_cut_off`, E8 `invalid_grade`. All three end as an
  `is_error` tool result Claude can act on.
- **Fail closed on the unknown:** E2 `unknown_tool` (scenario 7), E3
  `reply_cut_off` (scenario 9), E9 `unexpected_stop`, E6 `api_call_failed`,
  E7 `no_final_answer`. Each meets something the agent can't safely act on and
  ends the run, or refuses the request, with a clear message instead of
  guessing.
- **Bound the loop:** E4 `pass_cap` (scenario 8).

A guard a scenario shows gets a Watch it button. Tests check that its
scenario's recording really catches it. The other five are marked "Tested,
not demonstrated", with a test that's checked to exist.
**Reasoning:** "Errors go back" is about what Claude gets to see; "fail
closed" is about what the agent refuses to do. E3 sits under fail closed,
not bound the loop: a cut-off reply is never acted on (D22), whatever pass
it's on.
**What would change it:** a scenario added for a tested guard (it gets a
Watch it), or a guard whose effect changes, e.g. E6 retrying instead of
stopping.

## D41 — How it was built: numbers counted from the repo, links to GitHub

**Status:** **Approved** (issue #81, PR #92 review)
**Date:** 2026-11-14
**Decision:**
- Every number in How it was built comes from `build_numbers.py`, written to
  `site/numbers.json` and filled in by the page. The counts:
  - **Tests:** test cases unittest finds.
  - **Scenarios:** by group.
  - **Guards:** E-steps, and how many a recording shows caught.
  - **Decisions:** entries in this file, and how many say Approved or
    Proposed. 16 early entries have no Status line, and one says "closed by
    D28", so the page shows logged, approved and proposed.
  - **Merged pull requests:** `Merge pull request #` commits before HEAD.
    Leaving HEAD out means the count a PR commits still matches once it's
    merged, because its merge commit is then HEAD.
- Every PR reruns the script (CLAUDE.md). A test fails if the file and a
  fresh count differ.
- The page may link to this repo on GitHub, in `<a href>` only, and only to
  files that exist in it. Links aren't requests: D31's "loads nothing but its
  own files" still holds, and a test enforces both.
- The footer has no contact link yet (your call in #81).

**Reasoning:** numbers typed by hand go stale silently. Counting from the
repo, and testing the count, keeps the page honest as it grows.
**What would change it:**
- Squash merges, which leave no "Merge pull request" commit. Then count with
  the GitHub API at build time.
- The repo staying private at launch. Then the links come out, or copies of
  the docs ship with the page.

