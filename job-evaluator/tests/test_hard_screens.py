"""Tests for the hard screens in code: remote and the $180K floor (issue #26).

The rules are checked in evaluate_job before the rating call; a posting that
fails one is IGNORE and the grader is never asked. The grader answers only
"does this role build hands-on AI experience?", and code turns yes/no into
the rating. Fake Claude replies built from real SDK types (tests/fakes.py).
No API calls.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import json
import unittest

try:
    import fakes
    from test_tracing import TraceTestCase, kind, FINAL
except ImportError:  # when run as tests.test_hard_screens
    from tests import fakes
    from tests.test_tracing import TraceTestCase, kind, FINAL

agent = fakes.agent

JOB = {"company": "Lumen", "role_title": "AI Product Lead",
       "job_description": "Prototype LLM tools hands-on."}
YES = '{"answer": "yes", "reasons": ["Prototypes LLM tools hands-on"]}'
NO = '{"answer": "no", "reasons": ["Manages vendors; no hands-on AI"]}'


def grader(reply):
    """A fake client whose only queued call is the grader's. If evaluate_job
    makes a second call, or any call when none is queued, pop() raises."""
    return fakes.use_fake(outer=[], inner=[fakes.reply(fakes.text(reply))] if reply else [])


class LowestBaseTest(unittest.TestCase):
    """Reading the lowest yearly base from Claude's compensation text."""

    CASES = {
        "$140,000–$165,000 base": 140_000,
        "$200,000-$240,000": 200_000,
        "$185K–$215K": 185_000,
        "180-220k": 180_000,              # the first number borrows the K
        "180 to 220K": 180_000,
        "$175k - $230k plus equity": 175_000,
        "$200,000+": 200_000,
        "$250,000 base, 15% bonus": 250_000,    # the 15 isn't a salary
        "$1.2M": 1_200_000,
        "competitive": None,
        "Unknown": None,
        "": None,
        None: None,
        "$90/hr": None,                   # not a yearly salary: not compared
        "$95–$120 per hour": None,
        "$15,000/month": None,
    }

    def test_each_case(self):
        for text, expected in self.CASES.items():
            with self.subTest(text):
                self.assertEqual(agent.lowest_base(text), expected)


class ScreensTest(unittest.TestCase):
    """hard_screens on its own: a pure function, no API call."""

    def outcome(self, remote, compensation):
        return {s["name"]: (s["caught"], s["skipped"], s["note"])
                for s in agent.hard_screens(remote, compensation)}

    def test_the_rules_are_named_constants(self):
        self.assertEqual(agent.MIN_BASE, 180_000)
        self.assertIs(agent.REQUIRE_REMOTE, True)

    def test_floor_is_inclusive(self):
        self.assertFalse(self.outcome(True, "$180,000–$200,000")["comp_floor"][0])
        self.assertTrue(self.outcome(True, "$179,999–$200,000")["comp_floor"][0])

    def test_only_remote_false_fails_the_remote_screen(self):
        self.assertEqual(self.outcome(False, "$200K")["remote"], (True, False, "not remote"))
        self.assertEqual(self.outcome(True, "$200K")["remote"], (False, False, "remote"))
        for unknown in ("Unknown", None, "hybrid"):
            with self.subTest(unknown):
                caught, skipped, _ = self.outcome(unknown, "$200K")["remote"]
                self.assertEqual((caught, skipped), (False, True))

    def test_unreadable_pay_is_skipped_not_failed(self):
        caught, skipped, note = self.outcome(True, "competitive")["comp_floor"]
        self.assertEqual((caught, skipped), (False, True))
        self.assertIn("comp screen skipped", note)


class AcceptanceTest(TraceTestCase):
    """The acceptance criteria in issue #26, one test each."""

    def test_base_below_floor_is_ignore_with_no_rating_call(self):
        fake = grader(None)                      # no grader reply queued
        result = agent.evaluate_job(**JOB, remote=True,
                                    compensation="$140,000–$165,000 base")
        self.assertEqual(result, {"rating": "IGNORE", "reasons": ["base below $180K floor"]})
        self.assertEqual(fake.inner, [])         # nothing was asked of the grader

    def test_not_remote_is_ignore_with_no_rating_call(self):
        grader(None)
        result = agent.evaluate_job(**JOB, remote=False, compensation="$200,000–$240,000")
        self.assertEqual(result, {"rating": "IGNORE", "reasons": ["not remote"]})

    def test_both_screens_failing_gives_both_reasons(self):
        grader(None)
        result = agent.evaluate_job(**JOB, remote=False, compensation="$120K–$150K")
        self.assertEqual(result["reasons"], ["not remote", "base below $180K floor"])

    def test_remote_200k_and_yes_is_strong(self):
        fake = grader(YES)
        result = agent.evaluate_job(**JOB, remote=True, compensation="$200,000–$240,000")
        self.assertEqual(result, {"rating": "STRONG",
                                  "reasons": ["Prototypes LLM tools hands-on"]})
        self.assertEqual(fake.inner, [])         # the one grader reply was used

    def test_remote_200k_and_no_is_worth_reviewing(self):
        grader(NO)
        result = agent.evaluate_job(**JOB, remote=True, compensation="$200,000–$240,000")
        self.assertEqual(result["rating"], "WORTH REVIEWING")

    def test_competitive_pay_skips_the_comp_screen_and_the_trace_says_so(self):
        evaluate = fakes.tool_use("toolu_1", "evaluate_job",
                                  {**JOB, "remote": True, "compensation": "competitive"})
        final, rec = self.record(
            outer=[fakes.reply(evaluate, stop_reason="tool_use"), fakes.reply(fakes.text(FINAL))],
            inner=[fakes.reply(fakes.text(YES))])
        self.assertEqual(final, FINAL)
        comp = next(e for e in rec.events if kind(e) == ("guard", "comp_floor"))
        self.assertEqual(comp["step_id"], "run_tools")
        self.assertEqual(comp["guard"], {
            "name": "comp_floor", "checked": "lowest base >= MIN_BASE (180000)",
            "value": "competitive", "caught": False, "action": "screen_skipped",
            "message": None})
        # The rating call still happened, after the screens.
        self.assertTrue(any(kind(e) == "inner_api_request" for e in rec.events))
        result = next(e for e in rec.events if kind(e) == "tool_result")
        self.assertEqual(json.loads(result["payload"]["content"])["rating"], "STRONG")

    def test_rating_prompt_no_longer_mentions_salary_or_location(self):
        rubric = agent.RUBRIC.lower()
        for word in ("$", "180", "salary", "base", "pay", "compensation",
                     "remote", "location"):
            with self.subTest(word):
                self.assertNotIn(word, rubric)

    def test_grader_is_not_sent_remote_or_pay_separately(self):
        fake = fakes.FakeClaude(outer=[], inner=[fakes.reply(fakes.text(YES))])
        sent = []
        fake.create = lambda **kwargs: sent.append(kwargs) or fakes.reply(fakes.text(YES))
        agent.client = type("FakeClient", (), {"messages": fake})()
        agent.evaluate_job(**JOB, location="Remote (US)", remote=True,
                           compensation="$200,000–$240,000")
        content = sent[0]["messages"][0]["content"]
        self.assertNotIn("Compensation:", content)
        self.assertNotIn("Remote:", content)
        self.assertIn("Prototype LLM tools hands-on.", content)


class TraceTest(TraceTestCase):
    """What a screened-out posting looks like in the trace (scenario 5)."""

    def screened_out_run(self):
        evaluate = fakes.tool_use("toolu_1", "evaluate_job",
                                  {**JOB, "remote": True, "compensation": "$140,000–$165,000 base"})
        return self.record(
            outer=[fakes.reply(evaluate, stop_reason="tool_use"), fakes.reply(fakes.text(FINAL))],
            inner=[])                            # a rating call would fail the test

    def test_caught_screen_is_recorded_at_hard_screen_inside_the_tool_call(self):
        final, rec = self.screened_out_run()
        self.assertEqual(final, FINAL)
        call = next(e for e in rec.events if kind(e) == "tool_call")
        caught = [e for e in rec.events if e["guard"] and e["guard"]["caught"]]
        self.assertEqual(len(caught), 1)
        guard = caught[0]
        self.assertEqual(guard["step_id"], "hard_screen")
        self.assertEqual(guard["parent"], call["id"])
        self.assertEqual(guard["guard"], {
            "name": "comp_floor", "checked": "lowest base >= MIN_BASE (180000)",
            "value": 140000, "caught": True, "action": "ignore_returned",
            "message": "base below $180K floor"})

    def test_no_grader_events_and_the_result_is_a_normal_tool_result(self):
        _, rec = self.screened_out_run()
        self.assertFalse([e for e in rec.events if e["step_id"] == "inner_grader"])
        result = next(e for e in rec.events if kind(e) == "tool_result")
        self.assertIs(result["payload"]["is_error"], False)
        self.assertEqual(json.loads(result["payload"]["content"]),
                         {"rating": "IGNORE", "reasons": ["base below $180K floor"]})

    def test_passed_screens_are_recorded_uncaught_at_run_tools(self):
        evaluate = fakes.tool_use("toolu_1", "evaluate_job",
                                  {**JOB, "remote": True, "compensation": "$200K–$240K"})
        _, rec = self.record(
            outer=[fakes.reply(evaluate, stop_reason="tool_use"), fakes.reply(fakes.text(FINAL))],
            inner=[fakes.reply(fakes.text(YES))])
        screens = {e["guard"]["name"]: e for e in rec.events
                   if kind(e) in (("guard", "remote"), ("guard", "comp_floor"))}
        self.assertEqual(screens["remote"]["guard"]["value"], True)
        self.assertEqual(screens["comp_floor"]["guard"]["value"], 200000)
        for e in screens.values():
            self.assertEqual(e["step_id"], "run_tools")
            self.assertIs(e["guard"]["caught"], False)
            self.assertIsNone(e["guard"]["action"])


if __name__ == "__main__":
    unittest.main()
