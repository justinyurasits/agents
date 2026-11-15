# job-evaluator — Product brief

One page. Every milestone and issue should trace back to a line here. If it doesn't, it's post-v1.

## What it is

A learning and demonstration tool: an interface where you watch a simple agent work, step by step.

It runs nine prepared scenarios in two groups, each chosen to show a different agent behavior (D21; the list is `scenarios/scenarios.json`, shown in [SCENARIOS.md](SCENARIOS.md)):

**Normal runs**

1. **Clean run** — complete posting, one tool, done.
2. **Missing info** — no comp listed; Claude picks a different tool.
3. **Multi-tool** — a tool's result changes what the agent does next.
4. **Two tools at once** — Claude asks for two tools in one reply; both results go back together.
5. **Hard screen in code** — code rejects the posting before the grader is ever asked.

**Break the agent** (a fault is injected on purpose and labeled on the page)

6. **A tool fails** — the error goes back to Claude, and the agent recovers.
7. **Unknown tool** — Claude asks for a tool that doesn't exist; Python answers with the real ones.
8. **Runaway loop stopped** — a tool keeps failing and the loop cap stops the run.
9. **Reply cut off** — Claude's reply runs out of room; the run stops with a clear message.

Scenario 6, a tool fails (numbered 4 when D16 was written), was built end to end first (D16, page v0 #57), then the rest.

Each run plays out at a readable pace, with a short pause between major steps. Every step shows what's happening in plain English, the line of code running, and the data at that moment.

The job evaluation is the scenario. The product is visibility into how an agent works.

## Who it's for

- **People learning how agents work** — anyone who wants to see a real agent loop, not a diagram of one.
- **People evaluating my work** — hiring managers, recruiters, potential clients. They should come away thinking "that's actually really cool," and be able to follow the link from any step to the code, the issue, or the decision behind it.
- **Me** — building it is how I learn this properly.

## The moment that matters

When I walk someone through it — in an interview, a client conversation, or a training class — and the page carries the explanation: what the agent decided, why the run took the path it did, and how it handled the error.

## What's on the page

One long page. A header bar jumps to each section. Every claim the page makes
can be watched: principles and guardrails each have a "Watch it" button that
loads the matching scenario into the run view and plays it.

1. **Hero + the run** — one sentence on what this is, my name, and the
   Execution Explorer directly below: scenario chooser in two groups (Normal
   runs / Break the agent), playback that starts paused. Before the run, an
   intro gives the setup (what's different about this input, without the
   ending) and what to watch for. On the last step, a short summary card says
   what happened and why it matters. Both are labeled "Written for this page"
   (#75). Still to come: links on the card to watch another scenario or read
   How it works, once that section exists.
2. **How it works** — the mechanics, briefly: the loop, tools, and the
   conversation as memory.
3. **Design principles** — six, each one sentence with a Watch it button:
   1. The model for judgment, code for rules (scenario 5)
   2. A guard turns a crash into information the model can act on (scenario 6)
   3. Claude decides; Python executes (any run)
   4. The conversation is the memory (scenario 1)
   5. Tool descriptions steer the agent (scenario 2)
   6. Show what happened; label everything else (the page itself)
4. **Guardrails** — every failure the agent handles: what goes wrong, what
   catches it, what happens next, and a Watch it button. Guards with no
   scenario are marked "tested, not shown" and link to their test.
5. **How it was built** — the process (brief → decisions → issues with
   acceptance criteria → built by Claude Code → reviewed by me → tested),
   real counts linked to GitHub, three key decisions, and three or four
   learnings about building with an AI coding agent, linking to
   LEARNINGS.md. Claude Code wrote the code; I wrote the specs and reviewed
   every change.
6. **Footer** — name, one line, links to the repo, LinkedIn, and my site.

## The four questions (page design rule)

At every step, a viewer can answer four questions: Who is executing? What information do they have? What caused this? What happens next?

## Truthfulness rule

The page shows what actually happened and labels everything else.

- Recorded data (requests, responses, tool calls, results, errors, Claude's returned thinking) comes only from real runs.
- Teaching explanations are written separately and labeled "written for this page." The page never presents its own explanation as Claude's.
- Simulated failures are labeled on the page.

## Non-goals (v1)

- Not a job-search or resume-evaluation tool.
- Visitors can't enter their own job, profile, or data. It runs the prepared scenarios only.
- No accounts, no saved data.
- No rich evaluation output (THE_METHOD-style). The evaluation only needs to be believable.
- No multi-agent.

## How we'll know it worked

- I use it to explain how an agent works to a hiring manager or potential client.
- I can use it as a demo in a training class.
- A first-time visitor can say who decides, who executes, and how information moves after watching one run. (Test on two people before publishing.)

## Constraints

- **Time box:** two weeks from M2 start to public link.
- **Must never fail in a live demo.** No dependence on an API call succeeding while someone is watching.
- **Near-zero running cost.**
- **Free hosting** (GitHub Pages, D12).
- **Every recorded run is real:** produced by the actual agent, with the trace file linked.
- **Fictional companies only** in scenarios; no real company paired with an invented posting.

## Decided

- Recorded runs only; static page (D12).
- Seven scenarios; failures forced with labeled switches (D13, superseded by D21).
- research_company uses stored company data (D14).
- Run view: Execution Explorer, linear map (D15).
- Scenario 4 first (D16); now scenario 6, after renumbering.
- Tests use the standard library's unittest (D17).
- A tool's exception goes back to Claude as an `is_error` tool result (D18).
- An unknown tool name gets an error listing the real tools (D19).
- Several tool requests in one reply run in order, with one result message (D20).
- Nine scenarios: 5 normal runs + 4 break-the-agent runs (D21).
- A cut-off reply is never acted on (D22).
- Code references come from `# STEP:` markers, never hand-written line numbers (D23).
- Trace format: one flat event per step, every key always present (D24).
- Every guard check is recorded; "caught" means something went wrong (D25).
- A failed call to Claude stops the run, naming only the error type (D26).
- Faults are injected into real runs and labeled; the cap is lowered for the runaway demo (D27).
- Hard rules in code; the grader answers one yes/no question (D28).
- A stop reason the agent doesn't handle stops the run (D29).
- Recordings are checked against each scenario's `expect` (D30).
- Page v0 lives in `job-evaluator/site/`, ships its fonts, and shows Claude's words only under "Claude's response" (D31).
- Page steps: passing checks aren't steps; caught checks and "Claude says it's done" are (D32).
- One page, six sections, a "Watch it" button on every claim (D33).
- Browser tests check the page's rules in Chromium (Playwright, a dev-only requirement) and skip when it isn't installed. Claude's words are searched in every tab but its own; the only exemption is tool_result content in Payload (D38).
