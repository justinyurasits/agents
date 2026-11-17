"""Tests that agent.py's annotations stay accurate (issue #44).

agent.py tags every print as (terminal only) and every recording call as
(trace only), labels each guard with its error step from STEPS.md and each
rule with its normal step (#26: guards catch failures, rules apply
decisions), and its terminal output goes through say(), which starts each
line with the step id and its file:line (#120). These tests keep that true as
the code changes. They read source text only: no API calls, agent.py isn't imported.
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


def is_say(call):
    return isinstance(call.func, ast.Name) and call.func.id == "say"


def is_recording(call):
    # rec.…(), tracing.…(), recorder.…()
    f = call.func
    return (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
            and f.value.id in ("rec", "tracing", "recorder"))


class TagsTest(unittest.TestCase):

    def test_every_print_and_say_is_tagged_terminal_only(self):
        prints = [c for c in calls() if is_print(c) or is_say(c)]
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


class RuleLabelsTest(unittest.TestCase):
    """A rule (e.g. the $180K floor) applies one of Justin's decisions. When it
    rejects a posting the agent is working as intended, so a rule is a normal
    step, never an E-step, and is labelled RULE, not GUARD (#26)."""

    RULES = re.findall(r"RULE \(([a-z0-9_]+)\)", SOURCE)

    def test_there_is_at_least_one_rule(self):
        self.assertIn("hard_screen", self.RULES)

    def test_every_rule_is_a_normal_step(self):
        for step_id in self.RULES:
            with self.subTest(step_id):
                self.assertIn(step_id, STEP_IDS)
                self.assertNotIn(step_id, ERROR_STEPS.values())

    def test_every_rule_label_is_just_above_its_marker(self):
        markers = code_refs.find_markers(SOURCE)
        for step_id in self.RULES:
            with self.subTest(step_id):
                marker = markers[step_id]
                above = LINES[max(0, marker - 9):marker - 1]       # up to 8 lines above
                self.assertTrue(any(f"RULE ({step_id})" in line for line in above),
                                f"no 'RULE ({step_id})' comment just above '# STEP: {step_id}'")


class TerminalOutputTest(unittest.TestCase):
    """Terminal lines go through say(step_id, text), which adds the label
    "[step_id agent.py:line]" (#120). tests/test_terminal_labels.py checks
    the labels themselves."""

    def says(self):
        return [c for c in calls() if is_say(c)]

    def test_print_is_only_called_inside_say(self):
        say = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "say")
        inside = {id(c) for c in ast.walk(say) if isinstance(c, ast.Call)}
        for c in calls():
            if is_print(c):
                with self.subTest(line=c.lineno):
                    self.assertIn(id(c), inside, f"a bare print: {LINES[c.lineno - 1].strip()}")

    def test_every_say_names_a_real_step_id(self):
        self.assertGreater(len(self.says()), 10)
        for c in self.says():
            with self.subTest(line=c.lineno):
                first = c.args[0]
                self.assertIsInstance(first, ast.Constant, "the step id must be written out")
                self.assertIn(first.value, STEP_IDS)

    def test_no_label_typed_into_the_text(self):
        # say() adds the label; text that starts with one would show it twice.
        for c in self.says():
            for node in ast.walk(c.args[1]):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    with self.subTest(line=c.lineno):
                        self.assertNotRegex(node.value, r"\[[a-z_]+\]|\[step \d")


if __name__ == "__main__":
    unittest.main()
