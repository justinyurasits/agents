"""Docs that must stay in line with the code and the decision log (#62).

Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import json
import os
import re
import unittest

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

    def test_brief_lists_every_scenario_by_name(self):
        scenarios = json.loads(read("scenarios", "scenarios.json"))
        for s in scenarios:
            with self.subTest(s["id"]):
                self.assertIn(f"{s['id']}. **{s['name']}**", BRIEF)


class ScenarioFieldsTest(unittest.TestCase):

    def test_every_scenario_has_a_summary_field(self):
        # The end-of-run card's text; null until Justin writes it (#62).
        for s in json.loads(read("scenarios", "scenarios.json")):
            with self.subTest(s["id"]):
                self.assertIn("summary", s)


if __name__ == "__main__":
    unittest.main()
