"""
Job Evaluator Agent — end-to-end, one pass.
`# STEP: <step_id>` markers label the code each step in docs/STEPS.md points to.

Run:
    pip install -r requirements.txt
    cp .env.example .env    # then put your Anthropic API key in .env
    python agent.py
"""

import json
import re
import anthropic
from dotenv import load_dotenv

import tracing

load_dotenv(override=True)
client = anthropic.Anthropic()          # reads ANTHROPIC_API_KEY from env
MODEL = "claude-sonnet-5-5"
SYSTEM_PROMPT = "You help Justin triage job postings. Use the tools provided."
MAX_PASSES = 10    # outer API calls per run; stops a runaway loop (and its cost)
MAX_TOKENS = 2000  # longest reply Claude may write, for both API calls

# ---------------------------------------------------------------------------
# TOOL DEFINITIONS — the only thing Claude ever sees about your tools.
# Plain dicts. Sent with every outer API call.
# ---------------------------------------------------------------------------
tools = [
    {
        "name": "evaluate_job",
        "description": (
            "Rate a job posting against Justin's criteria. Use when the posting "
            "has enough information to rate: company, role, location/remote "
            "status, and compensation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company":         {"type": "string"},
                "role_title":      {"type": "string"},
                "job_description": {"type": "string"},
                "location":        {"type": "string"},
                "remote":          {"type": "boolean"},
                "compensation":    {"type": "string"},
            },
            "required": ["company", "role_title", "job_description"],
        },
    },
    {
        "name": "flag_for_review",
        "description": (
            "Flag a posting for manual review. Use when key information "
            "(compensation, remote status) is missing or ambiguous, so the "
            "job can't be rated reliably."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company":      {"type": "string"},
                "role_title":   {"type": "string"},
                "missing_info": {"type": "string"},
            },
            "required": ["company", "role_title", "missing_info"],
        },
    },
]

# ---------------------------------------------------------------------------
# TOOL FUNCTIONS — real Python. Claude never sees these.
# ---------------------------------------------------------------------------
RUBRIC = """You rate job postings for Justin.
STRONG: remote, $180K+ base, and builds his AI consulting practice.
WORTH REVIEWING: meets two of the three.
IGNORE: meets one or none.
Respond with JSON only: {"rating": "...", "reasons": ["...", "..."]}"""

# The only ratings the grader may give. A fixed rule, so it's checked in code
# (CLAUDE.md), not left to the prompt.
RATINGS = ("STRONG", "WORTH REVIEWING", "IGNORE")


def grade_problem(grade):
    """What's wrong with the grader's parsed JSON, or None if it's valid.

    Valid means: an object with `rating` (one of RATINGS) and `reasons` (a
    list of strings). Other keys are allowed. Pure function, no API call.
    """
    if not isinstance(grade, dict):
        return f"The grader's reply is a JSON {type(grade).__name__}, not an object."
    if "rating" not in grade:
        return "The grader's reply has no 'rating'."
    if grade["rating"] not in RATINGS:
        return (f"The grader's rating {grade['rating']!r} isn't one of "
                f"{', '.join(RATINGS)}.")
    if "reasons" not in grade:
        return "The grader's reply has no 'reasons'."
    reasons = grade["reasons"]
    if not isinstance(reasons, list) or not all(isinstance(r, str) for r in reasons):
        return "The grader's 'reasons' isn't a list of strings."
    return None


# A reply wrapped in a markdown code fence: ``` or ```json, then the JSON,
# then a closing ```. The (.*?) group captures just the JSON in between.
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def strip_json_fences(text):
    """Return text with any surrounding ```json ... ``` fence removed.

    Plain JSON with no fence comes back unchanged (just trimmed).
    Pure string cleanup, no API call, so it can be tested on its own.
    """
    text = text.strip()
    match = _FENCE.match(text)
    return match.group(1) if match else text


def evaluate_job(company, role_title, job_description,
                 location="Unknown", remote="Unknown", compensation="Unknown"):
    job_summary = (
        f"Company: {company}\nRole: {role_title}\nLocation: {location}\n"
        f"Remote: {remote}\nCompensation: {compensation}\n\n{job_description}"
    )

    # A separate, one-off Claude call. No tools, no loop.
    # The outer `messages` list is not touched.
    rec = tracing.active()            # the run's recorder, if any
    grader_messages = [{"role": "user", "content": job_summary}]
    print("  [step 7] evaluate_job → inner Claude call (API call #2)")
    rec.inner_api_request(RUBRIC, grader_messages)
    # STEP: inner_grader
    eval_response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=RUBRIC,
        messages=grader_messages,
    )
    rec.inner_api_response(eval_response)
    # A reply that hit the token limit is unfinished. Say so plainly, rather
    # than letting json.loads report a confusing "invalid JSON".
    rec.grader_checked(eval_response.stop_reason)
    # STEP: grader_cut_off
    if eval_response.stop_reason == "max_tokens":
        raise RuntimeError(f"The grader's reply was cut off (hit the "
                           f"max_tokens limit of {MAX_TOKENS}).")
    raw = next(b for b in eval_response.content if b.type == "text").text
    print(f"  [step 7] raw string back: {raw[:80]}...")

    # Claude sometimes wraps the JSON in ```json fences; json.loads can't
    # read those, so strip them first.
    grade = json.loads(strip_json_fences(raw))
    # Valid JSON isn't enough: check it's a real rating before passing it on.
    # A problem goes back to Claude as a tool error, like any other (#8).
    problem = grade_problem(grade)
    rec.grade_checked(problem)
    # STEP: invalid_grade
    if problem:
        raise ValueError(problem)
    return grade


def flag_for_review(company, role_title, missing_info):
    # No Claude call at all — a tool can be any Python.
    return {"status": "flagged", "company": company,
            "role_title": role_title, "missing_info": missing_info}


# ---------------------------------------------------------------------------
# THE AGENT LOOP
# ---------------------------------------------------------------------------
def run_agent(job_text, recorder=None):
    # `rec` writes one trace event per step (tracing.py). With no recorder,
    # NullRecorder does nothing, so the agent behaves exactly the same.
    rec = recorder or tracing.NullRecorder()
    tracing.activate(rec)   # so evaluate_job's own Claude call is recorded too
    rec.start(job_text, model=MODEL, max_tokens=MAX_TOKENS, max_passes=MAX_PASSES,
              system=SYSTEM_PROMPT, tools=tools)

    # The starting conversation: one user message.
    # STEP: conversation_setup
    messages = [{"role": "user", "content": f"Evaluate this job posting:\n\n{job_text}"}]
    rec.messages_changed("conversation_setup", [], messages)
    print(f"[step 1] messages has {len(messages)} item")

    # At most MAX_PASSES passes. A pass is one outer API call; evaluate_job's
    # own Claude call happens inside a tool, so it doesn't count.
    for api_calls in range(1, MAX_PASSES + 1):
        rec.pass_started(api_calls)        # records the pass-count check
        # Send system + tools + the WHOLE messages list.
        print(f"\n[step {2 if api_calls == 1 else 9}] outer API call, "
              f"sending {len(messages)} message(s)")
        rec.api_request(messages)
        try:
            # STEP: send_to_claude
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )
        # STEP: api_call_failed
        except anthropic.APIError as e:
            # The call itself failed (network, rate limit, overloaded, bad
            # key), so there's no reply to act on: stop and say why. Only the
            # error's type and status go in the message, never the request.
            status = getattr(e, "status_code", None)
            answer = (f"Couldn't get a reply from Claude: {type(e).__name__}"
                      f"{f' (status {status})' if status else ''}. The run stopped.")
            print(f"\n[stop] API call failed → {answer}")
            rec.end("api_error", answer, value=type(e).__name__)
            return answer

        # Claude decides on Anthropic's servers (step claude_decides, no
        # code here). Record and print what came back.
        rec.api_response(response)
        print(f"[step 4/10] stop_reason = {response.stop_reason}")
        for block in response.content:
            if block.type == "text":
                print(f"           text: {block.text[:80]}")
            elif block.type == "tool_use":
                print(f"           tool_use: id={block.id} name={block.name}")

        # Read why Claude stopped. end_turn: Claude chose to stop, so exit the
        # loop. (On that last pass this check is also step claude_done.)
        rec.reply_checked(response.stop_reason)
        # STEP: check_reply
        if response.stop_reason == "end_turn":
            print(f"\n[step 11] end_turn → done. "
                  f"Outer calls: {api_calls}, plus any inner tool calls.")
            # STEP: answer_returned
            answer = next((b.text for b in response.content if b.type == "text"), None)
            # Claude said it's done but wrote no text (e.g. only a thinking
            # block). Say so, rather than crash at the very last step.
            # STEP: no_final_answer
            if answer is None:
                answer = "Claude finished without writing a final answer."
                rec.end("no_text", answer)
                return answer
            rec.end("end_turn", answer)
            return answer

        # Claude ran out of room mid-reply. Anything in it (even a tool
        # request) may be incomplete, so stop rather than act on it.
        # STEP: reply_cut_off
        if response.stop_reason == "max_tokens":
            print(f"\n[stop] max_tokens → reply cut off at {MAX_TOKENS} tokens.")
            answer = (f"Claude's reply was cut off (hit the max_tokens limit "
                      f"of {MAX_TOKENS}).")
            rec.end("max_tokens", answer)
            return answer

        # Save Claude's FULL turn, tool_use block included.
        before = list(messages)
        # STEP: save_turn
        messages.append({"role": "assistant", "content": response.content})
        rec.messages_changed("save_turn", before, messages)
        print(f"[step 5] appended assistant turn → messages has {len(messages)}")

        # Dispatch: match the name string to a real function.
        # Claude can ask for several tools in one turn. Every tool_use block
        # needs its own tool_result, or the next API call is rejected, so
        # run them all (one after another) and collect the results.
        tool_results = []
        # STEP: run_tools
        for tool_block in (b for b in response.content if b.type == "tool_use"):
            print(f"[step 6] dispatching {tool_block.name}(**{tool_block.input})")
            rec.tool_checked(tool_block)       # does it exist? then the call

            # If the tool raises, don't crash: send the error back to Claude
            # as the tool_result, marked is_error, and let Claude decide.
            try:
                if tool_block.name == "evaluate_job":
                    result = evaluate_job(**tool_block.input)
                elif tool_block.name == "flag_for_review":
                    result = flag_for_review(**tool_block.input)
                else:
                    # STEP: unknown_tool
                    raise ValueError(
                        f"Unknown tool {tool_block.name!r}. Available tools: "
                        f"{', '.join(t['name'] for t in tools)}.")
                outcome = {"content": json.dumps(result)}
            # STEP: tool_failed
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                print(f"[step 6] {tool_block.name} raised → {error}")
                outcome = {"content": error, "is_error": True}
            rec.tool_finished(tool_block, outcome)   # did it succeed? then the result

            # Each result carries the SAME id Claude gave its request.
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                **outcome,
            })

        # Return ALL the results in ONE user-role message.
        before = list(messages)
        # STEP: results_back
        messages.append({"role": "user", "content": tool_results})
        rec.messages_changed("results_back", before, messages)
        ids = ", ".join(
            r["tool_use_id"] + (" is_error" if r.get("is_error") else "")
            for r in tool_results)
        print(f"[step 8] appended {len(tool_results)} tool_result(s) "
              f"(ids: {ids}) → messages has {len(messages)}")
        # ...back to the top of the loop for the next pass.

    # Used up every pass without end_turn: stop instead of looping forever.
    print(f"\n[cap] {MAX_PASSES} outer calls without end_turn → stopping.")
    # STEP: pass_cap
    answer = f"Stopped after {MAX_PASSES} passes without finishing."
    rec.end("pass_cap", answer)
    return answer


# ---------------------------------------------------------------------------
# TEST CASE
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    job = """Northwind Labs — AI Agent Architect
Location: Remote (US)
Compensation: $200,000–$240,000 base
Design and ship agentic workflows on Northwind's platform. Partner with
enterprise customers to architect multi-agent systems using LLM tool use,
evaluation frameworks, and integrations with customer data."""

    # Record this run as a trace (scenario names come with #17).
    recorder = tracing.Recorder(scenario="clean")
    # STEP: agent_starts
    final = run_agent(job, recorder=recorder)
    print("\nFINAL ANSWER:\n" + final)
    print(f"\nTrace written to {recorder.write()}")