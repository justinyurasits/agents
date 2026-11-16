# Steps shown on the page

Each step: title, what's happening (max two sentences, for someone who has
never seen an agent), and the code it points to.

Each step has a **step id**. The code a step points to is marked in
`agent.py` with a `# STEP: <step id>` comment on the line above it. Line
numbers are never written here: they're looked up from the markers when a
run is recorded (`code_refs.py`), so they can't go stale when the code moves.

## START (once)

### 1. The agent starts

Step id: `agent_starts`

A job posting is handed to the agent, which starts the loop.
Code: `# STEP: agent_starts` in agent.py (`final = run_agent(job, recorder=recorder, fault=...)`)

### 2. The conversation is set up

Step id: `conversation_setup`

Python creates the conversation Claude will see. It starts with one
message: the job to evaluate.
Code: `# STEP: conversation_setup` in agent.py (`messages = [...]`)

## EACH PASS OF THE LOOP (repeats until Claude is done, at most 10 times)

### 3. Python sends the conversation to Claude

Step id: `send_to_claude`

Python sends Claude the whole conversation so far, plus instructions and a
list of tools it may ask for. Claude keeps no memory between calls, so
everything goes every time.
Code: `# STEP: send_to_claude` in agent.py (`client.messages.create(...)`)

### 4. Claude decides what to do

Step id: `claude_decides`

Claude reads the job and the tool descriptions, then decides: ask for a
tool, or answer directly. This happens on Anthropic's servers. Claude
can't run anything itself; it can only send back a request.
Code: none — this is the model's choice

### 5. Python checks Claude's reply

Step id: `check_reply`

Every reply carries a label saying why Claude stopped: "I want a tool run,"
"I'm done," or "I ran out of room." Python reads the label to decide what
happens next; a reply that ran out of room is unfinished, so Python stops there.
Code: `# STEP: check_reply` in agent.py (`if response.stop_reason == "end_turn":`)

### 6. Python saves Claude's turn

Step id: `save_turn`

Claude's request is added to the conversation, so the next call shows
Claude what it already asked for. The request carries an ID that the
answer will have to match.
Code: `# STEP: save_turn` in agent.py (`messages.append({"role": "assistant", ...})`)

### 7. Python runs the tool Claude asked for

Step id: `run_tools`

Python finds each tool request in Claude's reply and runs the matching
function with the details Claude filled in. Claude can ask for more than
one tool at once; Python runs them one after another.
Code: `# STEP: run_tools` in agent.py (`for tool_block in ...` and the dispatch)

#### 7a. Inside evaluate_job: code checks your hard rules

Step id: `hard_screen`

Before any rating call, code checks the fixed rules: the role must be remote,
and its lowest base salary must be at least $180K. A posting that breaks one
is rated IGNORE right here and the grader is never asked; a rule that can't
be checked (no salary given, say) is skipped, not failed. This is a rule
working as intended, not an error.
Code: `# STEP: hard_screen` in agent.py (`if failed:`)

#### 7b. Inside evaluate_job: a second Claude grades the job

Step id: `inner_grader`

This tool asks a separate Claude call one question that needs judgment:
does this role build hands-on AI experience? It answers yes or no, and code
turns that into the rating (yes: STRONG, no: WORTH REVIEWING). It's a one-off
question with no tools and no loop.
Code: `# STEP: inner_grader` in agent.py (`eval_response = client.messages.create(...)`)

#### 7c. Inside research_company: Python looks up stored company facts

Step id: `research_company`

When a posting doesn't list pay, Claude can ask this tool about the company:
its size, its stage, and typical base pay for the role's level. The facts
come from a file of demo data written for this page, not from the web. A
company that isn't on file is a normal answer ("not found"), not an error;
Claude decides what to do next.
Code: `# STEP: research_company` in agent.py (`if name is None:`)

### 8. The result goes back into the conversation

Step id: `results_back`

Python adds the tools' results to the conversation in one message. Each
result is tagged with the same ID as the request it answers, so Claude
knows which is which. Then the loop goes back to step 3.
Code: `# STEP: results_back` in agent.py (`messages.append({"role": "user", "content": tool_results})`)

## FINISH (once)

### 9. Claude says it's done

Step id: `claude_done`

On the next pass, Claude sees the result, decides nothing else is needed,
and writes its final answer. The label on the reply now says "I'm done."
Code: same as step 5, `# STEP: check_reply` in agent.py
(`if response.stop_reason == "end_turn":`). Step 9 is that check on the
pass where Claude says it's done, so it has no marker of its own.

### 10. The answer comes back

Step id: `answer_returned`

Python takes Claude's final text and hands it back as the result. The loop
ends.
Code: `# STEP: answer_returned` in agent.py (`answer = next((b.text for b in response.content if b.type == "text"), None)`)

## WHEN SOMETHING GOES WRONG

Each guard in the code gets a step here. A guard added later gets one too.

### E1. A tool fails

Step id: `tool_failed`

A tool raised an error instead of returning a result. Python doesn't crash:
it sends the error back to Claude as that tool's result, marked as an error,
and Claude decides what to do next.
Code: `# STEP: tool_failed` in agent.py (`except Exception as e:`)

### E2. Claude asks for a tool that doesn't exist

Step id: `unknown_tool`

Claude asked for a tool name that isn't defined. Python answers with an
error that names it and lists the real tools, so Claude can pick again.
Code: `# STEP: unknown_tool` in agent.py (`raise ValueError(f"Unknown tool ...")`)

### E3. Claude's reply is cut off

Step id: `reply_cut_off`

Claude's reply hit the length limit and stopped part-way. Python won't act
on an unfinished reply, so it ends the run and says the reply was cut off.
Code: `# STEP: reply_cut_off` in agent.py (`if response.stop_reason == "max_tokens":`)

### E4. Too many passes

Step id: `pass_cap`

Claude still hasn't finished after 10 trips around the loop. Python stops
the run so a stuck agent can't loop, and spend money, forever.
Code: `# STEP: pass_cap` in agent.py (`answer = f"Stopped after ... passes without finishing."`)

### E5. The grader's reply is cut off

Step id: `grader_cut_off`

Inside evaluate_job, the grader's reply hit the length limit before its
rating was complete. The tool reports that it was cut off, rather than
"invalid JSON," and the error goes back to Claude like any tool failure (E1).
Code: `# STEP: grader_cut_off` in agent.py (`if eval_response.stop_reason == "max_tokens":`)

### E6. The call to Claude fails

Step id: `api_call_failed`

Python's call to Claude failed before any reply came back: the network was
down, the service was busy, or the API key was wrong. With no reply to act on,
Python stops the run and says which error it was.
Code: `# STEP: api_call_failed` in agent.py (`except anthropic.APIError as e:`)

### E7. Claude finishes without an answer

Step id: `no_final_answer`

Claude said it was done, but its reply had no text in it, for example only
its thinking. Python returns a message saying there was no final answer
instead of crashing at the very last step.
Code: `# STEP: no_final_answer` in agent.py (`if answer is None:`)

### E8. The grader's rating isn't valid

Step id: `invalid_grade`

The grader's reply was valid JSON but not a real answer: an answer that
isn't yes or no, missing reasons, or the wrong shape. The tool reports exactly
what was wrong, and the error goes back to Claude like any tool failure (E1).
Code: `# STEP: invalid_grade` in agent.py (`if problem:`)

### E9. Claude stops for a reason the agent doesn't handle

Step id: `unexpected_stop`

Claude's reply carries a label this agent has no plan for, for example
"refusal" (Claude declined to answer). Python won't guess what to do with it,
so it stops the run and says which label it was.
Code: `# STEP: unexpected_stop` in agent.py (`if response.stop_reason != "tool_use":`)

## CHECKS (shown in the Python box when they pass)

Each guard above runs its check every time, not only when something goes
wrong. A check that passes isn't a step on the page: it lights its badge in
the Python box for a moment, with its line below, and gets a card in the
Payload tab. A check that catches something is shown as its E-step instead.

One row per check and the step it runs at. "Runs at" is the step where the
check passes; "Caught as" is the E-step it becomes when it catches something
("none": the check only routes). The same check can run at two places and be
caught as two different E-steps, like `max_tokens`. "Passed means" is the
card's line when the check passes; "If it catches something" is what Python
does then. The page takes a card's wording from here, from those steps, and
the code from the caught-as step's `# STEP:` marker (#115, #118).

| Check | Runs at | Caught as | What it checks | Passed means | If it catches something |
|---|---|---|---|---|---|
| `pass_count` | `send_to_claude` | `pass_cap` | Checks this run hasn't hit the 10-pass limit. | The run is under its pass limit, so Python calls Claude again. | Python stops the run and says how many passes it made. |
| `api_call_succeeded` | `send_to_claude` | `api_call_failed` | Checks the call to Claude came back with a reply. | Python got a reply from Claude, so this guard didn't fire. | Python stops the run and says which error it was. |
| `stop_reason` | `check_reply`, `claude_done` | none | Reads the label on Claude's reply: run a tool, or done. | Python read the label on Claude's reply and took that path. | Nothing to catch: this check only routes the loop, to the tools or to the end. |
| `max_tokens` | `check_reply` | `reply_cut_off` | Checks the reply wasn't cut off by the length limit. | Claude's reply was complete, so Python can act on it. | Python stops the run and says the reply was cut off. |
| `stop_reason_known` | `check_reply` | `unexpected_stop` | Checks the label is one this agent knows how to handle. | The label was one this agent knows how to handle. | Python stops the run and says which label it was. |
| `tool_exists` | `run_tools` | `unknown_tool` | Checks the tool Claude asked for is a real one. | The tool Claude asked for is real, so Python runs it. | Python sends Claude an error naming the real tools, so it can pick again. |
| `tool_succeeded` | `run_tools` | `tool_failed` | Checks the tool finished without an error. | The tool returned a result, so Python sends it to Claude. | Python sends the error to Claude as the tool's result, marked as an error. |
| `max_tokens` | `inner_grader` | `grader_cut_off` | Checks the grader's reply wasn't cut off by the length limit. | The grader's reply was complete, so the tool can read it. | The tool reports the reply was cut off, and the error goes back to Claude. |
| `grade_valid` | `inner_grader` | `invalid_grade` | Checks the grader answered yes or no, with reasons. | The grader answered yes or no, with reasons. | The tool reports what was wrong, and the error goes back to Claude. |
| `final_text_present` | `answer_returned` | `no_final_answer` | Checks Claude's last reply has text to hand back. | Claude's last reply has text, so Python hands it back. | Python returns a message saying there was no final answer. |

## RULES (checked in code at step 7a)

A rule applies one of Justin's decisions. It isn't a guard: a rule that
rejects a posting is the agent working as intended, not an error. The page
takes each rule card's wording from here (#115), and its code from the
`# STEP:` marker in "Code at" (#118).

| Rule | Name | Code at | What it decides | If a posting fails it |
|---|---|---|---|---|
| `remote` | Remote | `hard_screen` | The role must be remote. | Code rates it IGNORE and the grader is never asked (D28). |
| `comp_floor` | Salary floor | `hard_screen` | The lowest base salary must be at least $180K. | Code rates it IGNORE and the grader is never asked (D28). |
