"""Make the agent fail on purpose, in one specific way (issue #46).

Used to record the "break the agent" scenarios (6–9) on demand. A fault is
switched on only on purpose: `python agent.py --fault <name>`, or a
scenario whose `fault` field names one. With no fault, every method here
returns its input unchanged, so the agent behaves exactly as normal.

Every fault is recorded in the trace as injected (a `fault_injected` event,
and `injected: true` on what it causes), so the page never shows it as a
real failure. The real API responses are still recorded as they came back.

    fault            what it forces                          guard that catches it
    tool_fails       grader's reply → broken JSON, once      tool_succeeded (E1)
    unknown_tool     Claude's tool request renamed, once     tool_exists (E2)
    runaway_loop     grader's reply → broken JSON, always,   pass_count (E4)
                     and the pass cap lowered to 2
    reply_cut_off    main call gets a tiny token limit       max_tokens (E3)
"""

FAULTS = ("tool_fails", "unknown_tool", "runaway_loop", "reply_cut_off")

BROKEN_JSON = "Sure! Here's my rating: STRONG"   # what a broken grader reply looks like
UNKNOWN_TOOL = "rate_posting"                     # a tool name that doesn't exist
RUNAWAY_MAX_PASSES = 2   # real Claude retries a failing tool once, then stops (#46)
CUT_OFF_MAX_TOKENS = 30  # small enough that every reply is cut off (tested live, #18)


class Fault:
    """One run's fault, or none. Tracks whether a once-only fault has fired."""

    def __init__(self, name=None):
        if name is not None and name not in FAULTS:
            raise ValueError(f"Unknown fault {name!r}. Choose one of: {', '.join(FAULTS)}.")
        self.name = name
        self.fired = False

    def __bool__(self):
        return self.name is not None

    # --- limits ----------------------------------------------------------

    def max_passes(self, normal):
        return RUNAWAY_MAX_PASSES if self.name == "runaway_loop" else normal

    def max_tokens(self, normal):
        return CUT_OFF_MAX_TOKENS if self.name == "reply_cut_off" else normal

    # --- changes to what came back -----------------------------------------

    def grader_reply(self, raw):
        """The grader's reply text, or BROKEN_JSON if a fault replaces it."""
        if self.name == "runaway_loop" or (self.name == "tool_fails" and not self.fired):
            self.fired = True
            return BROKEN_JSON
        return raw

    def tool_request(self, response):
        """For unknown_tool, once: rename the first tool request in Claude's
        reply to a tool that doesn't exist. Returns (old name, new name), or
        None if nothing was changed."""
        if self.name != "unknown_tool" or self.fired:
            return None
        block = next((b for b in response.content if b.type == "tool_use"), None)
        if block is None:
            return None
        self.fired = True
        old, block.name = block.name, UNKNOWN_TOOL
        return old, UNKNOWN_TOOL


# The fault for the run in progress. run_agent sets it, so evaluate_job can
# see it without a new parameter (the same pattern as tracing.active()).
_active = Fault()


def activate(fault):
    global _active
    _active = fault


def active():
    return _active
