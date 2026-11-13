"""Tests for the loop cap in run_agent (issue #15).

The loop stops after MAX_PASSES outer API calls even if Claude never says
end_turn. evaluate_job's own Claude call doesn't count toward the cap.

No API calls: fake client. Run from job-evaluator/:
    python -m unittest discover -s tests -v
"""

from types import SimpleNamespace

# Shared fakes and the safe `agent` import (no .env, placeholder key).
try:
    from test_tool_errors import FakeClientTestCase, text_response, agent
except ImportError:  # when run as tests.test_loop_cap
    from tests.test_tool_errors import FakeClientTestCase, text_response, agent


CAP_MESSAGE = "Stopped after 10 passes without finishing."
FLAG_INPUT = {"company": "Acme", "role_title": "Architect", "missing_info": "comp"}
EVAL_INPUT = {"company": "Acme", "role_title": "Architect", "job_description": "desc"}

# If the cap is missing, the loop would never end. Fail loudly instead of
# hanging the test run.
RUNAWAY_LIMIT = 50


def tool_use_reply(n, name, tool_input):
    block = SimpleNamespace(type="tool_use", id=f"toolu_{n}", name=name, input=tool_input)
    return SimpleNamespace(content=[block], stop_reason="tool_use")


class NeverFinishingClaude:
    """Stands in for client.messages. Outer calls (the ones sent with tools)
    always ask for a tool again, so Claude never says end_turn. Inner calls
    from evaluate_job (no tools) get a valid rating back."""

    def __init__(self, tool_name, tool_input):
        self.tool_name, self.tool_input = tool_name, tool_input
        self.outer_calls = 0
        self.inner_calls = 0

    def create(self, **kwargs):
        if self.outer_calls + self.inner_calls >= RUNAWAY_LIMIT:
            raise AssertionError(f"no cap: {RUNAWAY_LIMIT} API calls and still going")
        if "tools" in kwargs:
            self.outer_calls += 1
            return tool_use_reply(self.outer_calls, self.tool_name, self.tool_input)
        self.inner_calls += 1
        return text_response('{"answer": "yes", "reasons": ["x"]}')


class LoopCapTest(FakeClientTestCase):

    def run_never_finishing(self, tool_name, tool_input):
        fake = NeverFinishingClaude(tool_name, tool_input)
        agent.client = SimpleNamespace(messages=fake)
        return agent.run_agent("Acme — Architect"), fake

    def test_cap_constant_is_10(self):
        self.assertEqual(agent.MAX_PASSES, 10)

    def test_never_ending_run_stops_after_exactly_10_outer_calls(self):
        final, fake = self.run_never_finishing("flag_for_review", FLAG_INPUT)

        # Returned (didn't crash or hang) with the exact message.
        self.assertEqual(final, CAP_MESSAGE)
        self.assertEqual(fake.outer_calls, 10)

    def test_inner_evaluate_job_calls_do_not_count_toward_cap(self):
        # Every pass runs evaluate_job, which makes its own Claude call.
        # If inner calls counted, the run would stop after 5 outer calls.
        final, fake = self.run_never_finishing("evaluate_job", EVAL_INPUT)

        self.assertEqual(final, CAP_MESSAGE)
        self.assertEqual(fake.outer_calls, 10)
        self.assertEqual(fake.inner_calls, 10)

    def test_normal_run_ending_on_pass_2_is_unaffected(self):
        final, fake = self.run_with([
            tool_use_reply(1, "flag_for_review", FLAG_INPUT),
            text_response("Flagged for review."),
        ])

        self.assertEqual(final, "Flagged for review.")
        self.assertEqual(len(fake.sent), 2)

    def test_end_turn_on_the_last_allowed_pass_returns_claudes_answer(self):
        # Boundary check: finishing on pass 10 is a real finish, not the cap.
        replies = [tool_use_reply(n, "flag_for_review", FLAG_INPUT) for n in range(1, 10)]
        replies.append(text_response("Finished on pass 10."))
        final, fake = self.run_with(replies)

        self.assertEqual(final, "Finished on pass 10.")
        self.assertEqual(len(fake.sent), 10)


if __name__ == "__main__":
    import unittest
    unittest.main()
