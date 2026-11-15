"""Make site/preview.png: the image shown when the page's link is shared (#105).

    python make_preview.py        (needs Playwright and Chromium: requirements-dev.txt)

It serves job-evaluator/ locally, opens the page at scenario 6 (a tool fails),
moves to the step where the tool's error goes back to Python (the red arrow on
the map), and screenshots the run view at 1200x630, the size link previews
use. Rerun it when the page's look changes; nothing about it is done by hand.
"""

import functools
import http.server
import os
import threading

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PREVIEW = os.path.join(HERE, "site", "preview.png")
WIDTH, HEIGHT = 1200, 630
SCENARIO = 6
# The step to show, found by what happens there rather than by its number:
# the first tool result that's an error.
FIND_STEP = "window.explorer.state.steps.findIndex(s => s.kinds.has('tool_result') && s.bad)"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main(dest=PREVIEW):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=HERE))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1,
                                    reduced_motion="reduce")
            page.goto(f"http://127.0.0.1:{server.server_address[1]}/site/?scenario={SCENARIO}")
            page.wait_for_function(f"window.explorer && window.explorer.state.scenario"
                                   f" && window.explorer.state.scenario.id === {SCENARIO}")
            step = page.evaluate(FIND_STEP)
            if step < 0:
                raise SystemExit(f"scenario {SCENARIO} has no failed tool result to show")
            page.evaluate(f"window.explorer.show({step})")
            # The shot is of the run view alone: hide the nav, every other
            # section and the run's intro card, so the run's header is at the
            # top of the image.
            page.add_style_tag(content=".nav, .page > :not(#run-view), #intro { display: none !important; }")
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=dest)
            browser.close()
    finally:
        server.shutdown()
    print(f"Wrote {os.path.relpath(dest, HERE)}: {WIDTH}x{HEIGHT}, scenario {SCENARIO}, step {step + 1}")


if __name__ == "__main__":
    main()
