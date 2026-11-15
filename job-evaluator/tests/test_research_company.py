"""Tests for research_company and researched pay in evaluate_job (issue #65).

research_company looks up stored demo facts (data/companies.json). When
evaluate_job gets the pay research found, the hard rules use it as usual and
the reasons say it was estimated (D34). Fake Claude replies built from real
SDK types (tests/fakes.py). No API calls.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import glob
import json
import os
import tempfile
import unittest
from unittest import mock

try:
    import fakes
    from test_tracing import TraceTestCase
except ImportError:  # when run as tests.test_research_company
    from tests import fakes
    from tests.test_tracing import TraceTestCase

agent = fakes.agent

YES = '{"answer": "yes", "reasons": ["Builds agents hands-on"]}'
DONE = "Done."
NOTE = "base estimated from stored company data"

MARROWSTONE = {"company": "Marrowstone Logistics", "role_level": "Principal Product Manager"}
# What Claude #1 sends evaluate_job after researching: the posting's facts,
# with the researched pay as compensation.
EVAL_RESEARCHED = {"company": "Marrowstone Logistics",
                   "role_title": "Principal Product Manager, Agentic Operations",
                   "job_description": "Build agents for freight operations.", "remote": True,
                   "compensation": "$200,000–$235,000 base"}


def tool_turn(tool_id, name, tool_input):
    return fakes.reply(fakes.tool_use(tool_id, name, tool_input), stop_reason="tool_use")


def results(rec):
    """Every tool result in the trace: (tool, content as a dict or text, is_error)."""
    out = []
    for e in rec.events:
        p = e["payload"]
        if e["step_id"] == "run_tools" and isinstance(p, dict) and "is_error" in p:
            content = p["content"] if p["is_error"] else json.loads(p["content"])
            out.append((p["tool"], content, p["is_error"]))
    return out


class LookupTest(unittest.TestCase):
    """research_company on its own."""

    def setUp(self):
        quiet = mock.patch("builtins.print")
        quiet.start()
        self.addCleanup(quiet.stop)

    def test_known_company_returns_its_facts_from_stored_demo_data(self):
        result = agent.research_company(**MARROWSTONE)
        self.assertIs(result["found"], True)
        self.assertEqual(result["source"], "stored demo data")
        self.assertEqual(result["company"], "Marrowstone Logistics")
        self.assertEqual(result["size"], "About 600 employees")
        self.assertEqual(result["stage"], "Series C, profitable operations business")
        self.assertEqual(result["typical_base_for_level"], "$200,000–$235,000 base")

    def test_company_name_is_matched_ignoring_case_and_spaces(self):
        result = agent.research_company("  marrowstone LOGISTICS ", "principal")
        self.assertIs(result["found"], True)
        self.assertEqual(result["company"], "Marrowstone Logistics")

    def test_unknown_company_is_found_false_not_an_error(self):
        self.assertEqual(agent.research_company("Wrenfield Health", "Senior Product Manager"),
                         {"found": False, "source": "stored demo data"})

    def test_level_not_on_file_gives_no_pay_and_lists_the_levels(self):
        result = agent.research_company("Marrowstone Logistics", "Director of Product")
        self.assertIs(result["found"], True)
        self.assertIsNone(result["typical_base_for_level"])
        self.assertEqual(result["levels_on_file"], ["principal"])

    def test_the_file_is_not_a_company(self):
        self.assertIs(agent.research_company("_about", "principal")["found"], False)


class RunTest(TraceTestCase):
    """research_company inside a real run of the loop."""

    def test_unknown_company_the_run_carries_on_with_no_error_and_no_caught_guard(self):
        unknown = {"company": "Wrenfield Health", "role_level": "Senior Product Manager"}
        flag = {"company": "Wrenfield Health", "role_title": "Senior PM",
                "missing_info": "compensation"}
        final, rec = self.record(outer=[tool_turn("toolu_1", "research_company", unknown),
                                        tool_turn("toolu_2", "flag_for_review", flag),
                                        fakes.reply(fakes.text(DONE))])
        self.assertEqual(final, DONE)
        self.assertEqual(results(rec)[0], ("research_company",
                                           {"found": False, "source": "stored demo data"}, False))
        self.assertEqual([t for t, _, _ in results(rec)], ["research_company", "flag_for_review"])
        self.assertEqual([e for e in rec.events if e["guard"] and e["guard"]["caught"]], [])
        self.assertEqual(rec.result["ended_by"], "end_turn")

    def test_researched_pay_above_the_floor_says_it_was_estimated(self):
        final, rec = self.record(outer=[tool_turn("toolu_1", "research_company", MARROWSTONE),
                                        tool_turn("toolu_2", "evaluate_job", EVAL_RESEARCHED),
                                        fakes.reply(fakes.text(DONE))],
                                 inner=[fakes.reply(fakes.text(YES))])
        tool, rating, is_error = results(rec)[1]
        self.assertEqual((tool, is_error), ("evaluate_job", False))
        self.assertEqual(rating["rating"], "STRONG")
        self.assertIn(NOTE, rating["reasons"])
        self.assertIn("Builds agents hands-on", rating["reasons"])
        comp = next(e for e in rec.events if e["step_id"] == "hard_screen"
                    and e["payload"]["rule"] == "comp_floor")
        self.assertEqual((comp["payload"]["value"], comp["payload"]["outcome"]), (200000, "passed"))

    def test_researched_pay_is_used_when_claude_sends_no_pay(self):
        no_pay = {k: v for k, v in EVAL_RESEARCHED.items() if k != "compensation"}
        _, rec = self.record(outer=[tool_turn("toolu_1", "research_company", MARROWSTONE),
                                    tool_turn("toolu_2", "evaluate_job", no_pay),
                                    fakes.reply(fakes.text(DONE))],
                             inner=[fakes.reply(fakes.text(YES))])
        self.assertIn(NOTE, results(rec)[1][1]["reasons"])

    def test_researched_pay_below_the_floor_is_ignore_from_the_hard_rule_with_no_rating_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "companies.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"Lowpay Labs": {"size": "12 people", "stage": "Seed",
                                           "typical_base_by_level": {"senior": "$140,000–$160,000 base"}}}, f)
            low = {"company": "Lowpay Labs", "role_title": "Senior PM",
                   "job_description": "Build agents.", "remote": True,
                   "compensation": "$140,000–$160,000 base"}
            with mock.patch.object(agent, "COMPANIES_FILE", path):
                # inner=[]: a rating call would find nothing queued and fail.
                fake = fakes.use_fake(outer=[], inner=[])
                fake.outer = [tool_turn("toolu_1", "research_company",
                                        {"company": "Lowpay Labs", "role_level": "Senior PM"}),
                              tool_turn("toolu_2", "evaluate_job", low),
                              fakes.reply(fakes.text(DONE))]
                rec = agent.tracing.Recorder(scenario="test", git=("abc1234", False))
                agent.run_agent("a posting", recorder=rec)
        tool, rating, is_error = results(rec)[1]
        self.assertEqual((tool, is_error), ("evaluate_job", False))
        self.assertEqual(rating, {"rating": "IGNORE", "reasons": ["base below $180K floor", NOTE]})
        self.assertEqual([e for e in rec.events if e["step_id"] == "inner_grader"], [])

    def test_research_on_another_company_does_not_make_this_pay_estimated(self):
        # Same pay, different company: only research on this company counts.
        fakes.use_fake(outer=[], inner=[fakes.reply(fakes.text(YES))])
        other = dict(EVAL_RESEARCHED, company="Northwind Labs")
        rating = agent.evaluate_job(**other, researched_pay={
            "marrowstone logistics": "$200,000–$235,000 base"})
        self.assertEqual(rating["rating"], "STRONG")
        self.assertNotIn(NOTE, rating["reasons"])

    def test_different_pay_than_research_found_is_not_called_estimated(self):
        listed = dict(EVAL_RESEARCHED, compensation="$250,000 base")
        _, rec = self.record(outer=[tool_turn("toolu_1", "research_company", MARROWSTONE),
                                    tool_turn("toolu_2", "evaluate_job", listed),
                                    fakes.reply(fakes.text(DONE))],
                             inner=[fakes.reply(fakes.text(YES))])
        self.assertIs(results(rec)[0][1]["found"], True)
        self.assertNotIn(NOTE, results(rec)[1][1]["reasons"])

    def test_the_lookup_is_a_traced_step_inside_its_tool_call(self):
        _, rec = self.record(outer=[tool_turn("toolu_1", "research_company", MARROWSTONE),
                                    fakes.reply(fakes.text(DONE))])
        call = next(e for e in rec.events if e["crossing"] and e["crossing"]["kind"] == "tool_call")
        lookup = next(e for e in rec.events if e["step_id"] == "research_company")
        self.assertEqual(lookup["parent"], call["id"])
        self.assertEqual(lookup["actor"], "tool")
        self.assertEqual(lookup["payload"], {"company": "Marrowstone Logistics",
                                             "role_level": "Principal Product Manager",
                                             "found": True,
                                             "typical_base_for_level": "$200,000–$235,000 base",
                                             "source": "stored demo data"})
        self.assertEqual(lookup["code"]["marker"], "research_company")



class PrecedenceTest(unittest.TestCase):
    """#91, D42: the tool that should wait says so in its own description."""

    SENTENCE = "If compensation is missing, try research_company first; flag only if research finds no pay."

    def description(self, name):
        return next(t["description"] for t in agent.tools if t["name"] == name)

    def test_flag_for_review_says_to_research_first(self):
        self.assertTrue(self.description("flag_for_review").endswith(" " + self.SENTENCE))

    def test_research_companys_description_is_unchanged(self):
        self.assertEqual(self.description("research_company"),
                         "Look up stored facts about a company: size, stage, and typical base "
                         "pay for a role level. Use when a posting doesn't list compensation.")

    def test_every_recording_shows_the_description_claude_now_gets(self):
        # Recordings store the tools they offered; re-recorded in #91.
        for path in sorted(glob.glob(os.path.join(os.path.dirname(agent.__file__), "recordings", "*.json"))):
            with self.subTest(os.path.basename(path)):
                with open(path, encoding="utf-8") as f:
                    recorded = {t["name"]: t["description"] for t in json.load(f)["tools"]}
                self.assertEqual(recorded["flag_for_review"], self.description("flag_for_review"))


if __name__ == "__main__":
    unittest.main()
