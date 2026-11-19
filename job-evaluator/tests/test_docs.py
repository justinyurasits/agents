"""Docs that must stay in line with the code and the decision log (#62).

Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import html
import json
import os
import re
import unittest

import record
from design_repo import COMPONENT, design_doc, read_design

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


AGENT = read("agent.py")
# The design docs are in the design repo (#125): design.md holds the spec
# part and the decision log, split at "# Decision log"; then the brief.
SPEC, DECISIONS = design_doc()
BRIEF = read_design(*COMPONENT, "brief.md")


class GuardTableTest(unittest.TestCase):

    def test_spec_guard_table_matches_every_guard_marker(self):
        # "# GUARD (E1 tool_failed): ..." in agent.py  <->  "| E1 `tool_failed` |" in design.md
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

    def test_every_decision_has_its_own_id(self):
        # Each "## D…" heading is a number with an optional letter (D11a), and
        # no two share one. Two "## D11" entries made a reference to D11
        # ambiguous (#93).
        headings = re.findall(r"^## (D\S*) ", DECISIONS, re.M)
        self.assertGreaterEqual(len(headings), 40)
        self.assertEqual([h for h in headings if not re.fullmatch(r"D\d+[a-z]?", h)], [], "malformed ids")
        self.assertEqual(sorted({h for h in headings if headings.count(h) > 1}), [], "ids used twice")

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

    @staticmethod
    def page_section():
        return BRIEF.split("## What's on the page", 1)[1].split("\n## ", 1)[0]

    def test_brief_sections_match_the_page_nav_in_order(self):
        # BRIEF's eight sections are named the way the page's header bar names
        # them (#82): the nav's home link, then each section link.
        nav = re.search(r'<nav class="nav".*?</nav>', read("site", "index.html"), re.S).group()
        labels = [re.sub(r"<[^>]+>", "", t).strip() for t in re.findall(r"<a [^>]*>(.*?)</a>", nav)]
        listed = re.findall(r"^\d+\. \*\*(.+?)\*\*", self.page_section(), re.M)
        self.assertEqual(len(listed), 8)
        self.assertEqual(listed, [html.unescape(l) for l in labels])

    def test_brief_principles_match_specs_table(self):
        # The same seven principles, in order, with the same Watch it scenarios.
        brief = [(name, [int(n) for n in re.findall(r"\d+", watch)])
                 for name, watch in re.findall(r"^   \d+\. (.+) \((scenarios? [^)]*)\)$", self.page_section(), re.M)]
        table = SPEC.split("## Design principles", 1)[1].split("\n---\n", 1)[0]
        # Four-column rows only: principle | in this agent | guards | Watch it.
        # (The section also holds leftover three-column rows of the old table: #94.)
        rows = re.findall(r"^\| \*\*(.+?)\*\* \| [^|]+ \| [^|]+ \| ([^|]+) \|$", table, re.M)
        spec = [(name, [int(n) for n in re.findall(r"\d+", watch.split(":")[0])]) for name, watch in rows]
        self.assertEqual(len(brief), 7)
        self.assertEqual(brief, spec)

    def test_brief_has_no_guardrails_section_or_six_principles(self):
        # D36 dropped the Guardrails section; #80 made the principles seven.
        self.assertNotRegex(BRIEF, r"(?i)guardrail")
        self.assertNotRegex(BRIEF, r"(?i)\bsix (principles|sections)\b")

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
