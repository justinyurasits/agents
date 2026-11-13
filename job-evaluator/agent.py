"""
Job Evaluator Agent: rates one job posting, or flags it for review.

Run:
    pip install -r requirements.txt
    cp .env.example .env    # then put your Anthropic API key in .env
    python agent.py                     # the built-in sample posting
    python agent.py --scenario 6        # a scenario from scenarios/scenarios.json
    python agent.py --fault tool_fails  # force one failure on purpose (faults.py)

HOW TO READ THIS FILE
---------------------
Three kinds of line are mixed together. Only the first kind decides what the
agent does; the other two are tagged so you can skip them:

    the agent itself        API calls, tool dispatch, messages.append(...)
    # (terminal only)       print(...) lines: what you see while it runs
    # (trace only)          rec.… / tracing.… lines: record the run to a
                            trace file for the page; they never change what
                            the agent does

`# STEP: <step_id>` marks the code each step in docs/STEPS.md points to
(the page looks the line up from the marker). `GUARD (E<n> <step_id>)`
labels a check that stops a crash, a hang, or bad data; E1–E9 are the
"When something goes wrong" steps in STEPS.md.

THE WHOLE THING IN BRIEF
------------------------
1. `tools` describes two tools to Claude: evaluate_job and flag_for_review.
2. run_agent(job) starts a conversation (`messages`) with the posting.
3. Each pass of the loop:
     send messages + tools to Claude      → Claude replies
     reply says "done"?                   → return its text
     reply asks for tools?                → run each one, add the results
                                            to messages, go round again
   Inside evaluate_job, code checks the hard rules first (remote, the $180K
   floor); only a posting that passes them goes to the grader, a second
   Claude that answers one yes/no question.
4. Guards stop the run cleanly if something goes wrong (E1–E9).
5. Faults (faults.py) make one thing go wrong on purpose, so the guards can
   be shown working. They're off unless you ask for one, and every change a
   fault makes is labelled `injected` in the trace.
"""

import argparse
import json
import re
import anthropic
from dotenv import load_dotenv

import faults
import tracing

# Read the API key from .env. override=True: .env wins over any stale key
# already set in the terminal (that caused a 401 once; see BUILD_LOG).
load_dotenv(override=True)
client = anthropic.Anthropic()          # reads ANTHROPIC_API_KEY from env
MODEL = "claude-sonnet-5-5"
SYSTEM_PROMPT = "You help Justin triage job postings. Use the tools provided."
MAX_PASSES = 10    # outer API calls per run; stops a runaway loop (and its cost)
MAX_TOKENS = 2000  # longest reply Claude may write, for both API calls

# ---------------------------------------------------------------------------
# TOOL DEFINITIONS — the only thing Claude ever sees about your tools.
# Plain dicts. Sent with every outer API call.
#
# Claude reads each `description` to decide WHICH tool to ask for, and uses
# `input_schema` to fill in the arguments. It never sees the Python
# functions below; it can only send back a request naming a tool.
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

# HARD SCREENS: Justin's fixed rules, checked in code before any rating call
# (#26). Rules belong in code, where they can't be misapplied; judgment
# belongs in the prompt (CLAUDE.md).
MIN_BASE = 180_000     # lowest base salary in the range must be at least this
REQUIRE_REMOTE = True  # a role Claude marked remote: false is screened out


# Amounts in a compensation string: "140,000", "185K", "1.2M". The groups
# are the number and an optional K or M.
_AMOUNT = re.compile(r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*([km])?(?![a-z])", re.IGNORECASE)
# "-", "–", "—" or "to" between the two ends of a range, as in "180–220K".
_RANGE_DASH = re.compile(r"\s*(?:-|–|—|to)\s*\$?\s*", re.IGNORECASE)
# Pay that isn't a yearly salary ("$90/hr", "$15,000 per month"); not compared.
_NOT_YEARLY = re.compile(r"/\s*(?:hr|hour|day|week|wk|month|mo)\b|\bper\s+(?:hour|day|week|month)"
                         r"|\b(?:hourly|daily|weekly|monthly)\b", re.IGNORECASE)
_SCALE = {"": 1, "k": 1_000, "m": 1_000_000}


def lowest_base(compensation):
    """The lowest yearly base salary in Claude's compensation text, in
    dollars, or None if no salary can be read from it. Pure function.

        "$140,000–$165,000 base" → 140000      "$185K–$215K" → 185000
        "180-220k"               → 180000      "competitive" → None
        "$90/hr"                 → None (not a yearly salary)
    """
    if not isinstance(compensation, str) or _NOT_YEARLY.search(compensation):
        return None
    # finditer gives each match with its position, so we can see the text
    # between two amounts.
    matches = list(_AMOUNT.finditer(compensation))
    amounts = []
    for i, m in enumerate(matches):
        number, suffix = float(m.group(1).replace(",", "")), (m.group(2) or "").lower()
        # In "180-220K" the first number borrows the second one's K.
        if not suffix and number < 1_000 and i + 1 < len(matches):
            after = matches[i + 1]
            between = compensation[m.end():after.start()]
            if after.group(2) and _RANGE_DASH.fullmatch(between):
                suffix = after.group(2).lower()
        value = number * _SCALE[suffix]
        if value >= 10_000:          # skip small numbers: "15% bonus", "2 weeks"
            amounts.append(int(value))
    return min(amounts) if amounts else None


def hard_screens(remote, compensation):
    """Check the hard rules in code. Pure function, no API call.

    Returns one dict per screen, e.g. for remote=False, compensation="$200K":
        [{"name": "remote", "checked": "remote is not false", "value": False,
          "caught": True, "skipped": False, "note": "not remote"},
         {"name": "comp_floor", "checked": "lowest base >= MIN_BASE (180000)",
          "value": 200000, "caught": False, "skipped": False, "note": "..."}]
    A screen that can't be checked (no remote status, pay that isn't a number)
    is skipped, never failed: the posting goes on to the rating call.
    """
    if not REQUIRE_REMOTE:
        remote_screen = {"caught": False, "skipped": True, "note": "remote not required"}
    elif remote is False:
        remote_screen = {"caught": True, "skipped": False, "note": "not remote"}
    elif remote is True:
        remote_screen = {"caught": False, "skipped": False, "note": "remote"}
    else:
        remote_screen = {"caught": False, "skipped": True,
                         "note": f"remote status {remote!r} isn't true or false; "
                                 "remote screen skipped"}

    base = lowest_base(compensation)
    floor = f"${MIN_BASE // 1000}K floor"
    if base is None:
        comp_screen = {"caught": False, "skipped": True,
                       "note": f"couldn't read a yearly base salary from "
                               f"{compensation!r}; comp screen skipped"}
    elif base < MIN_BASE:
        comp_screen = {"caught": True, "skipped": False, "note": f"base below {floor}"}
    else:
        comp_screen = {"caught": False, "skipped": False,
                       "note": f"base ${base:,} meets the {floor}"}

    # {**a, **b} builds one dict from both: the fixed fields, then the outcome.
    return [{"name": "remote", "checked": "remote is not false", "value": remote,
             **remote_screen},
            # A skipped comp screen records the text it couldn't read instead.
            {"name": "comp_floor", "checked": f"lowest base >= MIN_BASE ({MIN_BASE})",
             "value": compensation if base is None else base, **comp_screen}]


# System prompt for the GRADER: a second Claude, called from inside
# evaluate_job. The agent (Claude #1) never sees this text. It asks only the
# question that needs judgment; the hard rules are checked in code (above).
RUBRIC = """You judge one thing about a job posting for Justin:
does this role build hands-on AI experience?
Answer only that question.
Respond with JSON only: {"answer": "yes" or "no", "reasons": ["...", "..."]}"""

# Code, not the grader, turns the answer into the rating. (A posting that
# failed a hard screen never reaches the grader: it's IGNORE.)
RATING_FOR_ANSWER = {"yes": "STRONG", "no": "WORTH REVIEWING"}


def grade_problem(grade):
    """What's wrong with the grader's parsed JSON, or None if it's valid.

    Valid means: an object with `answer` ("yes" or "no", in any case) and
    `reasons` (a list of strings). Other keys are allowed. Pure function, no
    API call.

    A valid grade looks like:
        {"answer": "yes", "reasons": ["Builds LLM agents hands-on"]}
    """
    # isinstance(x, dict) asks "is x a dict?" (a JSON object becomes a dict).
    if not isinstance(grade, dict):
        return f"The grader's reply is a JSON {type(grade).__name__}, not an object."
    if "answer" not in grade:
        return "The grader's reply has no 'answer'."
    answer = grade["answer"]
    # .strip().lower() makes the check forgiving: " Yes" counts as "yes".
    if not isinstance(answer, str) or answer.strip().lower() not in RATING_FOR_ANSWER:
        return f"The grader's answer {answer!r} isn't yes or no."
    if "reasons" not in grade:
        return "The grader's reply has no 'reasons'."
    reasons = grade["reasons"]
    # all(...) is True only if every item passes the check.
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
    """Tool: check the hard rules in code, then ask a second Claude (the
    grader) the one question that needs judgment.

    The arguments are exactly what Claude #1 filled in from the tool's
    input_schema. Optional ones it left out arrive as "Unknown".
    Returns {"rating": ..., "reasons": [...]}, or raises an error, which
    run_agent sends back to Claude #1 as a failed tool result (E1).
    """
    rec = tracing.active()            # the run's recorder, if any (trace only)

    # Hard screens first, in code. A posting that fails one is IGNORE, and
    # the rating call is never made.
    screens = hard_screens(remote, compensation)
    for screen in screens:
        print(f"  [hard_screen] {screen['name']}: {screen['note']}")  # (terminal only)
        rec.screen_checked(screen)  # (trace only)
    failed = [s["note"] for s in screens if s["caught"]]
    # GUARD (E9 hard_screen): the posting breaks a fixed rule (not remote, or
    # base below MIN_BASE). Return IGNORE straight away; no rating call.
    # STEP: hard_screen
    if failed:
        return {"rating": "IGNORE", "reasons": failed}

    # The grader sees only the posting: remote status and pay were already
    # handled by the screens above, so they aren't passed on separately.
    job_summary = f"Company: {company}\nRole: {role_title}\n\n{job_description}"

    # A separate, one-off Claude call. No tools, no loop.
    # The outer `messages` list is not touched: the grader gets its own
    # one-message conversation, which is thrown away when this returns.
    grader_messages = [{"role": "user", "content": job_summary}]
    print("  [inner_grader] evaluate_job → the grader's own Claude call")  # (terminal only)
    rec.inner_api_request(RUBRIC, grader_messages)  # (trace only)
    # STEP: inner_grader
    eval_response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=RUBRIC,
        messages=grader_messages,
    )
    rec.inner_api_response(eval_response)  # (trace only)

    # GUARD (E5 grader_cut_off): the grader's reply hit MAX_TOKENS and stopped
    # part-way, so its JSON is unfinished. Say so plainly, rather than letting
    # json.loads report a confusing "invalid JSON".
    rec.grader_checked(eval_response.stop_reason)  # (trace only)
    # STEP: grader_cut_off
    if eval_response.stop_reason == "max_tokens":
        raise RuntimeError(f"The grader's reply was cut off (hit the "
                           f"max_tokens limit of {MAX_TOKENS}).")

    # The reply is a list of content blocks; take the first text one.
    # (Find blocks by type, never by position: a thinking block can come first.)
    raw = next(b for b in eval_response.content if b.type == "text").text
    # Fault injection (only with --fault tool_fails or runaway_loop): swap the
    # grader's real reply for broken JSON. The real reply is still in the
    # trace; the swap is recorded as injected.
    fault = faults.active()
    swapped = fault.grader_reply(raw)
    if swapped != raw:
        rec.fault_injected("inner_grader", {"grader_reply": {"real": raw, "injected": swapped}})  # (trace only)
        raw = swapped
    print(f"  [inner_grader] raw string back: {raw[:80]}...")  # (terminal only)

    # Claude sometimes wraps the JSON in ```json fences; json.loads can't
    # read those, so strip them first.
    grade = json.loads(strip_json_fences(raw))

    # GUARD (E8 invalid_grade): valid JSON isn't enough; check it's a real
    # yes/no answer before using it. A problem goes back to Claude as a tool
    # error, like any other (#8).
    problem = grade_problem(grade)
    rec.grade_checked(problem)  # (trace only)
    # STEP: invalid_grade
    if problem:
        raise ValueError(problem)
    # Code turns the answer into the rating: yes → STRONG, no → WORTH REVIEWING.
    rating = RATING_FOR_ANSWER[grade["answer"].strip().lower()]
    return {"rating": rating, "reasons": grade["reasons"]}


def flag_for_review(company, role_title, missing_info):
    """Tool: mark the posting for a human to look at. No Claude call at all:
    a tool can be any Python."""
    return {"status": "flagged", "company": company,
            "role_title": role_title, "missing_info": missing_info}


# ---------------------------------------------------------------------------
# THE AGENT LOOP
#
#   messages = [the posting]                                conversation_setup
#   repeat, at most MAX_PASSES times:
#       reply = Claude(system, tools, messages)             send_to_claude
#           call failed?          → stop                    GUARD E6
#       done (end_turn)?          → return its text          check_reply / claude_done
#           no text in it?        → stop                    GUARD E7
#       cut off (max_tokens)?     → stop                    GUARD E3
#       messages += Claude's reply                          save_turn
#       for each tool request in the reply:                 run_tools
#           unknown tool?         → error result            GUARD E2
#           evaluate_job: fails a hard rule? → IGNORE,
#                         no rating call                    GUARD E9
#           tool raised?          → error result            GUARD E1
#       messages += all the results, in one message         results_back
#   ran out of passes             → stop                    GUARD E4
#
# With a fault (faults.py) the same loop runs, but one thing is forced to go
# wrong: a limit is lowered (max_passes / max_tokens below), Claude's tool
# request is renamed, or the grader's reply is swapped for broken JSON.
#
# How `messages` grows in a normal two-pass run:
#   pass 1 sends 1 message:
#     [{"role": "user", "content": "Evaluate this job posting: ..."}]
#   pass 2 sends 3, after save_turn and results_back added one each:
#     [{"role": "user", "content": "Evaluate this job posting: ..."},
#      {"role": "assistant", "content": [<tool_use block: evaluate_job, id "toolu_01…">]},
#      {"role": "user", "content": [{"type": "tool_result",
#                                    "tool_use_id": "toolu_01…",
#                                    "content": '{"rating": "WORTH REVIEWING", ...}'}]}]
# Claude keeps no memory between calls: this list IS its memory, and the
# whole list is sent every time.
# ---------------------------------------------------------------------------
def run_agent(job_text, recorder=None, fault=None):
    # `rec` writes one trace event per step (tracing.py). With no recorder,
    # NullRecorder does nothing, so the agent behaves exactly the same.
    # (`a or b` gives `a` if it's set, otherwise `b`.)
    rec = recorder or tracing.NullRecorder()  # (trace only)
    tracing.activate(rec)   # so evaluate_job's own Claude call is recorded too (trace only)

    # Fault injection: a Fault() with no name changes nothing. With one, it
    # may lower a limit for this run. activate() lets evaluate_job see it.
    fault = fault or faults.Fault()
    faults.activate(fault)
    max_passes = fault.max_passes(MAX_PASSES)
    max_tokens = fault.max_tokens(MAX_TOKENS)

    rec.start(job_text, model=MODEL, max_tokens=max_tokens, max_passes=max_passes,
              system=SYSTEM_PROMPT, tools=tools, fault=fault.name)  # (trace only)
    rec.limits_injected(MAX_PASSES, max_passes, MAX_TOKENS, max_tokens)  # (trace only)

    # The starting conversation: one user message.
    # STEP: conversation_setup
    messages = [{"role": "user", "content": f"Evaluate this job posting:\n\n{job_text}"}]
    rec.messages_changed("conversation_setup", [], messages)  # (trace only)
    print(f"[conversation_setup] messages has {len(messages)} item")  # (terminal only)

    # At most max_passes passes (MAX_PASSES, unless a fault lowered it). A
    # pass is one outer API call; evaluate_job's own Claude call happens
    # inside a tool, so it doesn't count.
    # range(1, max_passes + 1) counts 1, 2, ... 10. When it runs out, the
    # loop ends and we fall through to the cap at the bottom (E4).
    for api_calls in range(1, max_passes + 1):
        rec.pass_started(api_calls)        # records the pass-count check (trace only)
        # Send system + tools + the WHOLE messages list.
        print(f"\n[send_to_claude] pass {api_calls}: "
              f"sending {len(messages)} message(s)")  # (terminal only)
        rec.api_request(messages)  # (trace only)
        try:
            # STEP: send_to_claude
            response = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
            )
        # GUARD (E6 api_call_failed): the call itself failed (network, rate
        # limit, overloaded, bad key), so there's no reply to act on: stop and
        # say why. Only the error's type and status go in the message, never
        # the request.
        # STEP: api_call_failed
        except anthropic.APIError as e:
            # getattr(e, "status_code", None): the HTTP status if this error
            # has one (a network error doesn't), otherwise None.
            status = getattr(e, "status_code", None)
            answer = (f"Couldn't get a reply from Claude: {type(e).__name__}"
                      f"{f' (status {status})' if status else ''}. The run stopped.")
            print(f"\n[api_call_failed] {answer}")  # (terminal only)
            rec.end("api_error", answer, value=type(e).__name__)  # (trace only)
            return answer

        # Claude decides on Anthropic's servers (step claude_decides, no
        # code here). `response` is what came back:
        #   response.stop_reason  why Claude stopped: "end_turn" (done),
        #                         "tool_use" (wants tools), "max_tokens" (cut off)
        #   response.content      a list of blocks, e.g.
        #       [ThinkingBlock(thinking="..."),          (sometimes)
        #        TextBlock(text="I'll rate this."),
        #        ToolUseBlock(id="toolu_01…", name="evaluate_job",
        #                     input={"company": "Northwind Labs", ...})]
        rec.api_response(response)  # (trace only)

        print(f"[claude_decides] stop_reason = {response.stop_reason}")  # (terminal only)
        for block in response.content:
            if block.type == "text":
                print(f"           text: {block.text[:80]}")  # (terminal only)
            elif block.type == "tool_use":
                print(f"           tool_use: id={block.id} name={block.name}")  # (terminal only)

        # Read why Claude stopped. end_turn: Claude chose to stop, so exit the
        # loop. (On that last pass this check is also step claude_done.)
        rec.reply_checked(response.stop_reason)  # (trace only)
        # STEP: check_reply
        if response.stop_reason == "end_turn":
            print(f"\n[claude_done] end_turn → done. "
                  f"Outer calls: {api_calls}, plus any inner tool calls.")  # (terminal only)
            # next(<matches>, None): the first text block's text, or None if
            # the reply has no text block at all.
            # STEP: answer_returned
            answer = next((b.text for b in response.content if b.type == "text"), None)
            # GUARD (E7 no_final_answer): Claude said it's done but wrote no
            # text (e.g. only a thinking block). Say so, rather than crash at
            # the very last step.
            # STEP: no_final_answer
            if answer is None:
                answer = "Claude finished without writing a final answer."
                rec.end("no_text", answer)  # (trace only)
                return answer
            rec.end("end_turn", answer)  # (trace only)
            return answer

        # GUARD (E3 reply_cut_off): the reply hit the token limit and stopped
        # part-way. Anything in it, even a tool request, may be incomplete,
        # so stop rather than act on it.
        # STEP: reply_cut_off
        if response.stop_reason == "max_tokens":
            print(f"\n[reply_cut_off] reply cut off at {max_tokens} tokens.")  # (terminal only)
            answer = (f"Claude's reply was cut off (hit the max_tokens limit "
                      f"of {max_tokens}).")
            rec.end("max_tokens", answer)  # (trace only)
            return answer

        # Save Claude's FULL turn, tool_use block included, so the next call
        # shows Claude what it already asked for. (The API needs the request
        # in the conversation before the result that answers it.)
        # Fault injection (only with --fault unknown_tool, once): rename
        # Claude's first tool request to a tool that doesn't exist, before it's
        # saved, so the conversation stays consistent. The real response is
        # already in the trace; the rename is recorded as injected.
        renamed = fault.tool_request(response)
        if renamed:
            rec.fault_injected("save_turn", {"tool_name": {"real": renamed[0], "injected": renamed[1]}})  # (trace only)

        before = list(messages)  # a copy, for the trace's before/after (trace only)
        # STEP: save_turn
        messages.append({"role": "assistant", "content": response.content})
        rec.messages_changed("save_turn", before, messages)  # (trace only)
        print(f"[save_turn] appended assistant turn → messages has {len(messages)}")  # (terminal only)

        # Dispatch: match the name string to a real function.
        # Claude can ask for several tools in one turn. Every tool_use block
        # needs its own tool_result, or the next API call is rejected, so
        # run them all (one after another) and collect the results.
        tool_results = []
        # (b for b in ... if ...) yields just the tool_use blocks, in order.
        # STEP: run_tools
        for tool_block in (b for b in response.content if b.type == "tool_use"):
            print(f"[run_tools] dispatching {tool_block.name}(**{tool_block.input})")  # (terminal only)
            rec.tool_checked(tool_block)       # does it exist? then the call (trace only)

            # If the tool raises, don't crash: send the error back to Claude
            # as the tool_result, marked is_error, and let Claude decide.
            try:
                # **tool_block.input unpacks Claude's arguments into keyword
                # arguments: {"company": "X", ...} → evaluate_job(company="X", ...)
                if tool_block.name == "evaluate_job":
                    result = evaluate_job(**tool_block.input)
                elif tool_block.name == "flag_for_review":
                    result = flag_for_review(**tool_block.input)
                else:
                    # GUARD (E2 unknown_tool): Claude asked for a tool that
                    # doesn't exist. Raise, so the except below sends Claude
                    # an error naming the real tools.
                    # STEP: unknown_tool
                    raise ValueError(
                        f"Unknown tool {tool_block.name!r}. Available tools: "
                        f"{', '.join(t['name'] for t in tools)}.")
                outcome = {"content": json.dumps(result)}
            # GUARD (E1 tool_failed): any error from a tool (bad JSON, bad
            # arguments, the grader's own call failing) becomes an is_error
            # result for Claude, instead of crashing the run.
            # STEP: tool_failed
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                print(f"[tool_failed] {tool_block.name} raised → {error}")  # (terminal only)
                outcome = {"content": error, "is_error": True}
            rec.tool_finished(tool_block, outcome)   # did it succeed? then the result (trace only)

            # Each result carries the SAME id Claude gave its request.
            # **outcome copies outcome's keys into this dict, giving e.g.
            #   {"type": "tool_result", "tool_use_id": "toolu_01…",
            #    "content": "JSONDecodeError: ...", "is_error": True}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                **outcome,
            })

        # Return ALL the results in ONE user-role message.
        before = list(messages)  # a copy, for the trace's before/after (trace only)
        # STEP: results_back
        messages.append({"role": "user", "content": tool_results})
        rec.messages_changed("results_back", before, messages)  # (trace only)
        # (terminal only) `ids` just builds the text for the print below.
        ids = ", ".join(
            r["tool_use_id"] + (" is_error" if r.get("is_error") else "")
            for r in tool_results)
        print(f"[results_back] appended {len(tool_results)} tool_result(s) "
              f"(ids: {ids}) → messages has {len(messages)}")  # (terminal only)
        # ...back to the top of the loop for the next pass.

    # GUARD (E4 pass_cap): used up every pass without end_turn (e.g. Claude
    # keeps retrying a tool that keeps failing). Stop instead of looping,
    # and spending, forever.
    print(f"\n[pass_cap] {max_passes} outer calls without end_turn → stopping.")  # (terminal only)
    # STEP: pass_cap
    answer = f"Stopped after {max_passes} passes without finishing."
    rec.end("pass_cap", answer)  # (trace only)
    return answer


# ---------------------------------------------------------------------------
# RUNNING IT
# `if __name__ == "__main__":` runs only when you start this file directly
# (python agent.py), not when tests import it.
# ---------------------------------------------------------------------------
SAMPLE_JOB = """Northwind Labs — AI Agent Architect
Location: Remote (US)
Compensation: $200,000–$240,000 base
Design and ship agentic workflows on Northwind's platform. Partner with
enterprise customers to architect multi-agent systems using LLM tool use,
evaluation frameworks, and integrations with customer data."""

SCENARIOS_FILE = "scenarios/scenarios.json"


def choose_run(argv=None, scenarios_file=SCENARIOS_FILE):
    """Work out what to run from the command line: (job text, scenario name,
    fault name or None). No API call, so tests can check it directly.

        python agent.py                      → the sample posting, no fault
        python agent.py --scenario 6         → scenario 6's posting and fault
        python agent.py --fault tool_fails   → the sample posting with that fault
    """
    # argparse reads options like --fault from the command line.
    parser = argparse.ArgumentParser(description="Run the job evaluator agent.")
    parser.add_argument("--scenario", type=int,
                        help="run this scenario's posting (and its fault) from " + scenarios_file)
    parser.add_argument("--fault", choices=faults.FAULTS,
                        help="force one failure on purpose; overrides the scenario's fault")
    args = parser.parse_args(argv)

    job, name, fault = SAMPLE_JOB, "clean", None
    if args.scenario is not None:
        with open(scenarios_file, encoding="utf-8") as f:
            scenario = next((s for s in json.load(f) if s["id"] == args.scenario), None)
        if scenario is None:
            parser.error(f"no scenario {args.scenario} in {scenarios_file}")
        job, name, fault = scenario["posting"], f"scenario-{args.scenario}", scenario["fault"]
    if args.fault:
        fault = args.fault
        if args.scenario is None:
            name = args.fault
    return job, name, fault


if __name__ == "__main__":
    job, name, fault_name = choose_run()
    if fault_name:
        print(f"Fault: injecting {fault_name!r} on purpose (labelled injected in the trace)")  # (terminal only)

    # Record this run as a trace.
    recorder = tracing.Recorder(scenario=name)  # (trace only)
    # STEP: agent_starts
    final = run_agent(job, recorder=recorder, fault=faults.Fault(fault_name))
    print("\nFINAL ANSWER:\n" + final)  # (terminal only)
    path = recorder.write()   # save the trace file to traces/ (trace only)
    print(f"\nTrace written to {path}")  # (terminal only)
