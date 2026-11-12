"""Tests for tool errors in run_agent (issue #8).

A tool that raises must not crash the agent. The error goes back to Claude
as a tool_result with is_error: true, and the run still finishes.

No API calls: agent.client is swapped for a fake that returns canned
responses in order. Run from job-evaluator/:
    python -m unittest discover -s tests -v
"""

import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

# Same safe import as test_fences.py: skip .env, use a placeholder key.
with mock.patch("dotenv.load_dotenv"), \
        mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-placeholder"}):
    import agent


TOOL_ID = "toolu_test_1"
FINAL_TEXT = "The rating tool failed, so I couldn't rate this job."


class FakeMessages:
    """Stands in for client.messages. Returns canned responses in order and
    records the messages list sent on each call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []

    def create(self, **kwargs):
        # run_agent keeps appending to the same list, so copy it now.
        self.sent.append(list(kwargs["messages"]))
        return self.responses.pop(0)


def outer_tool_use(name, tool_input):
    """Outer Claude asks for one tool."""
    block = SimpleNamespace(type="tool_use", id=TOOL_ID, name=name, input=tool_input)
    return SimpleNamespace(content=[block], stop_reason="tool_use")


def text_response(text, stop_reason="end_turn"):
    """A text reply with a thinking block first, like the real API can send."""
    thinking = SimpleNamespace(type="thinking", thinking="...")
    answer = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[thinking, answer], stop_reason=stop_reason)


EVAL_INPUT = {"company": "Acme", "role_title": "Architect", "job_description": "desc"}


class ToolErrorTest(unittest.TestCase):

    def setUp(self):
        self.real_client = agent.client
        print_patch = mock.patch("builtins.print")  # keep test output clean
        print_patch.start()
        self.addCleanup(print_patch.stop)

    def tearDown(self):
        agent.client = self.real_client

    def run_with(self, responses):
        """Run the agent with a fake client. Returns (final text, fake)."""
        fake = FakeMessages(responses)
        agent.client = SimpleNamespace(messages=fake)
        final = agent.run_agent("Acme — Architect")
        return final, fake

    def last_tool_result(self, fake):
        """The tool_result block sent on the final outer call."""
        last_message = fake.sent[-1][-1]
        self.assertEqual(last_message["role"], "user")
        block = last_message["content"][0]
        self.assertEqual(block["type"], "tool_result")
        self.assertEqual(block["tool_use_id"], TOOL_ID)
        return block

    def test_tool_that_raises_does_not_crash_and_run_finishes(self):
        # A fake tool: evaluate_job replaced by one that raises.
        with mock.patch.object(agent, "evaluate_job",
                               side_effect=RuntimeError("inner call timed out")):
            final, fake = self.run_with([
                outer_tool_use("evaluate_job", EVAL_INPUT),
                text_response(FINAL_TEXT),          # end_turn after the error
            ])

        # Run finished with end_turn and a final text answer.
        self.assertEqual(final, FINAL_TEXT)
        self.assertEqual(len(fake.sent), 2)        # two outer calls, no crash

        # The error went back to Claude, marked as an error.
        block = self.last_tool_result(fake)
        self.assertIs(block["is_error"], True)
        self.assertIn("inner call timed out", block["content"])
        self.assertIn("RuntimeError", block["content"])

    def test_invalid_json_from_inner_call_becomes_tool_error(self):
        # The real evaluate_job, with inner replies that aren't valid JSON.
        cases = {
            "no_fence":   "Sure! Here's my rating: STRONG",
            "json_fence": '```json\n{rating: "STRONG"}\n```',
            "bare_fence": "```{\"rating\": \"STRONG\",}\n```",
        }
        for name, inner_reply in cases.items():
            with self.subTest(name):
                # The exact message json.loads gives for this reply.
                try:
                    json.loads(agent.strip_json_fences(inner_reply))
                    self.fail("test reply was supposed to be invalid JSON")
                except json.JSONDecodeError as e:
                    parse_error = str(e)

                final, fake = self.run_with([
                    outer_tool_use("evaluate_job", EVAL_INPUT),  # outer #1
                    text_response(inner_reply),                  # inner call
                    text_response(FINAL_TEXT),                   # outer #2
                ])

                self.assertEqual(final, FINAL_TEXT)
                block = self.last_tool_result(fake)
                self.assertIs(block["is_error"], True)
                self.assertIn("JSONDecodeError", block["content"])
                self.assertIn(parse_error, block["content"])

    def test_successful_tool_result_is_unchanged(self):
        # Regression check: a tool that works sends JSON, with no is_error.
        flag_input = {"company": "Acme", "role_title": "Architect",
                      "missing_info": "compensation"}
        final, fake = self.run_with([
            outer_tool_use("flag_for_review", flag_input),
            text_response("Flagged for review."),
        ])

        self.assertEqual(final, "Flagged for review.")
        block = self.last_tool_result(fake)
        self.assertNotIn("is_error", block)
        self.assertEqual(json.loads(block["content"])["status"], "flagged")


if __name__ == "__main__":
    unittest.main()
