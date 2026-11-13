"""Tests for markdown-fence handling in evaluate_job (issue #2).

No API calls: agent.client is swapped for a fake that returns a canned reply.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

# agent.py loads .env and builds an Anthropic client when it's imported.
# Skip the .env load and use a placeholder key, so the tests never see a
# real key and pass on a machine with no .env at all.
with mock.patch("dotenv.load_dotenv"), \
        mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-placeholder"}):
    import agent


EXPECTED = {"answer": "yes", "reasons": ["builds agents"]}          # the parsed JSON
RATED = {"rating": "STRONG", "reasons": ["builds agents"]}            # what evaluate_job returns

# The three reply shapes from issue #2.
REPLIES = {
    "json_fence":  '```json\n{"answer": "yes", "reasons": ["builds agents"]}\n```',
    "bare_fence":  '```{"answer": "yes", "reasons": ["builds agents"]}\n```',
    "plain_json":  '{"answer": "yes", "reasons": ["builds agents"]}',
}


class FakeMessages:
    """Stands in for client.messages. Returns one canned response per call."""

    def __init__(self, response):
        self.response = response
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return self.response


def reply_with_thinking_first(text):
    """A response shaped like the real API's: thinking block, then text.

    The thinking block has no .text attribute, like the real ThinkingBlock,
    so code that picks blocks by position fails here.
    """
    thinking = SimpleNamespace(type="thinking", thinking="...")
    answer = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[thinking, answer], stop_reason="end_turn")


class StripJsonFencesTest(unittest.TestCase):
    """strip_json_fences on its own: pure string cleanup."""

    def test_each_reply_shape_parses_to_the_rating(self):
        for name, raw in REPLIES.items():
            with self.subTest(name):
                cleaned = agent.strip_json_fences(raw)
                self.assertEqual(json.loads(cleaned), EXPECTED)


class EvaluateJobTest(unittest.TestCase):
    """evaluate_job end to end, with the inner Claude call faked."""

    def setUp(self):
        self.real_client = agent.client

    def tearDown(self):
        agent.client = self.real_client

    def test_each_reply_shape_with_thinking_block_first(self):
        for name, raw in REPLIES.items():
            with self.subTest(name):
                fake = FakeMessages(reply_with_thinking_first(raw))
                agent.client = SimpleNamespace(messages=fake)
                with mock.patch("builtins.print"):  # keep test output clean
                    result = agent.evaluate_job("Acme", "Architect", "desc")
                self.assertEqual(result, RATED)
                self.assertEqual(fake.calls, 1)


if __name__ == "__main__":
    unittest.main()
