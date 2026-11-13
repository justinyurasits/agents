"""Tests for the page's data and files (#57): steps.json and site/.

No browser here: these check what the page loads. The page's behavior
(playback, the map, the tabs) was checked in a real browser; see the PR.
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

    def test_a_repeated_step_id_is_an_error(self):
        md = "## X\n\n### 1. A\n\nStep id: `a`\n\nText.\nCode: x\n\n### 2. B\n\nStep id: `a`\n\nMore.\nCode: y\n"
        with self.assertRaises(ValueError):
            build_steps.parse_steps(md)


class SiteFilesTest(unittest.TestCase):

    FILES = ["index.html", "style.css", "app.js"]

    def test_the_page_requests_nothing_but_its_own_files(self):
        # No fonts, scripts or data from anywhere else: not even a URL in the source.
        for name in self.FILES:
            with self.subTest(name):
                self.assertIsNone(re.search(r"https?://|//[a-z0-9.-]+\.[a-z]{2,}/", read(os.path.join(SITE, name))))

    def test_every_file_the_page_loads_exists(self):
        html = read(os.path.join(SITE, "index.html"))
        for ref in re.findall(r'(?:src|href)="([^"]+)"', html):
            if ref.startswith("data:"):
                continue
            with self.subTest(ref):
                self.assertTrue(os.path.exists(os.path.join(SITE, ref)))
        app = read(os.path.join(SITE, "app.js"))
        loads = re.findall(r'^const (?:RECORDING|STEPS|SCENARIOS) = "([^"]+)";', app, re.M)
        self.assertEqual(len(loads), 3)
        for ref in loads:
            with self.subTest(ref):
                self.assertTrue(os.path.exists(os.path.normpath(os.path.join(SITE, ref))))

    def test_playback_is_two_and_a_half_seconds_per_step_at_1x(self):
        self.assertIn("const STEP_MS = 2500;", read(os.path.join(SITE, "app.js")))


if __name__ == "__main__":
    unittest.main()
