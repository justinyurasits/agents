"""Tests for stop reasons the agent doesn't handle (issue #21).

Only "tool_use" asks for tools. Any other stop reason that isn't "end_turn"
or "max_tokens" (refusal, stop_sequence, pause_turn, ...) must stop the run
with a message naming it, without dispatching a tool or sending another
request. Fake Claude replies built from real SDK types (tests/fakes.py).
No API calls.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import unittest
from unittest import mock

try:
    import fakes
    from test_tracing import TraceTestCase, kind, EVAL_INPUT, GRADE, FINAL
except ImportError:  # when run as tests.test_unexpected_stop
    from tests import fakes
    from tests.test_tracing import TraceTestCase, kind, EVAL_INPUT, GRADE, FINAL

agent = fakes.agent

# Every stop reason in the SDK that the agent doesn't handle on purpose.
UNHANDLED = ("refusal", "stop_sequence", "pause_turn", "model_context_window_exceeded")


def message_for(stop_reason):
    return (f"Claude stopped for a reason this agent doesn't handle "
            f"(stop_reason {stop_reason!r}). The run stopped.")


class StopsTest(TraceTestCase):

    def run_with(self, stop_reason, *blocks):
        fake = fakes.use_fake(outer=[fakes.reply(fakes.thinking(), *blocks,
                                                 stop_reason=stop_reason)])
        return fake, agent.run_agent("a posting")

    def test_each_unhandled_stop_reason_stops_with_a_message_naming_it(self):
        for stop_reason in UNHANDLED:
            with self.subTest(stop_reason):
                fake, answer = self.run_with(stop_reason, fakes.text("I can't help with that."))
                self.assertEqual(answer, message_for(stop_reason))
                self.assertEqual(fake.outer, [])      # the one reply was used, nothing more sent

    def test_no_tool_is_dispatched_even_if_the_reply_has_a_tool_request(self):
        evaluate = fakes.tool_use("toolu_1", "evaluate_job", EVAL_INPUT)
        with mock.patch.object(agent, "evaluate_job") as tool:
            _, answer = self.run_with("pause_turn", evaluate)
        tool.assert_not_called()
        self.assertEqual(answer, message_for("pause_turn"))

    def test_no_second_request_is_sent(self):
        # Before the fix, a text-only refusal went on to the dispatch and sent
        # a user message with empty content. Count the outer calls.
        calls = []
        fake = fakes.FakeClaude(outer=[fakes.reply(fakes.text("No."), stop_reason="refusal")])
        real_create = fake.create
        fake.create = lambda **kw: calls.append(kw) or real_create(**kw)
        agent.client = type("FakeClient", (), {"messages": fake})()
        agent.run_agent("a posting")
        self.assertEqual(len(calls), 1)


class ToolUseStillWorksTest(TraceTestCase):

    def test_tool_use_still_dispatches_and_finishes(self):
        final, rec = self.record(
            outer=[fakes.reply(fakes.tool_use("toolu_1", "evaluate_job", EVAL_INPUT),
                               stop_reason="tool_use"),
                   fakes.reply(fakes.text(FINAL))],
            inner=[fakes.reply(fakes.text(GRADE))])
        self.assertEqual(final, FINAL)
        self.assertTrue(any(kind(e) == "tool_call" for e in rec.events))
        known = next(e for e in rec.events if kind(e) == ("guard", "stop_reason_known"))
        self.assertEqual((known["step_id"], known["guard"]["caught"]), ("check_reply", False))


class TraceTest(TraceTestCase):

    def test_caught_guard_then_the_final_event(self):
        final, rec = self.record(outer=[fakes.reply(fakes.text("I can't help with that."),
                                                    stop_reason="refusal")])
        caught = [e for e in rec.events if e["guard"] and e["guard"]["caught"]]
        self.assertEqual(len(caught), 1)
        self.assertEqual(caught[0]["step_id"], "unexpected_stop")
        self.assertEqual(caught[0]["guard"], {
            "name": "stop_reason_known", "checked": 'stop_reason == "tool_use"',
            "value": "refusal", "caught": True, "action": "run_stopped",
            "message": message_for("refusal")})
        last = rec.events[-1]
        self.assertEqual(last["step_id"], "unexpected_stop")
        self.assertEqual(last["payload"], {"ended_by": "unexpected_stop", "text": final})
        self.assertEqual(rec.result, {"ended_by": "unexpected_stop", "text": final})
        self.assertFalse([e for e in rec.events if kind(e) == "tool_call"])
        self.assertFalse([e for e in rec.events if e["step_id"] == "save_turn"])


if __name__ == "__main__":
    unittest.main()
