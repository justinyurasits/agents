"""Tests for several tool_use blocks in one Claude reply (issue #7).

Every tool_use block must get its own tool_result, all in ONE user message,
each carrying the id of the request it answers.

No API calls: fake client, and the tool functions are swapped for stand-ins
that record each call. Run from job-evaluator/:
    python -m unittest discover -s tests -v
"""

import json
from types import SimpleNamespace
from unittest import mock

# Shared fakes and the safe `agent` import (no .env, placeholder key).
try:
    from test_tool_errors import FakeClientTestCase, text_response, agent
except ImportError:  # when run as tests.test_multiple_tools
    from tests.test_tool_errors import FakeClientTestCase, text_response, agent


FINAL_TEXT = "Done."
EVAL_INPUT = {"company": "Acme", "role_title": "Architect", "job_description": "desc"}


def flag_input(n):
    return {"company": f"Co{n}", "role_title": "Architect", "missing_info": "comp"}


def tool_use(tool_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=tool_input)


def multi_tool_reply(*blocks, preamble="I'll check these."):
    """One Claude reply asking for several tools. A text block comes first,
    like the real API often sends, so non-tool blocks must be skipped."""
    text = SimpleNamespace(type="text", text=preamble)
    return SimpleNamespace(content=[text, *blocks], stop_reason="tool_use")


class MultipleToolUseTest(FakeClientTestCase):

    def tool_results_sent(self, fake):
        """The user message sent after the multi-tool reply, and its blocks.

        fake.sent[1] is the messages list on the 2nd outer call:
        [job, assistant turn with the tool_use blocks, user turn with results].
        """
        sent = fake.sent[1]
        self.assertEqual(len(sent), 3, "expected exactly ONE user message after the assistant turn")
        assistant, user = sent[1], sent[2]
        self.assertEqual(assistant["role"], "assistant")
        self.assertEqual(user["role"], "user")
        for block in user["content"]:
            self.assertEqual(block["type"], "tool_result")
        return user["content"]

    def test_n_tool_uses_run_n_tools_and_return_n_matching_results(self):
        # n = 1 is the single-request criterion; 2 and 3 are the multi case.
        for n in (1, 2, 3):
            with self.subTest(n=n):
                ids = [f"toolu_{i}" for i in range(1, n + 1)]
                blocks = [tool_use(i, "flag_for_review", flag_input(k))
                          for k, i in enumerate(ids, start=1)]
                with mock.patch.object(agent, "flag_for_review",
                                       wraps=agent.flag_for_review) as spy:
                    final, fake = self.run_with([
                        multi_tool_reply(*blocks),
                        text_response(FINAL_TEXT),
                    ])

                self.assertEqual(final, FINAL_TEXT)
                # n tool functions ran, each with its own input, in order.
                self.assertEqual(spy.call_count, n)
                self.assertEqual([c.kwargs["company"] for c in spy.call_args_list],
                                 [f"Co{k}" for k in range(1, n + 1)])

                # One user message with exactly n results, ids matching in order.
                results = self.tool_results_sent(fake)
                self.assertEqual(len(results), n)
                self.assertEqual([r["tool_use_id"] for r in results], ids)
                # Each result is that request's own output, not a copy of another.
                for k, r in enumerate(results, start=1):
                    self.assertNotIn("is_error", r)
                    self.assertEqual(json.loads(r["content"])["company"], f"Co{k}")

    def test_different_tools_in_one_reply_each_get_their_own_result(self):
        evaluate = mock.Mock(return_value={"rating": "STRONG", "reasons": ["x"]})
        with mock.patch.object(agent, "evaluate_job", evaluate), \
                mock.patch.object(agent, "flag_for_review",
                                  wraps=agent.flag_for_review) as flag:
            final, fake = self.run_with([
                multi_tool_reply(
                    tool_use("toolu_eval", "evaluate_job", EVAL_INPUT),
                    tool_use("toolu_flag", "flag_for_review", flag_input(2)),
                ),
                text_response(FINAL_TEXT),
            ])

        self.assertEqual(final, FINAL_TEXT)
        evaluate.assert_called_once_with(**EVAL_INPUT)
        flag.assert_called_once_with(**flag_input(2))

        results = {r["tool_use_id"]: r for r in self.tool_results_sent(fake)}
        self.assertEqual(set(results), {"toolu_eval", "toolu_flag"})
        self.assertEqual(json.loads(results["toolu_eval"]["content"])["rating"], "STRONG")
        self.assertEqual(json.loads(results["toolu_flag"]["content"])["status"], "flagged")

    def test_one_failing_tool_does_not_drop_the_others(self):
        # Regression guard where #7 meets #8: errors are handled per tool,
        # so a failure in one block still leaves a result for every block.
        boom = mock.Mock(side_effect=RuntimeError("grader down"))
        with mock.patch.object(agent, "evaluate_job", boom):
            final, fake = self.run_with([
                multi_tool_reply(
                    tool_use("toolu_a", "evaluate_job", EVAL_INPUT),
                    tool_use("toolu_b", "flag_for_review", flag_input(2)),
                ),
                text_response(FINAL_TEXT),
            ])

        self.assertEqual(final, FINAL_TEXT)
        results = self.tool_results_sent(fake)
        self.assertEqual([r["tool_use_id"] for r in results], ["toolu_a", "toolu_b"])
        self.assertIs(results[0]["is_error"], True)
        self.assertIn("grader down", results[0]["content"])
        self.assertNotIn("is_error", results[1])
        self.assertEqual(json.loads(results[1]["content"])["status"], "flagged")


if __name__ == "__main__":
    import unittest
    unittest.main()
