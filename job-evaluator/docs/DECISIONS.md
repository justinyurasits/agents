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
