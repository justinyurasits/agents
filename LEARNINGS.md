# Learnings

What building these agents has taught me, kept as I go. Each entry says where it came from, so it can be checked against the code, issues and PRs.

Newest at the bottom of each section.

## How agents work

- **Claude decides; Python executes.** The model never runs anything. It returns a request (`tool_use`), and code decides whether and how to carry it out. "The agent" is the loop, the tools and the model together. _(job-evaluator, first walkthrough)_
- **The conversation is the memory.** Each API call is independent. Claude "remembers" only because the full messages list is sent every time. Drop an append and the agent forgets what it just did. _(job-evaluator, step 5 and 8)_
- **Tool descriptions steer the agent.** Removing compensation from a posting made Claude pick `flag_for_review` over `evaluate_job` with no code change. The description was the control logic. _(compensation test)_
- **Every request gets an answer with the same ID, even when the answer is an error.** Each `tool_use` needs a matching `tool_result` in the next message, or the next call is rejected. _(#7, #11)_
- **Find content by type, never by position.** The model can return a thinking block before its text. Code that assumed `content[0]` was text crashed. _(ThinkingBlock crash, #4)_
- **A guard turns a crash into information the model can act on.** Sending a tool error back as a `tool_result` marked `is_error` lets Claude retry, switch tools, or explain. Without it, the run just dies. _(#8, #11)_
- **In practice, Claude stops retrying on its own.** Live runs showed one retry, then an explanation. The loop cap is a backstop for when it doesn't, not the normal stop. _(#46 live runs)_
- **The model for judgment, code for rules.** Anything already decided (a salary floor, a remote requirement) belongs in code: same answer every time, testable, readable. The model gets only what needs interpretation. Same reason a bank never lets the model decide whether a caller is authenticated. _(#26, D28)_
- **Claude extracts, code decides.** Claude reads messy text and fills in clean fields; code applies the rule to those fields. Check what the model hands you: an unreadable value should be skipped and recorded, not trusted. _(#26)_
- **Smaller questions get more reliable answers.** The rating prompt went from three criteria including pay and location to one yes/no question about the work. _(#26)_
- **Guards, rules and routing are different things.** Guards catch failures. Rules apply decisions already made. Routing decides where the loop goes next. Treating them as one confuses both the code and anyone reading it. _(stop_reason discussion, #51 review)_
- **Fail closed on the unknown.** The loop handles the stop reasons it knows and stops on anything else, rather than listing known bad ones. A stop reason the API adds later is caught automatically. _(#21, D29)_
- **Guards catch failures; defensive handling prevents them.** Fence stripping, finding text by type and answering every tool request never "catch" anything: they handle every input correctly so nothing fails. Keeping them out of the guard list keeps "guard" meaning one thing. *(#63)*
- **Choosing a tool is intent classification.** Each tool description is a definition Claude matches the input against. Adding `research_company`, whose description overlapped `flag_for_review` on "no pay listed," moved scenarios 2 and 4 to a new path with no code change. Where two tools overlap, the model picks the order unless the descriptions state precedence. _(#65, PR #66)_
- **Adding a tool can change behavior you didn't touch.** A new description competes with every existing one. _(PR #66)_

## Showing how an agent works

- **Show what happened; label everything else.** Recorded data comes only from real runs. Teaching explanations are labeled as written for the page. Never present an explanation as the model's reasoning. _(BRIEF, truthfulness rule)_
- **Record real runs and replay them.** A demo that depends on a live API call can fail in front of the person you most want to impress. _(D12)_
- **The interesting moments are the boundary crossings.** What goes from Python to Claude, what comes back, what goes to a tool. Keep the architecture on screen and animate what crosses it. _(D15)_
- **Error handling is the most convincing part of the demo.** Happy-path agent demos are everywhere; watching an agent recover from a failure is what shows it was built properly. _(D21)_
- **A mockup shows one moment; the real page has to decide every moment.** The mockup answered what the page looks like at the failure. It didn't answer what an arrow shows between crossings, or how long a caught guard stays lit. Each of those had to be decided once the page played a whole run. _(#57, PR #60)_
- **Show only what's happening now.** A dashed "next · request" arrow, drawn during the pass count check, made it look as if the check sent the request. The Next card already says what comes next; the map should show only what's crossing at this step. _(PR #60 review)_
- **Events aren't steps.** The trace records 47 events for scenario 6; a visitor steps through 23. Checks that pass flash their badge with one line instead of being steps, and the events of one action (the hard rules, the grader call) are grouped. Saving the turn and adding results back stay, because they're what make "the conversation is the memory" visible. _(PR #60, D32)_
- **Routing isn't a check, even when it's recorded like one.** "Claude says it's done" is logged as a passing `stop_reason` check, but it's one of Claude's two decisions in the run and the reason the loop ends. The page shows it as a step. _(PR #60 review)_
- **One source for every explanation.** Step text and the one-line check explanations live only in STEPS.md, and a script builds the page's copy. A test fails if they drift. _(#57, build_steps.py)_

## Testing an agent

- **Test the code and the behavior separately.** Unit tests with a fake client prove the Python works, with no API calls and the same result every time. Recorded scenarios prove what Claude actually does on known inputs. Neither replaces the other. _(tests/, record.py)_
- **Break it on purpose.** Fault injection makes a tool fail, invents an unknown tool, forces a runaway loop, or cuts a reply off, so every guard is seen working in a real run instead of trusted. _(#48, faults.py)_
- **A description change is a code change.** Any PR that adds a tool or changes a description, prompt or rubric re-runs every scenario. That's the only reason the scenario 2 and 4 shift was caught. _(#69)_
- **Don't edit the expectation to make it pass.** A mismatch is information. Change the expected path only when you've decided the new path is right. _(#69)_
- **One PASS isn't proof.** The model varies run to run. Reliability means pass rates over many runs, which is next. _(open)_

## Building with an AI coding agent

- **The issue is the spec.** The coding agent builds exactly what the issue says, so acceptance criteria have to be input → expected result, something you can actually check. _(every issue)_
- **Ask for a plan before a big change.** For tracing (#1), a plan as an issue comment, then three small PRs, kept each review manageable. _(#1, PRs #34–#36)_
- **Verify from the output, not from the agent's report.** Run the tests yourself. Best practice: break the fix on purpose and confirm the tests fail. _(#5, #9 onward)_
- **Rules belong in a file the agent reads every time.** `CLAUDE.md` holds the workflow; every review that finds a gap becomes a new rule. _(CLAUDE.md)_
- **Two workers can't share one checkout.** The coding agent's uncommitted work rode along when I switched branches and landed in the wrong PR. Fix: the agent always works in its own git worktree. _(PR #39)_
- **A pushed key is a leaked key.** Revoke it; deleting it from the file doesn't remove it from history. And a stale key in the shell can silently override `.env`. _(day one)_
- **Define the product before writing issues.** Issues written ahead of the brief kept raising "what is this for?" Once the brief existed, every issue could be checked against it. _(BRIEF)_
