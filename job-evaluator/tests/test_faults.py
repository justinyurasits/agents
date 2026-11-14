"""Tests for fault injection (issue #46).

Fake Claude replies built from real SDK types (tests/fakes.py). No API calls.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import json
import os
import unittest
from unittest import mock

try:
    import fakes
    from test_tracing import TraceTestCase, kind, EVAL_INPUT, GRADE, FINAL
except ImportError:  # when run as tests.test_faults
    from tests import fakes
    from tests.test_tracing import TraceTestCase, kind, EVAL_INPUT, GRADE, FINAL

agent = fakes.agent
import faults   # noqa: E402
import tracing  # noqa: E402

SCENARIOS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "scenarios", "scenarios.json")


def evaluate(tool_id):
    return fakes.reply(fakes.tool_use(tool_id, "evaluate_job", EVAL_INPUT), stop_reason="tool_use")


def fault_events(rec):
    return [e for e in rec.events if e["payload"] and isinstance(e["payload"], dict)
            and "fault" in e["payload"]]


def guard(rec, name, caught=None):
    return [e for e in rec.events if e["guard"] and e["guard"]["name"] == name
            and (caught is None or e["guard"]["caught"] is caught)]


class FaultRunTestCase(TraceTestCase):

    def run_fault(self, name, outer, inner=()):
        fakes.use_fake(outer, inner)
        rec = tracing.Recorder(scenario="test", git=("abc1234", False))
        final = agent.run_agent("Acme — Architect", recorder=rec, fault=faults.Fault(name))
        return final, rec


class ToolFailsTest(FaultRunTestCase):

    def run_it(self):
        # Claude asks for evaluate_job, it fails (injected), Claude retries,
        # it works (the fault fires once), Claude finishes.
        return self.run_fault("tool_fails",
                              outer=[evaluate("toolu_1"), evaluate("toolu_2"), fakes.reply(fakes.text(FINAL))],
                              inner=[fakes.reply(fakes.text(GRADE)), fakes.reply(fakes.text(GRADE))])

    def test_guard_catches_it_error_result_and_the_run_finishes(self):
        final, rec = self.run_it()
        self.assertEqual(final, FINAL)
        self.assertEqual(rec.result["ended_by"], "end_turn")
        caught = guard(rec, "tool_succeeded", caught=True)
        self.assertEqual(len(caught), 1)                       # once only
        nxt = rec.events[rec.events.index(caught[0]) + 1]
        self.assertEqual(kind(nxt), "tool_result")
        self.assertIs(nxt["payload"]["is_error"], True)
        self.assertIn("JSONDecodeError", nxt["payload"]["content"])
        # The retry worked: the second result is a real rating.
        results = [e for e in rec.events if kind(e) == "tool_result"]
        self.assertEqual(json.loads(results[1]["payload"]["content"])["rating"], "WORTH REVIEWING")

    def test_fault_event_records_the_real_and_the_injected_reply(self):
        _, rec = self.run_it()
        (event,) = fault_events(rec)
        first_call = next(e for e in rec.events if kind(e) == "tool_call")
        self.assertEqual(event["step_id"], "inner_grader")
        self.assertEqual(event["parent"], first_call["id"])
        self.assertEqual(event["payload"], {"fault": "tool_fails",
                                            "grader_reply": {"real": GRADE, "injected": faults.BROKEN_JSON}})
        # The real grader response is recorded as it came back, not injected.
        first_response = next(e for e in rec.events if kind(e) == "inner_api_response")
        self.assertIs(first_response["injected"], False)
        self.assertEqual(first_response["payload"]["content"][0]["text"], GRADE)

    def test_exactly_the_faults_effects_are_injected(self):
        _, rec = self.run_it()
        injected = [(e["pass"], e["step_id"], kind(e)) for e in rec.events if e["injected"]]
        self.assertEqual(injected, [
            (1, "inner_grader", None),                          # fault_injected
            (1, "tool_failed", ("guard", "tool_succeeded")),
            (1, "run_tools", "tool_result"),
            (1, "results_back", None),
        ])


class UnknownToolTest(FaultRunTestCase):

    def run_it(self):
        return self.run_fault("unknown_tool",
                              outer=[evaluate("toolu_1"), evaluate("toolu_2"), fakes.reply(fakes.text(FINAL))],
                              inner=[fakes.reply(fakes.text(GRADE))])

    def test_tool_exists_catches_it_lists_real_tools_and_the_run_finishes(self):
        final, rec = self.run_it()
        self.assertEqual(final, FINAL)
        (g,) = guard(rec, "tool_exists", caught=True)
        self.assertEqual(g["guard"]["value"], faults.UNKNOWN_TOOL)
        self.assertEqual(g["guard"]["message"],
                         f"ValueError: Unknown tool '{faults.UNKNOWN_TOOL}'. "
                         "Available tools: evaluate_job, flag_for_review, research_company.")
        # Once only: the second request runs evaluate_job for real.
        self.assertEqual(len([e for e in rec.events if kind(e) == "tool_call"]), 1)

    def test_rename_is_everywhere_but_the_real_response_is_kept(self):
        _, rec = self.run_it()
        (event,) = fault_events(rec)
        self.assertEqual(event["step_id"], "save_turn")
        self.assertEqual(event["payload"]["tool_name"], {"real": "evaluate_job",
                                                         "injected": faults.UNKNOWN_TOOL})
        first_response = next(e for e in rec.events if kind(e) == "api_response")
        self.assertEqual(first_response["payload"]["content"][0]["name"], "evaluate_job")
        self.assertIs(first_response["injected"], False)
        saved = next(e for e in rec.events
                     if e["step_id"] == "save_turn" and e["messages_after"] is not None)
        self.assertEqual(saved["messages_after"][-1]["content"][0]["name"], faults.UNKNOWN_TOOL)
        self.assertIs(saved["injected"], True)

    def test_exactly_the_faults_effects_are_injected(self):
        _, rec = self.run_it()
        injected = [(e["pass"], e["step_id"], kind(e)) for e in rec.events if e["injected"]]
        self.assertEqual(injected, [
            (1, "save_turn", None),                             # fault_injected
            (1, "save_turn", None),
            (1, "unknown_tool", ("guard", "tool_exists")),
            (1, "run_tools", None),                             # Python's error result
            (1, "results_back", None),
        ])


class RunawayLoopTest(FaultRunTestCase):

    def run_it(self):
        retry_forever = [evaluate(f"toolu_{n}") for n in range(1, 11)]
        return self.run_fault("runaway_loop", outer=retry_forever,
                              inner=[fakes.reply(fakes.text(GRADE)) for _ in range(10)])

    def test_stops_at_the_lowered_cap(self):
        final, rec = self.run_it()
        self.assertEqual(final, f"Stopped after {faults.RUNAWAY_MAX_PASSES} passes without finishing.")
        self.assertEqual(rec.result["ended_by"], "pass_cap")
        self.assertEqual(max(e["pass"] for e in rec.events), faults.RUNAWAY_MAX_PASSES)

    def test_every_grader_reply_is_broken_and_the_cap_change_is_recorded(self):
        _, rec = self.run_it()
        events = fault_events(rec)
        limits = [e for e in events if "max_passes" in e["payload"]]
        swaps = [e for e in events if "grader_reply" in e["payload"]]
        self.assertEqual(limits[0]["payload"]["max_passes"],
                         {"normal": agent.MAX_PASSES, "injected": faults.RUNAWAY_MAX_PASSES})
        self.assertEqual(len(swaps), faults.RUNAWAY_MAX_PASSES)       # every call
        self.assertEqual(len(guard(rec, "tool_succeeded", caught=True)), faults.RUNAWAY_MAX_PASSES)

    def test_cap_events_are_injected(self):
        _, rec = self.run_it()
        cap_guard, end = rec.events[-2], rec.events[-1]
        self.assertEqual((cap_guard["guard"]["name"], cap_guard["guard"]["caught"]), ("pass_count", True))
        self.assertIs(cap_guard["injected"], True)
        self.assertIs(end["injected"], True)
        self.assertTrue(all(g["injected"] for g in guard(rec, "pass_count")))


class ReplyCutOffTest(FaultRunTestCase):

    class TokenLimitedClaude(fakes.FakeClaude):
        """Behaves like the real API: a small max_tokens cuts the reply off."""
        def create(self, **kwargs):
            if "tools" in kwargs and kwargs["max_tokens"] <= 50:
                self.seen_limit = kwargs["max_tokens"]
                return fakes.reply(fakes.tool_use("toolu_1", "evaluate_job", EVAL_INPUT),
                                   stop_reason="max_tokens")
            return super().create(**kwargs)

    def run_it(self):
        fake = self.TokenLimitedClaude(outer=[evaluate("toolu_1")])
        agent.client = type("C", (), {"messages": fake})()
        rec = tracing.Recorder(scenario="test", git=("abc1234", False))
        final = agent.run_agent("Acme — Architect", recorder=rec, fault=faults.Fault("reply_cut_off"))
        return final, rec, fake

    def test_stops_with_the_cut_off_message_and_nothing_dispatched(self):
        final, rec, fake = self.run_it()
        self.assertEqual(fake.seen_limit, faults.CUT_OFF_MAX_TOKENS)
        self.assertEqual(final, "Claude's reply was cut off (hit the max_tokens limit "
                                f"of {faults.CUT_OFF_MAX_TOKENS}).")
        self.assertNotIn("tool_call", [kind(e) for e in rec.events])
        self.assertEqual(rec.result["ended_by"], "max_tokens")

    def test_everything_under_the_lowered_limit_is_injected(self):
        _, rec, _ = self.run_it()
        (limit,) = fault_events(rec)
        self.assertEqual(limit["payload"]["max_tokens"],
                         {"normal": agent.MAX_TOKENS, "injected": faults.CUT_OFF_MAX_TOKENS})
        not_injected = [(e["step_id"], kind(e)) for e in rec.events if not e["injected"]]
        # Before the first call, plus the pass-count check: this fault lowers
        # the token limit, not the pass cap, so that check isn't touched.
        self.assertEqual(not_injected, [("agent_starts", None), ("conversation_setup", None),
                                        ("send_to_claude", ("guard", "pass_count"))])
        request = next(e for e in rec.events if kind(e) == "api_request")
        self.assertEqual(request["payload"]["max_tokens"], faults.CUT_OFF_MAX_TOKENS)


class NoFaultTest(FaultRunTestCase):

    def test_no_fault_injects_nothing(self):
        final, rec = self.run_fault(None, outer=[evaluate("toolu_1"), fakes.reply(fakes.text(FINAL))],
                                    inner=[fakes.reply(fakes.text(GRADE))])
        self.assertEqual(final, FINAL)
        self.assertEqual(fault_events(rec), [])
        self.assertTrue(all(e["injected"] is False for e in rec.events))
        self.assertIsNone(rec.to_dict()["fault"])

    def test_empty_fault_changes_nothing(self):
        f = faults.Fault()
        self.assertFalse(f)
        self.assertEqual(f.max_passes(10), 10)
        self.assertEqual(f.max_tokens(2000), 2000)
        self.assertEqual(f.grader_reply("x"), "x")
        self.assertIsNone(f.tool_request(fakes.reply(fakes.tool_use("t", "evaluate_job", {}))))

    def test_unknown_fault_name_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Unknown fault 'explode'"):
            faults.Fault("explode")

    def test_no_fault_is_left_active_for_the_next_run(self):
        self.run_fault("runaway_loop", outer=[evaluate(f"t{n}") for n in range(2)],
                       inner=[fakes.reply(fakes.text(GRADE)) for _ in range(2)])
        final, rec = self.run_fault(None, outer=[evaluate("toolu_1"), fakes.reply(fakes.text(FINAL))],
                                    inner=[fakes.reply(fakes.text(GRADE))])
        self.assertEqual(final, FINAL)
        self.assertEqual(fault_events(rec), [])


class ChooseRunTest(unittest.TestCase):

    def test_default_is_the_sample_posting_with_no_fault(self):
        self.assertEqual(agent.choose_run([], SCENARIOS), (agent.SAMPLE_JOB, "clean", None))

    def test_scenario_brings_its_posting_and_fault(self):
        with open(SCENARIOS, encoding="utf-8") as f:
            six = next(s for s in json.load(f) if s["id"] == 6)
        self.assertEqual(agent.choose_run(["--scenario", "6"], SCENARIOS),
                         (six["posting"], "scenario-6", "tool_fails"))

    def test_fault_flag_alone_and_overriding_a_scenario(self):
        self.assertEqual(agent.choose_run(["--fault", "reply_cut_off"], SCENARIOS),
                         (agent.SAMPLE_JOB, "reply_cut_off", "reply_cut_off"))
        _, name, fault = agent.choose_run(["--scenario", "1", "--fault", "runaway_loop"], SCENARIOS)
        self.assertEqual((name, fault), ("scenario-1", "runaway_loop"))

    def test_bad_input_is_refused(self):
        for argv in (["--fault", "explode"], ["--scenario", "99"]):
            with self.subTest(argv), self.assertRaises(SystemExit), \
                    mock.patch("sys.stderr"):
                agent.choose_run(argv, SCENARIOS)

    def test_break_scenarios_name_real_faults(self):
        with open(SCENARIOS, encoding="utf-8") as f:
            named = {s["id"]: s["fault"] for s in json.load(f) if s["fault"]}
        self.assertEqual(named, {6: "tool_fails", 7: "unknown_tool", 8: "runaway_loop", 9: "reply_cut_off"})
        self.assertLessEqual(set(named.values()), set(faults.FAULTS))


if __name__ == "__main__":
    unittest.main()
