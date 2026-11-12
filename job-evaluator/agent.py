"""
Job Evaluator Agent — end-to-end, one pass.
Step numbers in comments match the step-by-step diagram (1–11).

Run:
    pip install anthropic
    export ANTHROPIC_API_KEY=...
    python job_agent.py
"""

import json
import re
import anthropic
from dotenv import load_dotenv

load_dotenv(override=True)
client = anthropic.Anthropic()          # reads ANTHROPIC_API_KEY from env
MODEL = "claude-sonnet-5-5"
MAX_PASSES = 10    # outer API calls per run; stops a runaway loop (and its cost)

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

    # STEP 7 — a separate, one-off Claude call. No tools, no loop.
    # The outer `messages` list is not touched.
    print("  [step 7] evaluate_job → inner Claude call (API call #2)")
    eval_response = client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=RUBRIC,
        messages=[{"role": "user", "content": job_summary}],
    )
    raw = next(b for b in eval_response.content if b.type == "text").text
    print(f"  [step 7] raw string back: {raw[:80]}...")

    # Claude sometimes wraps the JSON in ```json fences; json.loads can't
    # read those, so strip them first.
    return json.loads(strip_json_fences(raw))


def flag_for_review(company, role_title, missing_info):
    # No Claude call at all — a tool can be any Python.
    return {"status": "flagged", "company": company,
            "role_title": role_title, "missing_info": missing_info}


# ---------------------------------------------------------------------------
# THE AGENT LOOP
# ---------------------------------------------------------------------------
def run_agent(job_text):
    # STEP 1 — the starting conversation: one user message.
    messages = [{"role": "user", "content": f"Evaluate this job posting:\n\n{job_text}"}]
    print(f"[step 1] messages has {len(messages)} item")

    # At most MAX_PASSES passes. A pass is one outer API call; evaluate_job's
    # own Claude call happens inside a tool, so it doesn't count.
    for api_calls in range(1, MAX_PASSES + 1):
        # STEP 2 / STEP 9 — send system + tools + the WHOLE messages list.
        print(f"\n[step {2 if api_calls == 1 else 9}] outer API call, "
              f"sending {len(messages)} message(s)")
        response = client.messages.create(
            model=MODEL,
            max_tokens=2000,
            system="You help Justin triage job postings. Use the tools provided.",
            tools=tools,
            messages=messages,
        )

        # STEP 3 / STEP 10 happen inside Claude. STEP 4 / STEP 10: what came back.
        print(f"[step 4/10] stop_reason = {response.stop_reason}")
        for block in response.content:
            if block.type == "text":
                print(f"           text: {block.text[:80]}")
            elif block.type == "tool_use":
                print(f"           tool_use: id={block.id} name={block.name}")

        # STEP 11 — Claude chose to stop. Exit the loop.
        if response.stop_reason == "end_turn":
            print(f"\n[step 11] end_turn → done. "
                  f"Outer calls: {api_calls}, plus any inner tool calls.")
            return next(b for b in response.content if b.type == "text").text

        # STEP 5 — save Claude's FULL turn, tool_use block included.
        messages.append({"role": "assistant", "content": response.content})
        print(f"[step 5] appended assistant turn → messages has {len(messages)}")

        # STEP 6 — dispatch: match the name string to a real function.
        # Claude can ask for several tools in one turn. Every tool_use block
        # needs its own tool_result, or the next API call is rejected, so
        # run them all (one after another) and collect the results.
        tool_results = []
        for tool_block in (b for b in response.content if b.type == "tool_use"):
            print(f"[step 6] dispatching {tool_block.name}(**{tool_block.input})")

            # If the tool raises, don't crash: send the error back to Claude
            # as the tool_result, marked is_error, and let Claude decide.
            try:
                if tool_block.name == "evaluate_job":
                    result = evaluate_job(**tool_block.input)
                elif tool_block.name == "flag_for_review":
                    result = flag_for_review(**tool_block.input)
                else:
                    known = ", ".join(t["name"] for t in tools)
                    raise ValueError(f"Unknown tool {tool_block.name!r}. "
                                     f"Available tools: {known}.")
                outcome = {"content": json.dumps(result)}
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                print(f"[step 6] {tool_block.name} raised → {error}")
                outcome = {"content": error, "is_error": True}

            # Each result carries the SAME id Claude gave its request.
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                **outcome,
            })

        # STEP 8 — return ALL the results in ONE user-role message.
        messages.append({"role": "user", "content": tool_results})
        ids = ", ".join(
            r["tool_use_id"] + (" is_error" if r.get("is_error") else "")
            for r in tool_results)
        print(f"[step 8] appended {len(tool_results)} tool_result(s) "
              f"(ids: {ids}) → messages has {len(messages)}")
        # ...back to the top of the loop (step 9).

    # Used up every pass without end_turn: stop instead of looping forever.
    print(f"\n[cap] {MAX_PASSES} outer calls without end_turn → stopping.")
    return f"Stopped after {MAX_PASSES} passes without finishing."


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

    final = run_agent(job)
    print("\nFINAL ANSWER:\n" + final)