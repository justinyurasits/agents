"""Tests that agent.py's annotations stay accurate (issue #44).

agent.py tags every print as (terminal only) and every recording call as
(trace only), labels each guard with its error step from STEPS.md, and its
terminal output uses step ids. These tests keep that true as the code
changes. They read source text only: no API calls, agent.py isn't imported.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import ast
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import code_refs  # noqa: E402

SOURCE = code_refs.load_source()
LINES = SOURCE.splitlines()
TREE = ast.parse(SOURCE)
with open(os.path.join(ROOT, "docs", "STEPS.md"), encoding="utf-8") as f:
    STEPS_MD = f.read()

STEP_IDS = set(re.findall(r"^Step id: `([a-z0-9_]+)`$", STEPS_MD, re.M))
# Error-case steps: "### E3. ..." followed by "Step id: `reply_cut_off`".
ERROR_STEPS = dict(re.findall(r"^### (E\d+)\. .*\n\nStep id: `([a-z0-9_]+)`", STEPS_MD, re.M))


def calls():
    return [n for n in ast.walk(TREE) if isinstance(n, ast.Call)]


def tagged(node, tag):
    """The tag is on the line above the call, or on any line of the call."""
    return any(tag in LINES[i - 1] for i in range(node.lineno - 1, node.end_lineno + 1))


def is_print(call):
    return isinstance(call.func, ast.Name) and call.func.id == "print"


def is_recording(call):
    # rec.…(), tracing.…(), recorder.…()
    f = call.func
    return (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
            and f.value.id in ("rec", "tracing", "recorder"))


class TagsTest(unittest.TestCase):

    def test_every_print_is_tagged_terminal_only(self):
        prints = [c for c in calls() if is_print(c)]
        self.assertGreater(len(prints), 10)
        for c in prints:
            with self.subTest(line=c.lineno):
                self.assertTrue(tagged(c, "(terminal only)"), LINES[c.lineno - 1].strip())

    def test_every_recording_call_is_tagged_trace_only(self):
        recording = [c for c in calls() if is_recording(c)]
        self.assertGreater(len(recording), 10)
        for c in recording:
            with self.subTest(line=c.lineno):
                self.assertTrue(tagged(c, "(trace only)"), LINES[c.lineno - 1].strip())


class GuardLabelsTest(unittest.TestCase):

    def test_steps_md_has_the_error_steps(self):
        self.assertEqual(sorted(ERROR_STEPS), [f"E{n}" for n in range(1, len(ERROR_STEPS) + 1)])
        self.assertGreaterEqual(len(ERROR_STEPS), 8)

    def test_every_error_step_has_a_guard_label_just_above_its_marker(self):
        markers = code_refs.find_markers(SOURCE)
        for number, step_id in ERROR_STEPS.items():
            with self.subTest(step_id):
                label = f"GUARD ({number} {step_id})"
                marker = markers[step_id]
                above = LINES[max(0, marker - 9):marker - 1]       # up to 8 lines above
                self.assertTrue(any(label in line for line in above),
                                f"no '{label}' comment just above '# STEP: {step_id}'")

    def test_no_guard_label_for_a_step_that_isnt_an_error_step(self):
        for number, step_id in re.findall(r"GUARD \((E\d+) ([a-z0-9_]+)\)", SOURCE):
            self.assertEqual(ERROR_STEPS.get(number), step_id)


class TerminalOutputTest(unittest.TestCase):

    def print_texts(self):
        texts = []
        for c in calls():
            if is_print(c) and c.args:
                for node in ast.walk(c.args[0]):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        texts.append(node.value)
        return texts

    def test_no_old_step_numbers(self):
        for text in self.print_texts():
            self.assertNotRegex(text, r"\[step \d|\[stop\]|\[cap\]")

    def test_bracketed_labels_are_real_step_ids(self):
        labels = {m for t in self.print_texts() for m in re.findall(r"\[([a-z_]+)\]", t)}
        self.assertTrue(labels)
        self.assertLessEqual(labels, STEP_IDS)


if __name__ == "__main__":
    unittest.main()
