"""Tests that every terminal line leads to its code (issue #120).

Each line agent.py prints starts with its step id and the file:line of that
step's code, e.g. "[send_to_claude agent.py:<line>] pass 1: ...". The number is
looked up from the `# STEP:` markers when the agent starts, never typed in.

Fake Claude replies (tests/fakes.py): no API calls, no key needed.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import contextlib
import io
import re
import unittest

try:
    import fakes
    from test_tracing import EVAL_INPUT, FLAG_INPUT, GRADE, FINAL
except ImportError:  # when run as tests.test_terminal_labels
    from tests import fakes
    from tests.test_tracing import EVAL_INPUT, FLAG_INPUT, GRADE, FINAL

agent = fakes.agent
import code_refs  # noqa: E402

SOURCE = code_refs.load_source()
LABEL = re.compile(r"^ *\[([a-z_]+) agent\.py:(\d+)\] ")


def where(step_id, source=SOURCE):
    """The line a step's label should name: the first line of its code."""
    step = code_refs.TERMINAL_SHARED.get(step_id, step_id)
    return code_refs.code_ref(step, source)["line"]


class LabelsFromMarkersTest(unittest.TestCase):

    def test_a_label_for_every_marker_and_shared_step(self):
        labels = code_refs.terminal_labels(SOURCE)
        self.assertEqual(set(labels), set(code_refs.find_markers(SOURCE))
                         | set(code_refs.SHARED) | set(code_refs.TERMINAL_SHARED))
        self.assertEqual(labels["send_to_claude"],
                         f"[send_to_claude agent.py:{where('send_to_claude')}]")

    def test_each_label_names_the_line_just_below_its_marker(self):
        markers = code_refs.find_markers(SOURCE)
        for step_id, label in code_refs.terminal_labels(SOURCE).items():
            with self.subTest(step_id):
                marker = markers[code_refs.TERMINAL_SHARED.get(
                    step_id, code_refs.SHARED.get(step_id, step_id))]
                self.assertEqual(label, f"[{step_id} agent.py:{marker + 1}]")

    def test_a_blank_line_at_the_top_moves_every_label_down_one(self):
        # Proves the numbers are looked up from the markers, not typed in.
        before = code_refs.terminal_labels(SOURCE)
        after = code_refs.terminal_labels("\n" + SOURCE)
        self.assertEqual(set(before), set(after))
        for step_id in before:
            with self.subTest(step_id):
                number = int(re.search(r":(\d+)\]", before[step_id]).group(1))
                self.assertEqual(after[step_id], f"[{step_id} agent.py:{number + 1}]")

    def test_agent_uses_the_labels_of_its_own_source(self):
        self.assertEqual(agent.TERMINAL_LABELS, code_refs.terminal_labels(SOURCE))

    def test_no_line_number_is_typed_in_agent_py(self):
        # "agent.py:539" or ".py:539" anywhere, a comment included, would be a
        # number someone typed, which goes stale when the file changes.
        for number, line in enumerate(SOURCE.splitlines(), start=1):
            with self.subTest(line=number):
                self.assertNotRegex(line, r"\.py:\d")


class RunOutputTest(unittest.TestCase):
    """Run the agent on fake replies and read what it printed."""

    def setUp(self):
        self.real_client = agent.client
        self.addCleanup(setattr, agent, "client", self.real_client)

    def output(self, outer, inner=()):
        fakes.use_fake(outer, inner)
        out = io.StringIO()
        # redirect_stdout: send print() to `out` instead of the terminal.
        with contextlib.redirect_stdout(out):
            agent.run_agent("Acme — Architect")
        return out.getvalue().splitlines()

    def runs(self):
        tool = lambda tid, name, args: fakes.reply(fakes.tool_use(tid, name, args),  # noqa: E731
                                                   stop_reason="tool_use")
        return {
            "rated, then done": self.output(
                [tool("t1", "research_company", {"company": "Nobody Inc", "role_level": "Staff"}),
                 tool("t2", "evaluate_job", EVAL_INPUT),
                 fakes.reply(fakes.text("Rated it."), fakes.text(FINAL))],
                inner=[fakes.reply(fakes.text(GRADE))]),
            "unknown tool, then flagged": self.output(
                [tool("t1", "no_such_tool", {}),
                 tool("t2", "flag_for_review", FLAG_INPUT),
                 fakes.reply(fakes.text(FINAL))]),
            "cut off": self.output([fakes.reply(fakes.text("Half a"), stop_reason="max_tokens")]),
        }

    def test_every_line_starts_with_a_step_id_and_its_code_line(self):
        seen = set()
        for name, lines in self.runs().items():
            self.assertTrue(lines, name)
            for line in lines:
                if not line:
                    continue                      # blank lines space out the passes
                with self.subTest(run=name, line=line):
                    match = LABEL.match(line)
                    self.assertIsNotNone(match, "no [step_id agent.py:line] label")
                    step_id, number = match.group(1), int(match.group(2))
                    self.assertEqual(number, where(step_id))
                    seen.add(step_id)
        # The runs cover the main loop, a tool, the grader and two guards.
        self.assertLessEqual({"conversation_setup", "send_to_claude", "claude_decides",
                              "save_turn", "run_tools", "research_company", "hard_screen",
                              "inner_grader", "results_back", "claude_done", "tool_failed",
                              "reply_cut_off"}, seen)


if __name__ == "__main__":
    unittest.main()
