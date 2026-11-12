# Steps shown on the page

Each step: title, what's happening (max two sentences, for someone who has
never seen an agent), and the code it points to.

## START (once)

### 1. The agent starts

A job posting and a candidate profile are handed to the agent, which
starts the loop.
Code: agent.py · `final = run_agent(job)` (line 206)

### 2. The conversation is set up

Python creates the conversation Claude will see. It starts with one
message: the job to evaluate.
Code: agent.py · `messages = [...]` (line 124)

## EACH PASS OF THE LOOP (repeats until Claude is done)

### 3. Python sends the conversation to Claude

Python sends Claude the whole conversation so far, plus instructions and a
list of tools it may ask for. Claude keeps no memory between calls, so
everything goes every time.
Code: agent.py · `client.messages.create(...)` (lines 133–139)

### 4. Claude decides what to do

Claude reads the job and the tool descriptions, then decides: ask for a
tool, or answer directly. This happens on Anthropic's servers. Claude
can't run anything itself; it can only send back a request.
Code: none — this is the model's choice

### 5. Python checks Claude's reply

Every reply carries a label saying why Claude stopped: "I want a tool run"
or "I'm done." Python reads the label to decide what happens next.
Code: agent.py · `if response.stop_reason == "end_turn":` (line 150)

### 6. Python saves Claude's turn

Claude's request is added to the conversation, so the next call shows
Claude what it already asked for. The request carries an ID that the
answer will have to match.
Code: agent.py · `messages.append({"role": "assistant", ...})` (line 156)

### 7. Python runs the tool Claude asked for

Python finds the tool request in Claude's reply and runs the matching
function with the details Claude filled in.
Code: agent.py · `tool_block = next(...)` and the dispatch (lines 163–177)

#### 7a. Inside evaluate_job: a second Claude grades the job

This tool asks a separate Claude call to grade the job against the
candidate's criteria and return a structured rating. It's a one-off
question with no tools and no loop.
Code: agent.py · `eval_response = client.messages.create(...)` (line 99)

### 8. The result goes back into the conversation

Python adds the tool's result to the conversation, tagged with the same ID
as Claude's request so Claude knows which question it answers. Then the
loop goes back to step 3.
Code: agent.py · `messages.append({"type": "tool_result", ...})` (lines 181–188)

## FINISH (once)

### 9. Claude says it's done

On the next pass, Claude sees the result, decides nothing else is needed,
and writes its final answer. The label on the reply now says "I'm done."
Code: agent.py · `if response.stop_reason == "end_turn":` (line 150)

### 10. The answer comes back

Python takes Claude's final text and hands it back as the result. The loop
ends.
Code: agent.py · `return next(b for b in response.content if b.type == "text").text` (line 153)
