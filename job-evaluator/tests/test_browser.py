"""Browser tests for the page (#84): the checks that used to be run by hand on
every page PR.

They load site/ in headless Chromium, through Playwright for Python, from a
local http server these tests start, and check all nine scenarios:
  1. Claude's words stay in the "Claude's response" tab (D31): searched in
     the State change, Code and Payload tabs at every step (D38).
  2. Every scenario plays from step 1 to its last step without errors.
  3. The URL: an unknown id, picking a scenario, and Back.
  4. The page structure (#78): the nav reaches each section, "Watch it run"
     and the "Watch it" buttons reach the run, and the page fits a phone.
  5. The scenario cards (#79): grouped and in order, each card's tool path
     matches its recording, and clicking one loads its run.
  6. Design principles (#80): every Watch it loads its scenario, and guard
     names come from steps.json.
  7. How it was built (#81): every number shown is the one in numbers.json.

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


def collapse(text):
    """Whitespace runs as one space, the way a browser shows visible text."""
    return " ".join(text.split())


def as_json(text):
    """text as it appears inside a JSON string on the Payload tab: quotes and
    newlines escaped. [1:-1] drops json.dumps's surrounding quotes."""
    return json.dumps(text, ensure_ascii=False)[1:-1]


def pieces(words):
    """Claude's words as overlapping 30-character pieces, both as written and
    as they'd appear inside Payload's JSON (escaped), whitespace collapsed."""
    out = set()
    for w in words:
        for text in (collapse(w), collapse(as_json(w))):
            out.update(text[k:k + PIECE] for k in range(0, len(text) - PIECE + 1, STRIDE))
    return sorted(out)


def given_to_claude(trace):
    """Text in the recording that isn't Claude's own, though Claude may repeat
    it: the posting, what Python sends Claude (system prompt, tool
    definitions, user messages other than tool results), and the arguments of
    Claude's tool requests, which D31 treats as data. A piece of Claude's
    words that also appears here proves nothing, so it isn't searched for."""
    texts = []

    def strings(value):
        if isinstance(value, str):
            texts.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                strings(v)
        elif isinstance(value, list):
            for v in value:
                strings(v)

    for e in trace["events"]:
        p = e["payload"]
        if not isinstance(p, dict):
            continue
        kind = (e["crossing"] or {}).get("kind")
        if e["step_id"] == "agent_starts":
            strings(p)
        if kind in ("api_request", "inner_api_request"):
            strings(p.get("system"))
            strings(p.get("tools"))
            for m in p.get("messages", []):
                if m["role"] == "user" and isinstance(m["content"], str):
                    texts.append(m["content"])
        if kind == "tool_call":
            strings(p.get("arguments"))
        if e["actor"] == "claude" and isinstance(p.get("content"), list):
            strings([b.get("input") for b in p["content"] if b["type"] == "tool_use"])
    return [form for t in texts for form in (collapse(t), collapse(as_json(t)))]


def tool_results(trace):
    """The content of every tool_result in the recording, as it appears in
    Payload's JSON. The one exemption (D38): a tool's result is data, even
    when it carries the grader's reasons inside evaluate_job's rating."""
    found = []

    def walk(value):
        if isinstance(value, dict):
            if "tool_use_id" in value and isinstance(value.get("content"), str):
                found.append(collapse(as_json(value["content"])))
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    for e in trace["events"]:
        walk(e["payload"])
    return sorted(set(found), key=len, reverse=True)   # longest first, so none is cut by a shorter one


def tool_path(trace):
    """A run's tool path, worked out here from the recording, independently of
    the page: one group per pass, tools in a pass joined with " + ", passes
    with " → ", and " → error" after a tool that failed."""
    passes = {}
    for e in trace["events"]:
        p = e["payload"]
        if e["step_id"] == "run_tools" and isinstance(p, dict) and "is_error" in p:
            passes.setdefault(e["pass"], []).append(p["tool"] + (" → error" if p["is_error"] else ""))
    return " → ".join(" + ".join(tools) for _, tools in sorted(passes.items())) or "no tools called"


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

    def open(self, query="", width=1440):
        """A fresh page at site/<query>, collecting console errors and uncaught
        exceptions in self.errors. Reduced motion, so links jump instead of
        scrolling smoothly and positions can be read straight away."""
        page = self.browser.new_page(viewport={"width": width, "height": 1000}, reduced_motion="reduce")
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
        # innerText is only what's rendered: the inspector shows one tab at a
        # time, so only that tab's content is in it.
        return collapse(page.inner_text(".page"))

    # The tabs searched for Claude's words: every tab but "Claude's response".
    TABS = {"state": "State change", "code": "Code", "payload": "Payload"}

    def test_the_recordings_have_claudes_words_to_search_for(self):
        # Guards the check below: if the extractor ever finds nothing, that
        # check would pass without searching. A single scenario can have none
        # (#91: scenario 9's reply was cut off inside a tool request, before
        # any text), but most have plenty.
        found = [sc["id"] for sc in SCENARIOS if pieces(claudes_words(recording(sc["id"])))]
        self.assertGreaterEqual(len(found), 7, f"Claude's words found only in scenarios {found}")

    def test_claudes_words_stay_in_their_tab(self):
        # D31: Claude's own words appear only under "Claude's response".
        for sc in SCENARIOS:
            n = sc["id"]
            with self.subTest(scenario=n):
                page = self.open(f"?scenario={n}")
                self.wait_for_scenario(page, n)
                trace = recording(n)
                given = given_to_claude(trace)
                look_for = [p for p in pieces(claudes_words(trace)) if not any(p in g for g in given)]
                exempt = tool_results(trace)
                leaks = []
                for k in range(self.steps(page)):
                    self.show(page, k, f"scenario {n}, step {k + 1}")
                    for tab, name in self.TABS.items():
                        where = f"scenario {n}, step {k + 1}, {name} tab"
                        page.click(f'#tabs [data-tab="{tab}"]')
                        # A tab that fails to draw leaves the last one on screen,
                        # so check the right tab is showing before searching it.
                        self.assertEqual(self.errors, [], f"{where}: console errors")
                        self.assertEqual(page.get_attribute(f'#tabs [data-tab="{tab}"]', "aria-selected"), "true", where)
                        text = self.visible_text(page)
                        if tab == "payload":
                            for content in exempt:
                                text = text.replace(content, "<tool_result content>")
                        leaks += [f"step {k + 1}, {name} tab: {p!r}" for p in look_for if p in text][:1]
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


    # --- page structure (#78) ----------------------------------------------

    def top_of(self, page, selector):
        """Where an element's top sits in the window, in pixels."""
        return page.evaluate("s => document.querySelector(s).getBoundingClientRect().top", selector)

    def test_each_nav_link_reaches_its_section(self):
        page = self.open("?scenario=1")
        self.wait_for_scenario(page, 1)
        links = page.eval_on_selector_all(".nav a", "as => as.map(a => a.getAttribute('href'))")
        self.assertEqual(len(links), 8)
        for href in links:
            with self.subTest(href):
                self.assertEqual(page.locator(href).count(), 1, f"nav link {href}: no section with that id")
                page.click(f'.nav a[href="{href}"]')
                top = self.top_of(page, href)
                # Just below the sticky nav (about 50px), or as high as the page can scroll.
                at_bottom = page.evaluate("innerHeight + scrollY >= document.documentElement.scrollHeight - 2")
                self.assertTrue(0 <= top <= 120 or at_bottom, f"{href} is at {top}px after its nav link")
        self.assertEqual(self.errors, [])

    def test_watch_it_run_reaches_the_run_view(self):
        page = self.open()
        self.wait_for_scenario(page, 1)
        page.click(".hero-cta")
        self.assertLessEqual(abs(self.top_of(page, "#run-view") - 64), 60)
        self.assertEqual(self.errors, [])

    def test_each_watch_it_button_loads_its_scenario_and_scrolls_to_the_run(self):
        page = self.open("?scenario=6")
        self.wait_for_scenario(page, 6)
        buttons = page.eval_on_selector_all("#how-it-works button.watch", "bs => bs.map(b => Number(b.dataset.scenario))")
        self.assertEqual(buttons, [1, 3, 4])
        for n in buttons:
            with self.subTest(scenario=n):
                page.evaluate("window.explorer.show(3)")
                page.evaluate("window.scrollTo(0, 0)")
                page.click(f'#how-it-works button.watch[data-scenario="{n}"]')
                self.wait_for_scenario(page, n, f"Watch it, scenario {n}")
                self.assertTrue(page.url.endswith(f"?scenario={n}"), page.url)
                self.assertEqual(page.evaluate("window.explorer.state.i"), 0, f"scenario {n}: not at step 1")
                top = self.top_of(page, "#run-view")
                self.assertLessEqual(abs(top - 64), 60, f"scenario {n}: run view is at {top}px")
        page.go_back()
        self.wait_for_scenario(page, 3, "Back after the Watch it buttons")
        self.assertEqual(self.errors, [])

    def test_back_over_a_nav_link_keeps_the_run_where_it_was(self):
        page = self.open("?scenario=2")
        self.wait_for_scenario(page, 2)
        page.evaluate("window.explorer.show(5)")
        page.click('.nav a[href="#how-it-works"]')
        page.go_back()
        page.wait_for_timeout(300)
        self.assertEqual(page.evaluate("[window.explorer.state.scenario.id, window.explorer.state.i]"), [2, 5])

    def test_space_drives_the_run_only_while_it_is_on_screen(self):
        page = self.open("?scenario=1")
        self.wait_for_scenario(page, 1)
        page.evaluate("window.scrollTo(0, 0)")   # the hero: the run is below the fold
        page.keyboard.press("Space")
        self.assertFalse(page.evaluate("window.explorer.state.playing"), "Space started the run from the hero")
        page.evaluate("document.getElementById('run-view').scrollIntoView()")
        page.keyboard.press("Space")
        self.assertTrue(page.evaluate("window.explorer.state.playing"), "Space didn't play with the run on screen")

    def test_every_section_fits_a_phone(self):
        page = self.open("?scenario=4", width=390)
        self.wait_for_scenario(page, 4)
        width = page.evaluate("document.documentElement.scrollWidth")
        self.assertLessEqual(width, 390, "the page scrolls sideways at phone width")
        for selector in ["#hero", "#what-is-an-agent", "#how-it-works", "#scenarios", "#run-view",
                         "#principles", "#how-it-was-built", "#footer"]:
            with self.subTest(selector):
                box = page.eval_on_selector(selector, "e => e.getBoundingClientRect().right")
                self.assertLessEqual(box, 390)
        self.assertEqual(self.errors, [])


    # --- scenario cards (#79) ----------------------------------------------

    def cards_ready(self, page):
        page.wait_for_function("document.querySelectorAll('.scenario-card').length === 9"
                               " && [...document.querySelectorAll('.card-path')].every(c => !c.textContent.includes('…'))")

    def selected_cards(self, page):
        return page.eval_on_selector_all(".scenario-card.selected", "cs => cs.map(c => Number(c.dataset.scenario))")

    def test_the_cards_are_grouped_and_in_order(self):
        page = self.open()
        self.cards_ready(page)
        groups = page.eval_on_selector_all(".card-group", """gs => gs.map(g => [g.querySelector('.card-group-name').textContent,
            [...g.querySelectorAll('.scenario-card')].map(c => Number(c.dataset.scenario))])""")
        self.assertEqual(groups, [["Normal runs", [1, 2, 3, 4, 5]], ["Break the agent", [6, 7, 8, 9]]])
        self.assertEqual(self.errors, [])

    def test_each_cards_tool_path_matches_its_recording(self):
        page = self.open()
        self.cards_ready(page)
        for sc in SCENARIOS:
            n = sc["id"]
            with self.subTest(scenario=n):
                shown = collapse(page.inner_text(f'.scenario-card[data-scenario="{n}"] .card-path'))
                self.assertEqual(shown, tool_path(recording(n)), f"scenario {n}: card path vs recording")

    def test_break_the_agent_cards_say_the_failure_is_simulated(self):
        page = self.open()
        self.cards_ready(page)
        for sc in SCENARIOS:
            with self.subTest(scenario=sc["id"]):
                chip = page.locator(f'.scenario-card[data-scenario="{sc["id"]}"] .card-sim')
                self.assertEqual(chip.count(), 1 if sc["fault"] else 0)
                if sc["fault"]:
                    self.assertEqual(chip.inner_text(), "Simulated failure")

    # A rating, or saying there was one. (?i:...) ignores case for that part only.
    RATING_WORDS = re.compile(r"\b(STRONG|WORTH REVIEWING|IGNORE)\b|(?i:\brat(ed|ing)\b)")

    def test_no_card_states_the_rating(self):
        # D39 (PR #89 review): a card's own words never state the rating. Its
        # own words are everything but the scenario's name and the tool path:
        # a path may end in flag_for_review, and a break-the-agent name states
        # its failure, which is the premise, not the ending. (The setup line
        # is also held to #75's stricter intro rule, in test_docs.)
        page = self.open()
        self.cards_ready(page)
        for sc in SCENARIOS:
            with self.subTest(scenario=sc["id"]):
                words = page.eval_on_selector(f'.scenario-card[data-scenario="{sc["id"]}"]', """c => {
                    const copy = c.cloneNode(true);
                    copy.querySelectorAll('.card-name, .card-path').forEach(x => x.remove());
                    return copy.textContent; }""")
                found = self.RATING_WORDS.search(words)
                self.assertIsNone(found and found.group(), f"scenario {sc['id']}: {words!r}")

    def test_clicking_a_card_loads_its_run_and_back_returns_to_the_previous_card(self):
        page = self.open("?scenario=2")
        self.cards_ready(page)
        self.wait_for_scenario(page, 2)
        self.assertEqual(self.selected_cards(page), [2])
        page.evaluate("window.explorer.show(4); window.scrollTo(0, 0)")
        page.click('.scenario-card[data-scenario="7"]')
        self.wait_for_scenario(page, 7, "clicking card 7")
        self.assertTrue(page.url.endswith("?scenario=7"), page.url)
        self.assertEqual(page.evaluate("window.explorer.state.i"), 0)
        self.assertEqual(self.selected_cards(page), [7])
        self.assertLessEqual(abs(self.top_of(page, "#run-view") - 64), 60, "clicking a card didn't scroll to the run")
        page.go_back()
        self.wait_for_scenario(page, 2, "Back after clicking card 7")
        self.assertEqual(self.selected_cards(page), [2])
        page.go_forward()
        self.wait_for_scenario(page, 7, "Forward to card 7")
        self.assertEqual(self.selected_cards(page), [7])
        page.select_option("#scenario", "5")   # the drop-down still works, and moves the selection
        self.wait_for_scenario(page, 5, "picking 5 from the drop-down")
        self.assertEqual(self.selected_cards(page), [5])
        self.assertEqual(self.errors, [])

    def test_the_selected_card_on_page_load(self):
        for query, want in (("", [1]), ("?scenario=5", [5]), ("?scenario=42", [])):
            with self.subTest(query or "no scenario"):
                page = self.open(query)
                self.cards_ready(page)
                page.wait_for_function("window.explorer && (window.explorer.state.steps.length"
                                       " || !document.getElementById('load-error').hidden)")
                self.assertEqual(self.selected_cards(page), want)

    def test_the_cards_stack_on_a_phone(self):
        page = self.open(width=390)
        self.cards_ready(page)
        lefts = page.eval_on_selector_all(".scenario-card", "cs => cs.map(c => Math.round(c.getBoundingClientRect().left))")
        self.assertEqual(len(set(lefts)), 1, f"cards aren't in one column: {lefts}")
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
        self.assertEqual(self.errors, [])


    # --- design principles (#80) -------------------------------------------

    def test_every_principles_watch_it_loads_its_scenario_and_scrolls_to_the_run(self):
        page = self.open("?scenario=5")
        self.wait_for_scenario(page, 5)
        buttons = page.eval_on_selector_all("#principles button.watch",
                                            "bs => bs.map((b, i) => [i, Number(b.dataset.scenario), b.textContent])")
        self.assertEqual(len(buttons), 11)   # 7 for the principles, 4 for demonstrated guards
        for i, n, label in buttons:
            with self.subTest(button=label, scenario=n):
                page.evaluate("window.explorer.show(2); window.scrollTo(0, 0)")
                page.locator("#principles button.watch").nth(i).click()
                self.wait_for_scenario(page, n, f"principles button {label!r}")
                self.assertTrue(page.url.endswith(f"?scenario={n}"), page.url)
                self.assertEqual(page.evaluate("window.explorer.state.i"), 0, f"{label!r}: not at step 1")
                top = self.top_of(page, "#run-view")
                self.assertLessEqual(abs(top - 64), 60, f"{label!r}: run view is at {top}px")
        self.assertEqual(self.errors, [])

    def test_guard_names_come_from_steps_json(self):
        steps = json.load(open(os.path.join(HERE, "site", "steps.json"), encoding="utf-8"))["steps"]
        page = self.open()
        self.wait_for_scenario(page, 1)
        shown = page.eval_on_selector_all("#principles li[data-guard]",
                                          "ls => ls.map(l => [l.dataset.guard, l.querySelector('.guard-name').textContent])")
        self.assertEqual(len(shown), 9)
        for step, name in shown:
            with self.subTest(step):
                self.assertEqual(name, f"{steps[step]['number']} · {steps[step]['title']}")


    # --- how it was built (#81) --------------------------------------------

    def test_how_it_was_built_shows_the_numbers_from_numbers_json(self):
        numbers = json.load(open(os.path.join(HERE, "site", "numbers.json"), encoding="utf-8"))
        page = self.open()
        self.wait_for_scenario(page, 1)
        page.wait_for_function("[...document.querySelectorAll('[data-number]')].every(n => n.textContent !== '')")
        shown = page.eval_on_selector_all("[data-number]", "ns => ns.map(n => [n.dataset.number, n.textContent])")
        self.assertEqual(len(shown), 10)
        for slot, text in shown:
            with self.subTest(slot):
                value = numbers
                for key in slot.split("."):
                    value = value[key]
                self.assertEqual(text, str(value))
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
