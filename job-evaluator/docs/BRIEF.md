# job-evaluator — Product brief

One page. Every milestone and issue should trace back to a line here. If it doesn't, it's post-v1.

## What it is

A learning and demonstration tool: an interface where you watch a simple agent work, step by step.

It runs seven prepared scenarios, each chosen to show a different agent behavior:

1. **Clean run** — complete posting, one tool, done.
2. **Missing info** — no comp listed; Claude picks a different tool.
3. **Multi-tool** — a tool's result changes what the agent does next.
4. **Tool fails, agent recovers** — the error goes back to Claude, and the agent recovers.
5. **Two tools at once** — Claude asks for two tools in one reply; both results go back together.
6. **Hard screen in code** — code rejects the posting before Claude is ever asked.
7. **Runaway loop stopped** — a tool keeps failing and the loop cap stops the run.

Scenario 4 is built end to end first (D16), then the rest.

Each run plays out at a readable pace, with a short pause between major steps. Every step shows what's happening in plain English, the line of code running, and the data at that moment.

The job evaluation is the scenario. The product is visibility into how an agent works.

## Who it's for

- **People learning how agents work** — anyone who wants to see a real agent loop, not a diagram of one.
- **People evaluating my work** — hiring managers, recruiters, potential clients. They should come away thinking "that's actually really cool," and be able to follow the link from any step to the code, the issue, or the decision behind it.
- **Me** — building it is how I learn this properly.

## The moment that matters

When I walk someone through it — in an interview, a client conversation, or a training class — and the page carries the explanation: what the agent decided, why the run took the path it did, and how it handled the error.

## What's on the page

1. **Hero** — one sentence on what this is; pick a scenario and press Run.
2. **The run (Execution Explorer, D15)** — an execution map that stays visible: Claude | Python | Tools, with the data that crosses each arrow and a tool's own Claude call drawn as a separate path. Below it: the four questions, a timeline grouped by pass, the step explanation, and an inspector with State change (messages[] before and after), Code, Payload, and Claude's response. Controls to pause, step, and change speed.
3. **How it works** — the anatomy: trigger → loop → Claude decides → tools → results go back → error handling → stop. Each part links to its code and to the issue or decision behind it.
4. **How it was built** — the board, issues, PRs, and decision log. Built with Claude Code, issue by issue.

## Design principle

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
- Seven scenarios; failures forced with labeled switches (D13).
- research_company uses stored company data (D14).
- Run view: Execution Explorer, linear map (D15).
- Scenario 4 first (D16).
