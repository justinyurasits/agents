"""Tests for the page's data and files (#57): steps.json and site/.

No browser here: these check what the page loads. The page's behavior in a
real browser is tested in test_browser.py (#84).
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import glob
import json
import os
import re
import unittest

import build_steps
import code_refs

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(HERE, "site")
REPO_ROOT = os.path.dirname(HERE)
# The one outside address the page may name, in an <a href> link only (#81):
# this repo on GitHub. Links aren't requests; the page still loads nothing else.
REPO_URL = "https://github.com/justinyurasits/agents"
REPO_LINK = re.compile(r'<a href="' + re.escape(REPO_URL) + r'(/blob/main/[\w./-]+)?">')


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class StepsJsonTest(unittest.TestCase):

    def test_committed_steps_json_matches_steps_md(self):
        # Fails if STEPS.md was edited without rerunning build_steps.py.
        self.assertEqual(read(build_steps.STEPS_JSON), build_steps.render(read(build_steps.STEPS_MD)))

    def test_editing_a_step_in_steps_md_changes_its_text(self):
        md = read(build_steps.STEPS_MD)
        old = "A tool raised an error instead of returning a result."
        self.assertIn(old, md)
        edited = build_steps.build(md.replace(old, "EDITED: the tool broke."))
        self.assertTrue(edited["steps"]["tool_failed"]["text"].startswith("EDITED: the tool broke."))
        self.assertEqual(edited["steps"]["run_tools"], build_steps.build(md)["steps"]["run_tools"])

    def test_a_step_reads_title_number_text_and_kind(self):
        steps = build_steps.parse_steps(read(build_steps.STEPS_MD))
        self.assertEqual(steps["hard_screen"]["number"], "7a")
        self.assertEqual(steps["hard_screen"]["title"], "Inside evaluate_job: code checks your hard rules")
        self.assertFalse(steps["hard_screen"]["error"])
        self.assertEqual(steps["tool_failed"]["number"], "E1")
        self.assertTrue(steps["tool_failed"]["error"])
        # The "Code:" line is for developers, not the page.
        for step in steps.values():
            self.assertNotIn("Code:", step["text"])
            self.assertNotIn("# STEP:", step["text"])
            self.assertTrue(step["text"])

    def test_every_step_in_the_code_and_every_recorded_step_has_an_explanation(self):
        steps = build_steps.parse_steps(read(build_steps.STEPS_MD))
        markers = set(code_refs.find_markers(code_refs.load_source()))
        needed = markers | code_refs.NO_CODE | set(code_refs.SHARED)
        for path in glob.glob(os.path.join(HERE, "recordings", "*.json")):
            needed |= {e["step_id"] for e in json.loads(read(path))["events"]}
        self.assertEqual(needed - set(steps), set())

    def test_every_guard_has_a_one_line_check(self):
        # A passing check isn't a step: the page shows this line instead (#57 review).
        checks = build_steps.parse_checks(read(build_steps.STEPS_MD))
        names = set(re.findall(r'self\.guard\("[a-z_]+", "([a-z_]+)"', read(os.path.join(HERE, "tracing.py"))))
        for path in glob.glob(os.path.join(HERE, "recordings", "*.json")):
            names |= {e["guard"]["name"] for e in json.loads(read(path))["events"] if e["guard"]}
        self.assertGreaterEqual(len(names), 9)
        self.assertEqual(names - set(checks), set())
        self.assertEqual(checks["pass_count"], "Checks this run hasn't hit the 10-pass limit.")

    def test_the_checks_section_is_not_read_as_a_step(self):
        steps = build_steps.parse_steps(read(build_steps.STEPS_MD))
        self.assertNotIn("pass_count", steps["unexpected_stop"]["text"])

    def test_a_repeated_step_id_is_an_error(self):
        md = "## X\n\n### 1. A\n\nStep id: `a`\n\nText.\nCode: x\n\n### 2. B\n\nStep id: `a`\n\nMore.\nCode: y\n"
        with self.assertRaises(ValueError):
            build_steps.parse_steps(md)


class SiteFilesTest(unittest.TestCase):

    FILES = ["index.html", "style.css", "app.js"]

    def test_the_page_requests_nothing_but_its_own_files(self):
        # No fonts, scripts or data from anywhere else: not even a URL in the
        # source, apart from <a href> links to this repo on GitHub (#81).
        for name in self.FILES:
            with self.subTest(name):
                text = REPO_LINK.sub("<a>", read(os.path.join(SITE, name)))
                self.assertIsNone(re.search(r"https?://|//[a-z0-9.-]+\.[a-z]{2,}/", text))

    def test_every_github_link_points_at_a_file_in_this_repo(self):
        links = REPO_LINK.findall(read(os.path.join(SITE, "index.html")))
        self.assertGreaterEqual(len(links), 5)
        for path in links:
            with self.subTest(path or "the repo"):
                if path:
                    self.assertTrue(os.path.isfile(os.path.join(REPO_ROOT, path[len("/blob/main/"):])), path)

    def test_every_file_the_page_loads_exists(self):
        html = read(os.path.join(SITE, "index.html"))
        for ref in re.findall(r'(?:src|href)="([^"]+)"', html):
            if ref.startswith("data:"):
                continue
            if ref.startswith(REPO_URL):   # a link to this repo: checked in the test above (#81)
                continue
            if ref.startswith("#"):   # a link within the page: the id must exist (#78)
                with self.subTest(ref):
                    self.assertIn(f'id="{ref[1:]}"', html)
                continue
            with self.subTest(ref):
                self.assertTrue(os.path.exists(os.path.join(SITE, ref)))
        for ref in re.findall(r'url\("([^"]+)"\)', read(os.path.join(SITE, "style.css"))):
            with self.subTest(ref):
                self.assertTrue(os.path.exists(os.path.join(SITE, ref)))
        app = read(os.path.join(SITE, "app.js"))
        loads = re.findall(r'^const (?:RECORDING_DIR|STEPS|SCENARIOS|NUMBERS) = "([^"]+)";', app, re.M)
        self.assertEqual(len(loads), 4)
        for ref in loads:
            with self.subTest(ref):
                self.assertTrue(os.path.exists(os.path.normpath(os.path.join(SITE, ref))))

    def test_every_scenario_in_the_chooser_has_a_recording(self):
        # The page loads recordings/scenario-0N.json for scenario N (#71).
        scenarios = json.loads(read(os.path.join(HERE, "scenarios", "scenarios.json")))
        self.assertEqual(len(scenarios), 9)
        for sc in scenarios:
            with self.subTest(sc["id"]):
                path = os.path.join(HERE, "recordings", f"scenario-{sc['id']:02d}.json")
                self.assertTrue(os.path.exists(path))
                self.assertEqual(json.loads(read(path))["scenario"], f"scenario-{sc['id']}")

    def test_the_chooser_groups_are_the_scenario_groups_in_d21_order(self):
        # app.js names the groups; every scenario must be in one of them.
        app = read(os.path.join(SITE, "app.js"))
        groups = re.findall(r'\["([a-z]+)", "[^"]+"\]', re.search(r"^const GROUPS = (.*);$", app, re.M).group(1))
        self.assertEqual(groups, ["normal", "break"])
        scenarios = json.loads(read(os.path.join(HERE, "scenarios", "scenarios.json")))
        self.assertEqual({sc["group"] for sc in scenarios}, set(groups))
        # D21: the five normal runs come before the four break-the-agent runs.
        self.assertEqual([sc["group"] for sc in scenarios], ["normal"] * 5 + ["break"] * 4)

    def test_playback_is_two_and_a_half_seconds_per_step_at_1x(self):
        self.assertIn("const STEP_MS = 2500;", read(os.path.join(SITE, "app.js")))


class PageStructureTest(unittest.TestCase):
    """The eight sections and the tool names on the page (#78, D36)."""

    SECTIONS = ["hero", "what-is-an-agent", "how-it-works", "scenarios", "run-view",
                "principles", "how-it-was-built", "footer"]
    HTML = read(os.path.join(SITE, "index.html"))
    APP = read(os.path.join(SITE, "app.js"))

    @staticmethod
    def agent_tools():
        import agent   # here, not at the top: the other tests in this file don't need it
        return [t["name"] for t in agent.tools]

    def test_the_eight_sections_are_in_order(self):
        ids = re.findall(r'<(?:header|section|footer)[^>]* id="([a-z-]+)"', self.HTML)
        self.assertEqual([i for i in ids if i in self.SECTIONS], self.SECTIONS)

    def test_the_nav_links_to_each_section_in_order(self):
        nav = re.search(r'<nav class="nav".*?</nav>', self.HTML, re.S).group()
        self.assertEqual(re.findall(r'href="#([a-z-]+)"', nav), self.SECTIONS)

    def test_the_page_names_only_tools_in_agent_py(self):
        # Every snake_case word in the page's text must be a tool in agent.py,
        # a step id, a guard name, a name in agent.py's code (is_error,
        # hard_screens), or a test file or test name (#80's "Tested, not
        # demonstrated"). A renamed or invented tool fails here.
        known = set(self.agent_tools())
        md = read(build_steps.STEPS_MD)
        known |= set(build_steps.parse_steps(md)) | set(build_steps.parse_checks(md))
        known |= set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", read(os.path.join(HERE, "agent.py"))))
        known |= {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(HERE, "*.py"))}   # build_numbers
        for path in glob.glob(os.path.join(HERE, "tests", "test_*.py")):
            known.add(os.path.basename(path)[:-3])
            known |= set(re.findall(r"^\s*def (test_\w+)", read(path), re.M))
        self.assertNotIn("rate_posting", known, "the made-up tool from scenario 7 must still fail this test")
        text = re.sub(r"<[^>]+>", " ", re.sub(r"<!--.*?-->", " ", self.HTML, flags=re.S))
        words = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", text))
        self.assertTrue(words, "expected tool names in the page text")
        self.assertEqual(words - known, set())
        for name in re.findall(r'<code class="tool">([^<]+)</code>', self.HTML):
            with self.subTest(name):
                self.assertIn(name, self.agent_tools())

    def test_every_tool_has_a_line_and_every_line_is_a_tool(self):
        block = re.search(r"^const TOOL_LINES = \{(.*?)^\};", self.APP, re.M | re.S).group(1)
        self.assertEqual(sorted(re.findall(r"^\s*([a-z_]+):", block, re.M)), sorted(self.agent_tools()))

    def test_the_recordings_offer_exactly_agent_pys_tools(self):
        # The page lists the tools from a recording's first request, so the
        # recordings must match the code.
        for path in sorted(glob.glob(os.path.join(HERE, "recordings", "*.json"))):
            with self.subTest(os.path.basename(path)):
                events = json.loads(read(path))["events"]
                first = next(e for e in events if e["crossing"] and e["crossing"]["kind"] == "api_request")
                self.assertEqual(first["payload"]["tools"], self.agent_tools())



class NumbersTest(unittest.TestCase):
    """How it was built (#81): every number shown comes from build_numbers.py."""

    HTML = read(os.path.join(SITE, "index.html"))

    def test_committed_numbers_json_matches_the_repo(self):
        # Fails when a PR changes a count (a test, a decision, a merge) without
        # rerunning build_numbers.py (or build_steps.py, which runs it).
        import build_numbers
        self.assertEqual(json.loads(read(build_numbers.NUMBERS_JSON)), build_numbers.build())

    def test_every_number_slot_names_a_number_in_the_file(self):
        import build_numbers
        numbers = json.loads(read(build_numbers.NUMBERS_JSON))
        slots = re.findall(r'data-number="([a-z_.]+)"', self.HTML)
        self.assertEqual(len(slots), 10)
        for slot in slots:
            with self.subTest(slot):
                value = numbers
                for key in slot.split("."):
                    value = value[key]
                self.assertIsInstance(value, int)

    def test_no_number_is_typed_into_the_section(self):
        # Digits in How it was built may only come from numbers.json.
        section = re.search(r'<section[^>]* id="how-it-was-built".*?</section>', self.HTML, re.S).group()
        text = re.sub(r"<!--.*?-->", "", section, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        self.assertEqual(re.findall(r"\d+", text), [])


class PrinciplesTest(unittest.TestCase):
    """The Design principles table (#80): the page and SPEC agree, every guard
    is under a principle, and every claim it makes is checked."""

    HTML = read(os.path.join(SITE, "index.html"))
    SPEC = read(os.path.join(HERE, "docs", "SPEC.md"))
    STEPS = build_steps.parse_steps(read(build_steps.STEPS_MD))

    def page_rows(self):
        """[(principle, [guard step ids], [Watch it scenarios]), ...] from the page."""
        section = re.search(r'<section[^>]* id="principles".*?</section>', self.HTML, re.S).group()
        rows = re.findall(r"<tr>\s*<th scope=\"row\"[^>]*>(.*?)</th>(.*?)</tr>", section, re.S)
        out = []
        for name, rest in rows:
            feature, watch = rest.split('<td class="principle-watch">')
            out.append((name, re.findall(r'data-guard="([a-z_]+)"', feature),
                        [int(n) for n in re.findall(r'data-scenario="(\d+)"', watch)]))
        return out

    def spec_rows(self):
        """The same, from SPEC's Design principles table."""
        table = self.SPEC.split("## Design principles", 1)[1].split("\n---\n", 1)[0]   # up to the section's rule
        out = []
        for line in table.splitlines():
            m = re.match(r"\| \*\*(.+?)\*\* \| .*? \| (.*?) \| (.*?) \|$", line)
            if m:
                guards = re.findall(r"E\d+ `([a-z_]+)`", m.group(2))
                watch = [int(n) for n in re.findall(r"\d+", m.group(3).split(":")[0])]
                out.append((m.group(1), guards, watch))
        return out

    def test_spec_principles_section_holds_only_the_seven_row_table(self):
        # Every table line in the section must be the header, its separator, or
        # one of the seven four-column rows. Rows the parser skipped hid the old
        # table's leftovers (#94).
        table = self.SPEC.split("## Design principles", 1)[1].split("\n---\n", 1)[0]
        lines = [line for line in table.splitlines() if "|" in line]
        self.assertEqual(lines[0], "| Principle | In this agent | Guards | Watch it |")
        self.assertEqual(lines[1], "|---|---|---|---|")
        rows = lines[2:]
        four_columns = re.compile(r"^\| \*\*[^*]+\*\* \| [^|]+ \| [^|]+ \| [^|]+ \|$")
        self.assertEqual([r for r in rows if not four_columns.match(r)], [], "lines that aren't a principle row")
        self.assertEqual(len(rows), 7)

    def test_the_page_and_spec_list_the_same_seven_principles(self):
        page, spec = self.page_rows(), self.spec_rows()
        self.assertEqual(len(page), 7)
        self.assertEqual([r[0] for r in page], [r[0] for r in spec])
        for (name, guards, watch), (_, spec_guards, spec_watch) in zip(page, spec):
            with self.subTest(name):
                self.assertEqual(guards, spec_guards, "guards")
                self.assertEqual(watch, spec_watch, "Watch it scenarios")

    def test_every_guard_is_under_exactly_one_principle(self):
        guards = [g for _, gs, _ in self.page_rows() for g in gs]
        e_steps = {sid for sid, step in self.STEPS.items() if step["error"]}
        self.assertEqual(len(e_steps), 9)
        self.assertEqual(sorted(guards), sorted(e_steps), "each E-step in STEPS.md once")

    def test_a_demonstrated_guard_is_caught_in_its_scenario(self):
        # "Watch it (6)" next to E1 is a claim: scenario 6's recording must
        # have that guard catching something.
        for step, n in re.findall(r'<li data-guard="([a-z_]+)" data-scenario="(\d+)">', self.HTML):
            with self.subTest(guard=step, scenario=n):
                events = json.loads(read(os.path.join(HERE, "recordings", f"scenario-{int(n):02d}.json")))["events"]
                self.assertTrue(any(e["step_id"] == step and e["guard"] and e["guard"]["caught"] for e in events),
                                f"{step} isn't caught in scenario {n}'s recording")

    def test_a_tested_guard_names_a_test_that_exists(self):
        tested = re.findall(r'<li data-guard="([a-z_]+)">.*?<code>tests/([a-z_]+\.py)</code> · <code>(\w+)</code>',
                            self.HTML)
        self.assertEqual(len(tested), 5)
        for step, file, name in tested:
            with self.subTest(guard=step):
                source = read(os.path.join(HERE, "tests", file))
                self.assertTrue(re.search(rf"^\s*(class|def) {name}\b", source, re.M), f"{name} isn't in tests/{file}")

    def test_every_guard_is_demonstrated_or_tested(self):
        items = re.findall(r'<li data-guard="([a-z_]+)"[^>]*>(.*?)</li>', self.HTML, re.S)
        self.assertEqual(len(items), 9)
        for step, body in items:
            with self.subTest(step):
                self.assertTrue(("Watch it (" in body) != ("Tested, not demonstrated" in body))

    def test_every_decision_cited_exists(self):
        section = re.search(r'<section[^>]* id="principles".*?</section>', self.HTML, re.S).group()
        decisions = set(re.findall(r"^## (D\d+) ", read(os.path.join(HERE, "docs", "DECISIONS.md")), re.M))
        cited = set(re.findall(r"\bD\d+\b", section))
        self.assertTrue(cited)
        self.assertEqual(cited - decisions, set())


if __name__ == "__main__":
    unittest.main()
