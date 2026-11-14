"""Browser tests for the page (#84): the checks that used to be run by hand on
every page PR.

They load site/ in headless Chromium, through Playwright for Python, from a
local http server these tests start, and check all nine scenarios:
  1. Claude's words stay in the "Claude's response" tab (D31).
  2. Every scenario plays from step 1 to its last step without errors.
  3. The URL: an unknown id, picking a scenario, and Back.

Needs Playwright and Chromium (see README, "Browser tests"). Without them the
whole suite is skipped with the reason, and the other tests still run.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import functools
import http.server
import json
import os
import re
import threading
import unittest

try:
    from playwright.sync_api import Error as PlaywrightError, sync_playwright
except ImportError:  # Playwright isn't installed: skip, don't fail
    sync_playwright = None

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENARIOS = json.load(open(os.path.join(HERE, "scenarios", "scenarios.json"), encoding="utf-8"))
PIECE = 30    # characters per piece of Claude's words (the #83 check)
STRIDE = 15   # pieces overlap by half, so a quote that starts mid-piece still matches
# A JavaScript value that leaked into visible text. \b = word boundary.
BROKEN = re.compile(r"\bundefined\b|\bNaN\b|\[object \w+\]")


def recording(n):
    with open(os.path.join(HERE, "recordings", f"scenario-{n:02d}.json"), encoding="utf-8") as f:
        return json.load(f)


def claudes_words(trace):
    """Everything Claude wrote in a run, from the recording itself: its text and
    thinking (main conversation and the grader), its final answer, and the
    grader's real reply where a simulated failure replaced it."""
    words = []
    for e in trace["events"]:
        p = e["payload"]
        if not isinstance(p, dict):
            continue
        if e["actor"] == "claude" and isinstance(p.get("content"), list):
            for b in p["content"]:
                if b["type"] in ("text", "thinking"):
                    words.append(b.get(b["type"]) or "")
        if e["step_id"] == "answer_returned" and isinstance(p.get("text"), str):
            words.append(p["text"])
        if "fault" in p:
            words += [v["real"] for v in p.values() if isinstance(v, dict) and isinstance(v.get("real"), str)]
    return words


def pieces(words):
    """Claude's words as overlapping 30-character pieces, whitespace collapsed
    the way a browser collapses it in visible text."""
    out = set()
    for w in words:
        text = " ".join(w.split())
        out.update(text[k:k + PIECE] for k in range(0, len(text) - PIECE + 1, STRIDE))
    return sorted(out)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # no request log in the test output
        pass


@unittest.skipIf(sync_playwright is None,
                 "Playwright isn't installed: pip install -r requirements-dev.txt (see README, Browser tests)")
class BrowserTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Serve job-evaluator/ so the page can read ../recordings and ../scenarios.
        # Port 0 = any free port. partial() fixes the folder the handler serves.
        handler = functools.partial(QuietHandler, directory=HERE)
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}/site/"
        cls.pw = sync_playwright().start()
        try:
            cls.browser = cls.pw.chromium.launch()
        except PlaywrightError:
            cls.pw.stop()
            cls.server.shutdown()
            raise unittest.SkipTest("Chromium isn't installed for Playwright: python -m playwright install chromium")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()

    def open(self, query=""):
        """A fresh page at site/<query>, collecting console errors and uncaught
        exceptions in self.errors."""
        page = self.browser.new_page(viewport={"width": 1440, "height": 1000})
        self.addCleanup(page.close)
        self.errors = []
        page.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        page.on("pageerror", lambda exc: self.errors.append(str(exc)))
        page.goto(self.base + query)
        return page

    def wait_for_scenario(self, page, n, why=None):
        """Wait until scenario n is loaded; fail (not hang) if it never is."""
        # The page exposes its state as window.explorer for checks like these.
        try:
            page.wait_for_function(
                "n => window.explorer && window.explorer.state.scenario"
                " && window.explorer.state.scenario.id === n && window.explorer.state.steps.length",
                arg=n, timeout=5000)
        except PlaywrightError:
            self.fail(f"{why or 'opening the page'}: scenario {n} never loaded (URL {page.url}, errors {self.errors})")

    def show(self, page, k, where):
        """Show step k (0-based); an error the page throws fails, naming the step."""
        try:
            page.evaluate("k => window.explorer.show(k)", k)
        except PlaywrightError as exc:
            self.fail(f"{where}: the page threw {exc.message.splitlines()[0]}")

    def steps(self, page):
        return page.evaluate("window.explorer.state.steps.length")

    def visible_text(self, page):
        # innerText is only what's rendered: the inspector shows the State
        # change tab, so the Claude's response tab's content isn't in it.
        return " ".join(page.inner_text(".page").split())

    def test_claudes_words_stay_in_their_tab(self):
        # D31: Claude's own words appear only under "Claude's response".
        for sc in SCENARIOS:
            n = sc["id"]
            with self.subTest(scenario=n):
                page = self.open(f"?scenario={n}")
                self.wait_for_scenario(page, n)
                look_for = pieces(claudes_words(recording(n)))
                self.assertTrue(look_for, f"scenario {n}: no words of Claude's found in its recording")
                leaks = []
                for k in range(self.steps(page)):
                    self.show(page, k, f"scenario {n}, step {k + 1}")
                    text = self.visible_text(page)
                    leaks += [f"step {k + 1}: {p!r}" for p in look_for if p in text][:1]
                self.assertEqual(leaks, [], f"scenario {n}: Claude's words outside the Claude's response tab")

    def test_every_scenario_plays_to_the_end(self):
        for sc in SCENARIOS:
            n = sc["id"]
            with self.subTest(scenario=n):
                page = self.open(f"?scenario={n}")
                self.wait_for_scenario(page, n)
                total = self.steps(page)
                for k in range(total):
                    where = f"scenario {n}, step {k + 1} of {total}"
                    self.assertEqual(page.evaluate("window.explorer.state.i"), k, where)
                    broken = BROKEN.search(self.visible_text(page))
                    if broken:
                        self.fail(f"{where}: {broken.group()!r} in visible text")
                    self.assertEqual(self.errors, [], f"{where}: console errors")
                    if k < total - 1:
                        page.click("#next")
                self.assertTrue(page.is_disabled("#next"), f"scenario {n}: Next isn't disabled at the last step")
                self.assertEqual(self.errors, [], f"scenario {n}: console errors")

    def test_unknown_scenario_shows_not_found(self):
        page = self.open("?scenario=42")
        page.wait_for_selector("#load-error", state="visible")
        self.assertIn('no scenario "42"', page.inner_text("#load-error"))
        self.assertTrue(page.is_hidden("#run"))
        self.assertEqual(self.errors, [])

    def test_picking_a_scenario_updates_the_url_and_back_returns(self):
        page = self.open("?scenario=5")
        self.wait_for_scenario(page, 5)
        page.select_option("#scenario", "3")
        self.wait_for_scenario(page, 3, "picking scenario 3 after 5")
        self.assertTrue(page.url.endswith("?scenario=3"), page.url)
        self.assertEqual(page.evaluate("window.explorer.state.i"), 0)
        page.go_back()
        self.wait_for_scenario(page, 5, "Back after picking 3")
        self.assertTrue(page.url.endswith("?scenario=5"), page.url)
        self.assertEqual(page.input_value("#scenario"), "5")
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
