"""Tests for API errors on the outer Claude call (issue #30).

The fake client raises the SDK's real error types (built on httpx2, which the
SDK already depends on). No API calls are made.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import json
import os
import tempfile
import unittest
from unittest import mock

import anthropic
import httpx2

try:
    import fakes
    from test_tracing import TraceTestCase, kind, EVAL_INPUT, FLAG_INPUT, GRADE, FINAL
except ImportError:  # when run as tests.test_api_errors
    from tests import fakes
    from tests.test_tracing import TraceTestCase, kind, EVAL_INPUT, FLAG_INPUT, GRADE, FINAL

agent = fakes.agent

URL = "https://api.anthropic.com/v1/messages"


def request():
    # Like a real request, this one carries the key in a header. Neither the
    # key nor the header may end up in the message or the trace.
    return httpx2.Request("POST", URL, headers={"x-api-key": fakes.FAKE_KEY})


def status_error(cls, code):
    # The error text mentions the key on purpose: the message must not echo it.
    return cls(f"Error code: {code} - rejected key {fakes.FAKE_KEY}",
               response=httpx2.Response(code, request=request()), body=None)


ERRORS = {
    "connection": (anthropic.APIConnectionError(request=request()), "APIConnectionError", None),
    "timeout":    (anthropic.APITimeoutError(request=request()), "APITimeoutError", None),
    "bad key":    (status_error(anthropic.AuthenticationError, 401), "AuthenticationError", 401),
    "rate limit": (status_error(anthropic.RateLimitError, 429), "RateLimitError", 429),
    "overloaded": (status_error(anthropic.OverloadedError, 529), "OverloadedError", 529),
    "server":     (status_error(anthropic.InternalServerError, 500), "InternalServerError", 500),
}


def expected_message(name, status):
    detail = f" (status {status})" if status else ""
    return f"Couldn't get a reply from Claude: {name}{detail}. The run stopped."


class OuterApiErrorTest(TraceTestCase):

    def test_each_api_error_returns_a_message_naming_it(self):
        for label, (error, name, status) in ERRORS.items():
            with self.subTest(label):
                final, _ = self.record(outer=[error])            # no crash
                self.assertEqual(final, expected_message(name, status))

    def test_without_a_recorder_too(self):
        error, name, status = ERRORS["overloaded"]
        fakes.use_fake(outer=[error])
        self.assertEqual(agent.run_agent("Acme — Architect"), expected_message(name, status))

    def test_no_key_or_headers_in_the_message_or_trace(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": fakes.FAKE_KEY}):
            for label, (error, _, _) in ERRORS.items():
                with self.subTest(label):
                    final, rec = self.record(outer=[error])
                    for text in (final, json.dumps(rec.to_dict())):
                        self.assertNotIn("sk-ant", text)
                        self.assertNotIn("x-api-key", text)
                        self.assertNotIn(URL, text)
                    with tempfile.TemporaryDirectory() as d:
                        rec.write(d)                          # writer accepts it

    def test_failure_on_a_later_pass_after_a_tool_ran(self):
        error, name, status = ERRORS["rate limit"]
        final, rec = self.record(outer=[
            fakes.reply(fakes.tool_use("toolu_1", "flag_for_review", FLAG_INPUT),
                        stop_reason="tool_use"),
            error,                                             # pass 2 fails
        ])
        self.assertEqual(final, expected_message(name, status))
        self.assertIn("tool_result", [kind(e) for e in rec.events])
        self.assertEqual(rec.events[-1]["pass"], 2)


class TraceOfApiErrorTest(TraceTestCase):

    def test_trace_ends_with_the_caught_guard_then_run_end(self):
        error, name, status = ERRORS["bad key"]
        final, rec = self.record(outer=[error])
        guard, end = rec.events[-2], rec.events[-1]
        self.assertEqual(guard["step_id"], "api_call_failed")
        self.assertEqual(guard["guard"], {"name": "api_call_succeeded",
                                          "checked": "client.messages.create returned a reply",
                                          "value": name, "caught": True,
                                          "action": "run_stopped", "message": final})
        self.assertEqual(end["step_id"], "api_call_failed")
        self.assertEqual(end["payload"], {"ended_by": "api_error", "text": final})
        self.assertEqual(rec.result, {"ended_by": "api_error", "text": final})
        # No reply came back, so there's no api_response event.
        self.assertNotIn("api_response", [kind(e) for e in rec.events])

    def test_successful_calls_record_the_check_uncaught(self):
        _, rec = self.record(outer=[fakes.reply(fakes.text(FINAL))])
        checks = [e for e in rec.events if e["guard"] and e["guard"]["name"] == "api_call_succeeded"]
        self.assertEqual(len(checks), 1)
        self.assertIs(checks[0]["guard"]["caught"], False)
        self.assertEqual(checks[0]["step_id"], "send_to_claude")


class GraderApiErrorTest(TraceTestCase):
    """Regression guard: the grader's call is inside a tool, so its API errors
    stay tool errors (#8). Only the outer call stops the run."""

    def test_grader_api_error_is_still_a_tool_error_and_the_run_continues(self):
        error, name, _ = ERRORS["rate limit"]
        final, rec = self.record(
            outer=[fakes.reply(fakes.tool_use("toolu_1", "evaluate_job", EVAL_INPUT),
                               stop_reason="tool_use"),
                   fakes.reply(fakes.text(FINAL))],
            inner=[error])
        self.assertEqual(final, FINAL)
        result = next(e for e in rec.events if kind(e) == "tool_result")
        self.assertIs(result["payload"]["is_error"], True)
        self.assertTrue(result["payload"]["content"].startswith(name + ":"))
        self.assertEqual(rec.result["ended_by"], "end_turn")


if __name__ == "__main__":
    unittest.main()
