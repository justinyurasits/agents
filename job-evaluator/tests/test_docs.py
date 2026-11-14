"""Docs that must stay in line with the code and the decision log (#62).

Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import json
import os
import re
import unittest

import record

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


AGENT = read("agent.py")
SPEC = read("docs", "SPEC.md")
BRIEF = read("docs", "BRIEF.md")
DECISIONS = read("docs", "DECISIONS.md")


class GuardTableTest(unittest.TestCase):

    def test_spec_guard_table_matches_every_guard_marker(self):
        # "# GUARD (E1 tool_failed): ..." in agent.py  <->  "| E1 `tool_failed` |" in SPEC.md
        in_code = set(re.findall(r"# GUARD \((E\d+) ([a-z_]+)\)", AGENT))
        section = SPEC[SPEC.index("## 5. Guards"):SPEC.index("## 6.")]
        in_spec = set(re.findall(r"\| (E\d+) `([a-z_]+)` \|", section))
        self.assertGreaterEqual(len(in_code), 9)
        self.assertEqual(in_spec, in_code)

    def test_guard_table_holds_only_guards(self):
        # Checks that prevent a failure rather than catch one are "defensive
        # handling", in their own table with no E-step (#62 review).
        section = SPEC[SPEC.index("## 5. Guards"):SPEC.index("## 6.")]
        guards = section[:section.index("### Defensive handling")]
        rows = [line for line in guards.splitlines() if line.startswith("| **")]
        self.assertEqual(len(rows), len(re.findall(r"# GUARD \(E\d+", AGENT)))
        for row in rows:
            self.assertRegex(row, r"\| E\d+ `[a-z_]+` \|")
        defensive = section[section.index("### Defensive handling"):]
        for name in ("Fence stripping", "Find text by type", "Every tool request answered"):
            self.assertIn(f"| **{name}**", defensive)


class BriefTest(unittest.TestCase):

    def test_decided_list_covers_every_approved_decision(self):
        approved = set()
        for number, body in re.findall(r"^## D(\d+) .*?\n(.*?)(?=^## D|\Z)", DECISIONS, re.M | re.S):
            if re.search(r"^\*\*Status:\*\* \*\*Approved\*\*", body, re.M):
                approved.add(int(number))
        decided = BRIEF[BRIEF.index("## Decided"):]
        listed = {int(n) for n in re.findall(r"\bD(\d+)\b", decided)}
        self.assertGreaterEqual(len(approved), 15)
        self.assertEqual(approved - listed, set())

    def test_brief_four_questions_heading_is_distinct_from_design_principles(self):
        self.assertIn("## The four questions (page design rule)", BRIEF)
        self.assertNotIn("## Design principle\n", BRIEF)

    def test_brief_lists_every_scenario_by_name(self):
        scenarios = json.loads(read("scenarios", "scenarios.json"))
        for s in scenarios:
            with self.subTest(s["id"]):
                self.assertIn(f"{s['id']}. **{s['name']}**", BRIEF)


class ScenarioFieldsTest(unittest.TestCase):
    """The page's intro and summary card text, in scenarios.json (#75)."""

    SCENARIOS = json.loads(read("scenarios", "scenarios.json"))
    # Words that give away how a run ends: a rating, a flag, a stop.
    OUTCOME_WORDS = re.compile(r"STRONG|WORTH REVIEWING|IGNORE|flag|stop(?! reason)|rated|rating|cut off|recover|retr(y|ies)",
                               re.IGNORECASE)

    def test_every_scenario_has_setup_watch_for_and_summary_text(self):
        for s in self.SCENARIOS:
            for field in ("setup", "watch_for", "summary"):
                with self.subTest(scenario=s["id"], field=field):
                    self.assertIsInstance(s.get(field), str)
                    self.assertTrue(s[field].strip())

    def test_no_intro_states_the_outcome(self):
        for s in self.SCENARIOS:
            for field in ("setup", "watch_for"):
                with self.subTest(scenario=s["id"], field=field):
                    self.assertIsNone(self.OUTCOME_WORDS.search(s[field]), s[field])

    def test_break_the_agent_intros_say_what_is_simulated(self):
        for s in self.SCENARIOS:
            with self.subTest(s["id"]):
                if s["fault"]:
                    self.assertIn("Simulated:", s["setup"])
                else:
                    self.assertNotIn("Simulated", s["setup"])

    def test_each_summary_names_its_recordings_tools_and_outcome(self):
        # record.actual() is what record.py checks a run against: the tools
        # called, in order, and the outcome. The summary must agree with it.
        words = {"flagged": "flagged", "stopped": "stopped", "no rating": "no rating"}
        others = {"STRONG", "WORTH REVIEWING", "IGNORE", "flagged", "stopped"}
        for s in self.SCENARIOS:
            with self.subTest(s["id"]):
                got = record.actual(json.loads(read("recordings", f"scenario-{s['id']:02d}.json")))
                for tool in got["tools"]:
                    self.assertIn(tool, s["summary"])
                for outcome in got["outcome"]:
                    self.assertIn(words.get(outcome, outcome), s["summary"])
                for wrong in others - set(got["outcome"]):
                    self.assertNotIn(wrong, s["summary"])


if __name__ == "__main__":
    unittest.main()
