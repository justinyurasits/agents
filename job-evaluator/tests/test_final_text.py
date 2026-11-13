"""Tests for an end_turn reply with no text block (issue #31).

Fake Claude replies built from real SDK types (tests/fakes.py). No API calls.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import unittest

try:
    import fakes
    from test_tracing import TraceTestCase, kind, FLAG_INPUT
except ImportError:  # when run as tests.test_final_text
    from tests import fakes
    from tests.test_tracing import TraceTestCase, kind, FLAG_INPUT

agent = fakes.agent

NO_ANSWER = "Claude finished without writing a final answer."


class NoTextBlockTest(TraceTestCase):

    def test_only_a_thinking_block(self):
        final, _ = self.record(outer=[fakes.reply(fakes.thinking("Nothing more to add."))])
        self.assertEqual(final, NO_ANSWER)

    def test_empty_content(self):
        final, _ = self.record(outer=[fakes.reply()])
        self.assertEqual(final, NO_ANSWER)

    def test_without_a_recorder_too(self):
        fakes.use_fake(outer=[fakes.reply(fakes.thinking())])
        self.assertEqual(agent.run_agent("Acme — Architect"), NO_ANSWER)

    def test_on_a_later_pass_after_a_tool_ran(self):
        final, rec = self.record(outer=[
            fakes.reply(fakes.tool_use("toolu_1", "flag_for_review", FLAG_INPUT),
                        stop_reason="tool_use"),
            fakes.reply(fakes.thinking("Flagged; done.")),
        ])
        self.assertEqual(final, NO_ANSWER)
        self.assertIn("tool_result", [kind(e) for e in rec.events])
        self.assertEqual(rec.events[-1]["pass"], 2)


class SeveralTextBlocksTest(TraceTestCase):

    def test_first_text_block_is_returned_as_before(self):
        final, _ = self.record(outer=[fakes.reply(fakes.thinking(), fakes.text("First."),
                                                  fakes.text("Second."))])
        self.assertEqual(final, "First.")


class TraceTest(TraceTestCase):

    def test_trace_ends_with_the_caught_guard_then_run_end(self):
        final, rec = self.record(outer=[fakes.reply(fakes.thinking())])
        guard, end = rec.events[-2], rec.events[-1]
        self.assertEqual(guard["step_id"], "no_final_answer")
        self.assertEqual(guard["guard"], {"name": "final_text_present",
                                          "checked": "the reply has a text block",
                                          "value": None, "caught": True,
                                          "action": "run_stopped", "message": final})
        self.assertEqual(end["step_id"], "no_final_answer")
        self.assertEqual(end["payload"], {"ended_by": "no_text", "text": final})
        self.assertEqual(rec.result, {"ended_by": "no_text", "text": final})

    def test_a_normal_finish_records_the_check_uncaught(self):
        _, rec = self.record(outer=[fakes.reply(fakes.text("Done."))])
        guard = rec.events[-2]
        self.assertEqual(guard["step_id"], "answer_returned")
        self.assertEqual(guard["guard"]["name"], "final_text_present")
        self.assertIs(guard["guard"]["caught"], False)
        self.assertEqual(rec.result["ended_by"], "end_turn")


if __name__ == "__main__":
    unittest.main()
