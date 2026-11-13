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

## Showing how an agent works

- **Show what happened; label everything else.** Recorded data comes only from real runs. Teaching explanations are labeled as written for the page. Never present an explanation as the model's reasoning. _(BRIEF, truthfulness rule)_
- **Record real runs and replay them.** A demo that depends on a live API call can fail in front of the person you most want to impress. _(D12)_
- **The interesting moments are the boundary crossings.** What goes from Python to Claude, what comes back, what goes to a tool. Keep the architecture on screen and animate what crosses it. _(D15)_
- **Error handling is the most convincing part of the demo.** Happy-path agent demos are everywhere; watching an agent recover from a failure is what shows it was built properly. _(D21)_

## Building with an AI coding agent

- **The issue is the spec.** The coding agent builds exactly what the issue says, so acceptance criteria have to be input → expected result, something you can actually check. _(every issue)_
- **Ask for a plan before a big change.** For tracing (#1), a plan as an issue comment, then three small PRs, kept each review manageable. _(#1, PRs #34–#36)_
- **Verify from the output, not from the agent's report.** Run the tests yourself. Best practice: break the fix on purpose and confirm the tests fail. _(#5, #9 onward)_
- **Rules belong in a file the agent reads every time.** `CLAUDE.md` holds the workflow; every review that finds a gap becomes a new rule. _(CLAUDE.md)_
- **Two workers can't share one checkout.** The coding agent's uncommitted work rode along when I switched branches and landed in the wrong PR. Fix: the agent always works in its own git worktree. _(PR #39)_
- **A pushed key is a leaked key.** Revoke it; deleting it from the file doesn't remove it from history. And a stale key in the shell can silently override `.env`. _(day one)_
- **Define the product before writing issues.** Issues written ahead of the brief kept raising "what is this for?" Once the brief existed, every issue could be checked against it. _(BRIEF)_
