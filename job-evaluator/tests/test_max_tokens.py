"""Tests for replies cut off by the max_tokens limit (issue #18).

A reply with stop_reason "max_tokens" is unfinished. The main loop must stop
without dispatching anything, and evaluate_job must report "cut off", not
"invalid JSON". Both API calls use the MAX_TOKENS constant.

No API calls: fake client. Run from job-evaluator/:
    python -m unittest discover -s tests -v
"""

import json
from types import SimpleNamespace
from unittest import mock

# Shared fakes and the safe `agent` import (no .env, placeholder key).
try:
    from test_tool_errors import FakeClientTestCase, text_response, agent
except ImportError:  # when run as tests.test_max_tokens
    from tests.test_tool_errors import FakeClientTestCase, text_response, agent


CUT_OFF_MESSAGE = "Claude's reply was cut off (hit the max_tokens limit of 2000)."
EVAL_INPUT = {"company": "Acme", "role_title": "Architect", "job_description": "desc"}
FLAG_INPUT = {"company": "Acme", "role_title": "Architect", "missing_info": "comp"}


def tool_use_reply(tool_id, name, tool_input, stop_reason="tool_use", preamble=None):
    blocks = []
    if preamble:
        blocks.append(SimpleNamespace(type="text", text=preamble))
    blocks.append(SimpleNamespace(type="tool_use", id=tool_id, name=name, input=tool_input))
    return SimpleNamespace(content=blocks, stop_reason=stop_reason)


class RecordingClaude:
    """Fake client.messages: returns canned replies in order and records the
    keyword arguments of every call (outer and inner)."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.replies.pop(0)

    def outer(self):
        return [c for c in self.calls if "tools" in c]

    def inner(self):
        return [c for c in self.calls if "tools" not in c]


class MaxTokensTest(FakeClientTestCase):

    def run_recording(self, replies):
        fake = RecordingClaude(replies)
        agent.client = SimpleNamespace(messages=fake)
        return agent.run_agent("Acme — Architect"), fake

    def last_tool_result(self, fake):
        block = fake.outer()[-1]["messages"][-1]["content"][0]
        self.assertEqual(block["type"], "tool_result")
        return block

    # --- main loop -------------------------------------------------------

    def test_cut_off_main_loop_reply_stops_without_dispatching(self):
        # The cut-off reply even contains a tool request. It must be ignored:
        # with the reply unfinished, its input may be incomplete.
        flag = mock.Mock(return_value={"status": "flagged"})
        with mock.patch.object(agent, "flag_for_review", flag):
            final, fake = self.run_recording([
                tool_use_reply("toolu_1", "flag_for_review", FLAG_INPUT,
                               stop_reason="max_tokens", preamble="Let me flag"),
                # Only reached if the loop wrongly carries on (old behavior).
                text_response("Done."),
            ])

        self.assertEqual(final, CUT_OFF_MESSAGE)
        flag.assert_not_called()
        self.assertEqual(len(fake.outer()), 1)   # stopped; no second call

    def test_cut_off_main_loop_reply_with_only_text_also_stops(self):
        final, fake = self.run_recording([
            text_response("Here is my assessment of the posting, which",
                          stop_reason="max_tokens"),
            text_response("Done."),
        ])

        self.assertEqual(final, CUT_OFF_MESSAGE)
        self.assertEqual(len(fake.outer()), 1)

    # --- evaluate_job ----------------------------------------------------

    def test_cut_off_grader_reply_is_reported_as_cut_off_not_invalid_json(self):
        final, fake = self.run_recording([
            tool_use_reply("toolu_1", "evaluate_job", EVAL_INPUT),           # outer 1
            text_response('{"answer": "yes", "reasons": ["Builds LLM ag',     # inner
                          stop_reason="max_tokens"),
            text_response("The grader was cut off."),                         # outer 2
        ])

        self.assertEqual(final, "The grader was cut off.")
        block = self.last_tool_result(fake)
        self.assertEqual(block["tool_use_id"], "toolu_1")
        self.assertIs(block.get("is_error"), True,
                      f"not an error; sent: {block['content']!r}")
        self.assertIn("cut off", block["content"])
        self.assertIn("max_tokens limit of 2000", block["content"])
        self.assertNotIn("JSONDecodeError", block["content"])

    # --- normal run, and the constant -------------------------------------

    def test_normal_run_is_unaffected(self):
        final, fake = self.run_recording([
            tool_use_reply("toolu_1", "evaluate_job", EVAL_INPUT),
            text_response('{"answer": "yes", "reasons": ["x"]}'),   # end_turn
            text_response("Rated STRONG."),
        ])

        self.assertEqual(final, "Rated STRONG.")
        block = self.last_tool_result(fake)
        self.assertNotIn("is_error", block)
        self.assertEqual(json.loads(block["content"])["rating"], "STRONG")

    def test_both_api_calls_use_the_max_tokens_constant(self):
        self.assertEqual(agent.MAX_TOKENS, 2000)
        # Change the constant: both calls must follow it, so neither one
        # still has 2000 written in by hand.
        with mock.patch.object(agent, "MAX_TOKENS", 123):
            _, fake = self.run_recording([
                tool_use_reply("toolu_1", "evaluate_job", EVAL_INPUT),
                text_response('{"answer": "yes", "reasons": ["x"]}'),
                text_response("Rated STRONG."),
            ])

        self.assertEqual([c["max_tokens"] for c in fake.outer()], [123, 123])
        self.assertEqual([c["max_tokens"] for c in fake.inner()], [123])


if __name__ == "__main__":
    import unittest
    unittest.main()
