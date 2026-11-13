"""Tests for inner-call events, guard events and `injected` (issue #29).

Fake Claude replies built from real SDK types (tests/fakes.py). No API calls.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import json
import unittest
from unittest import mock

try:
    import fakes
    from test_tracing import TraceTestCase, kind, EVAL_INPUT, FLAG_INPUT, GRADE, FINAL
except ImportError:  # when run as tests.test_guard_events
    from tests import fakes
    from tests.test_tracing import TraceTestCase, kind, EVAL_INPUT, FLAG_INPUT, GRADE, FINAL

agent = fakes.agent
import code_refs  # noqa: E402
import tracing    # noqa: E402

GUARD_KEYS = ["name", "checked", "value", "caught", "action", "message"]


def guards(rec, name=None, caught=None):
    return [e for e in rec.events if e["guard"]
            and (name is None or e["guard"]["name"] == name)
            and (caught is None or e["guard"]["caught"] is caught)]


def one_tool_then_done(tool_id, name, tool_input):
    return [fakes.reply(fakes.tool_use(tool_id, name, tool_input), stop_reason="tool_use"),
            fakes.reply(fakes.text(FINAL))]


class InnerCallTest(TraceTestCase):

    def test_grader_call_is_parented_to_the_evaluate_job_tool_call(self):
        _, rec = self.record(outer=one_tool_then_done("toolu_1", "evaluate_job", EVAL_INPUT),
                             inner=[fakes.reply(fakes.text(GRADE), input_tokens=240, output_tokens=96)])
        call = next(e for e in rec.events if kind(e) == "tool_call")
        request = next(e for e in rec.events if kind(e) == "inner_api_request")
        response = next(e for e in rec.events if kind(e) == "inner_api_response")

        self.assertEqual(call["payload"]["tool"], "evaluate_job")
        for e in (request, response):
            self.assertEqual(e["parent"], call["id"])
            self.assertEqual(e["step_id"], "inner_grader")
        self.assertEqual(request["crossing"], {"from": "tool", "to": "claude", "kind": "inner_api_request"})
        self.assertEqual(response["crossing"], {"from": "claude", "to": "tool", "kind": "inner_api_response"})
        self.assertEqual(request["payload"]["system"], agent.RUBRIC)
        self.assertEqual(request["payload"]["tools"], [])
        self.assertIn("Company: Northwind Labs", request["payload"]["messages"][0]["content"])
        self.assertEqual(response["payload"]["content"][0]["text"], GRADE)
        self.assertEqual(response["tokens"], {"input": 240, "output": 96})
        # The grader's own max_tokens check belongs to the same tool call.
        self.assertEqual(guards(rec, "max_tokens")[-1]["parent"], call["id"])

    def test_only_events_inside_a_tool_have_a_parent(self):
        _, rec = self.record(outer=one_tool_then_done("toolu_1", "evaluate_job", EVAL_INPUT),
                             inner=[fakes.reply(fakes.text(GRADE))])
        parented = {e["step_id"] for e in rec.events if e["parent"]}
        self.assertEqual(parented, {"inner_grader"})

    def test_evaluate_job_outside_a_run_records_nothing(self):
        _, rec = self.record(outer=[fakes.reply(fakes.text(FINAL))])
        count = len(rec.events)
        fakes.use_fake(outer=[], inner=[fakes.reply(fakes.text(GRADE))])
        agent.evaluate_job(**EVAL_INPUT)
        self.assertEqual(len(rec.events), count)
        self.assertIsInstance(tracing.active(), tracing.NullRecorder)


class CaughtGuardTest(TraceTestCase):

    def test_tool_raises_then_tool_result_is_error(self):
        with mock.patch.object(agent, "evaluate_job", side_effect=RuntimeError("grader down")):
            _, rec = self.record(outer=one_tool_then_done("toolu_1", "evaluate_job", EVAL_INPUT))
        caught = guards(rec, "tool_succeeded", caught=True)
        self.assertEqual(len(caught), 1)
        g = caught[0]
        self.assertEqual(g["step_id"], "tool_failed")
        self.assertEqual(g["guard"]["action"], "error_sent_to_claude")
        self.assertEqual(g["guard"]["value"], "RuntimeError")
        self.assertEqual(g["guard"]["message"], "RuntimeError: grader down")
        # Directly followed by the tool_result with is_error.
        nxt = rec.events[rec.events.index(g) + 1]
        self.assertEqual(kind(nxt), "tool_result")
        self.assertIs(nxt["payload"]["is_error"], True)
        self.assertEqual(nxt["payload"]["content"], g["guard"]["message"])

    def test_loop_cap_ends_with_pass_count_guard_then_run_end(self):
        never_done = [fakes.reply(fakes.tool_use(f"toolu_{n}", "flag_for_review", FLAG_INPUT),
                                  stop_reason="tool_use") for n in range(agent.MAX_PASSES)]
        final, rec = self.record(outer=never_done)
        guard, end = rec.events[-2], rec.events[-1]
        self.assertEqual(guard["guard"]["name"], "pass_count")
        self.assertIs(guard["guard"]["caught"], True)
        self.assertEqual(guard["step_id"], "pass_cap")
        self.assertEqual(guard["guard"]["value"], agent.MAX_PASSES + 1)
        self.assertEqual(guard["guard"]["action"], "run_stopped")
        self.assertEqual(guard["guard"]["message"], final)
        self.assertEqual(end["step_id"], "pass_cap")
        self.assertEqual(end["payload"], {"ended_by": "pass_cap", "text": final})
        # One uncaught pass_count check at the start of every pass.
        self.assertEqual([g["guard"]["value"] for g in guards(rec, "pass_count", caught=False)],
                         list(range(1, agent.MAX_PASSES + 1)))

    def test_unknown_tool(self):
        _, rec = self.record(outer=one_tool_then_done("toolu_x", "search_web", {"q": "Acme"}))
        caught = guards(rec, caught=True)
        self.assertEqual(len(caught), 1)                 # only tool_exists, no tool ran
        g = caught[0]
        self.assertEqual(g["guard"]["name"], "tool_exists")
        self.assertEqual(g["step_id"], "unknown_tool")
        self.assertEqual(g["guard"]["value"], "search_web")
        self.assertEqual(g["guard"]["action"], "error_sent_to_claude")
        self.assertEqual(g["guard"]["message"],
                         "ValueError: Unknown tool 'search_web'. Available tools: "
                         "evaluate_job, flag_for_review.")
        self.assertNotIn("tool_call", [kind(e) for e in rec.events])
        # Python itself answers: no tool, so no crossing.
        nxt = rec.events[rec.events.index(g) + 1]
        self.assertEqual((nxt["step_id"], nxt["actor"], nxt["crossing"]), ("run_tools", "python", None))
        self.assertIs(nxt["payload"]["is_error"], True)
        self.assertEqual(nxt["payload"]["content"], g["guard"]["message"])

    def test_main_loop_reply_cut_off(self):
        final, rec = self.record(outer=[fakes.reply(
            fakes.tool_use("toolu_1", "flag_for_review", FLAG_INPUT), stop_reason="max_tokens")])
        caught = guards(rec, caught=True)
        self.assertEqual(len(caught), 1)
        g = caught[0]
        self.assertEqual((g["guard"]["name"], g["step_id"]), ("max_tokens", "reply_cut_off"))
        self.assertEqual(g["guard"]["action"], "run_stopped")
        self.assertEqual(g["guard"]["message"], final)
        self.assertEqual(rec.events[-1]["step_id"], "reply_cut_off")      # then run_end
        self.assertNotIn("tool_call", [kind(e) for e in rec.events])    # nothing dispatched

    def test_grader_reply_cut_off(self):
        _, rec = self.record(outer=one_tool_then_done("toolu_1", "evaluate_job", EVAL_INPUT),
                             inner=[fakes.reply(fakes.text('{"rating": "STR'), stop_reason="max_tokens")])
        call = next(e for e in rec.events if kind(e) == "tool_call")
        grader = next(e for e in guards(rec, "max_tokens", caught=True))
        self.assertEqual(grader["step_id"], "grader_cut_off")
        self.assertEqual(grader["parent"], call["id"])
        self.assertEqual(grader["guard"]["action"], "error_raised")
        # The raised error then fails the tool, with the same text.
        failed = next(e for e in guards(rec, "tool_succeeded", caught=True))
        self.assertEqual(failed["guard"]["message"], "RuntimeError: " + grader["guard"]["message"])
        self.assertLess(grader["seq"], failed["seq"])


class AllGuardsTest(TraceTestCase):

    SCENARIOS = {
        "clean": dict(outer=one_tool_then_done("toolu_1", "evaluate_job", EVAL_INPUT),
                      inner=[fakes.reply(fakes.text(GRADE))]),
        "flag": dict(outer=one_tool_then_done("toolu_1", "flag_for_review", FLAG_INPUT)),
        "unknown": dict(outer=one_tool_then_done("toolu_1", "search_web", {})),
        "bad_json": dict(outer=one_tool_then_done("toolu_1", "evaluate_job", EVAL_INPUT),
                         inner=[fakes.reply(fakes.text("not json"))]),
        "cut_off": dict(outer=[fakes.reply(fakes.text("Here"), stop_reason="max_tokens")]),
    }

    def runs(self):
        for name, replies in self.SCENARIOS.items():
            yield name, self.record(**replies)[1]

    def test_every_event_has_injected_false(self):
        for name, rec in self.runs():
            with self.subTest(name):
                self.assertTrue(all(e["injected"] is False for e in rec.events))

    def test_guard_shape_and_meaning_of_caught(self):
        error_steps = {"tool_failed", "unknown_tool", "reply_cut_off", "pass_cap", "grader_cut_off"}
        for name, rec in self.runs():
            for g in guards(rec):
                with self.subTest(name, guard=g["id"]):
                    self.assertEqual(list(g["guard"]), GUARD_KEYS)
                    self.assertEqual(g["actor"], "python")
                    self.assertIsNone(g["crossing"])
                    # Caught guards (and only those) use the error-case steps.
                    self.assertEqual(g["step_id"] in error_steps, g["guard"]["caught"])
                    if not g["guard"]["caught"]:
                        self.assertIsNone(g["guard"]["message"])

    def test_every_event_points_at_its_markers_code(self):
        source = code_refs.load_source()
        for name, rec in self.runs():
            for e in rec.events:
                with self.subTest(name, event=e["id"]):
                    self.assertEqual(e["code"], code_refs.code_ref(e["step_id"], source))

    def test_no_recorder_is_left_active_after_a_run(self):
        for name, rec in self.runs():
            with self.subTest(name):
                self.assertIsInstance(tracing.active(), tracing.NullRecorder)

    def test_trace_still_json_and_secret_free(self):
        for name, rec in self.runs():
            with self.subTest(name):
                self.assertNotIn("sk-ant", json.dumps(rec.to_dict()))


if __name__ == "__main__":
    unittest.main()
