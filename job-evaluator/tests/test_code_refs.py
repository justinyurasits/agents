"""Tests for step markers and the code-reference lookup (issue #27).

Reads source text only: no API calls, no key, agent.py isn't imported.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import code_refs  # noqa: E402

STEPS_PATH = os.path.join(ROOT, "docs", "STEPS.md")

# What each step's code starts with and ends with, and how many lines it
# spans. If code moves, these stay true; if code changes, update them.
EXPECTED = {
    "agent_starts":       ("final = run_agent(job, recorder=recorder, fault=faults.Fault(fault_name))",
                           "fault=faults.Fault(fault_name))", 1),
    "conversation_setup": ('messages = [{"role": "user"', "job_text}\"}]", 1),
    "send_to_claude":     ("response = client.messages.create(", ")", 7),
    "check_reply":        ('if response.stop_reason == "end_turn":', "return answer", 17),
    "save_turn":          ('messages.append({"role": "assistant"', "})", 1),
    "run_tools":          ("for tool_block in (b for b in response.content", "})", 41),
    "inner_grader":       ("eval_response = client.messages.create(", ")", 6),
    "results_back":       ('messages.append({"role": "user", "content": tool_results})',
                           "tool_results})", 1),
    "answer_returned":    ('answer = next((b.text for b in response.content if b.type == "text"), None)',
                           "None)", 1),
    "no_final_answer":    ("if answer is None:", "return answer", 4),
    "tool_failed":        ("except Exception as e:", '"is_error": True}', 4),
    "unknown_tool":       ("raise ValueError(", 'for t in tools)}.")', 3),
    "reply_cut_off":      ('if response.stop_reason == "max_tokens":', "return answer", 6),
    "api_call_failed":    ("except anthropic.APIError as e:", "return answer", 9),
    "invalid_grade":      ("if problem:", "raise ValueError(problem)", 2),
    "grader_cut_off":     ('if eval_response.stop_reason == "max_tokens":', 'of {MAX_TOKENS}).")', 3),
    "pass_cap":           ('answer = f"Stopped after {max_passes} passes without finishing."',
                           'finishing."', 1),
}


def steps_md():
    with open(STEPS_PATH, encoding="utf-8") as f:
        return f.read()


def step_ids_in_steps_md():
    return re.findall(r"^Step id: `([a-z][a-z0-9_]*)`$", steps_md(), re.M)


class MarkersMatchStepsTest(unittest.TestCase):
    """Every step with code has exactly one marker, and every marker is a step."""

    def setUp(self):
        self.source = code_refs.load_source()
        self.markers = code_refs.find_markers(self.source)   # raises on duplicates
        self.step_ids = step_ids_in_steps_md()

    def test_step_ids_are_unique(self):
        self.assertEqual(len(self.step_ids), len(set(self.step_ids)))

    def test_every_step_has_code_or_is_known_to_have_none(self):
        for step_id in self.step_ids:
            with self.subTest(step_id):
                marker = code_refs.SHARED.get(step_id, step_id)
                self.assertTrue(step_id in code_refs.NO_CODE or marker in self.markers,
                                f"STEPS.md step {step_id!r} has no '# STEP: {marker}' marker")

    def test_every_marker_is_a_step(self):
        for marker in self.markers:
            with self.subTest(marker):
                self.assertIn(marker, self.step_ids,
                              f"marker {marker!r} in agent.py has no step in STEPS.md")

    def test_shared_and_no_code_steps_have_no_marker_of_their_own(self):
        for step_id in list(code_refs.SHARED) + list(code_refs.NO_CODE):
            self.assertNotIn(step_id, self.markers)

    def test_markers_named_in_steps_md_exist(self):
        for marker in re.findall(r"# STEP: ([a-z0-9_]+)", steps_md()):
            self.assertIn(marker, self.markers)

    def test_four_error_case_steps_exist_with_markers(self):
        for step_id in ("tool_failed", "unknown_tool", "reply_cut_off", "pass_cap",
                        "grader_cut_off", "api_call_failed", "no_final_answer",
                        "invalid_grade"):
            with self.subTest(step_id):
                self.assertIn(step_id, self.step_ids)
                self.assertIn(step_id, self.markers)


class LookupTest(unittest.TestCase):

    def setUp(self):
        self.source = code_refs.load_source()

    def test_each_step_resolves_to_the_expected_full_statement(self):
        for step_id, (first, last, count) in EXPECTED.items():
            with self.subTest(step_id):
                ref = code_refs.code_ref(step_id, self.source)
                self.assertEqual(ref["file"], "agent.py")
                self.assertEqual(ref["marker"], step_id)
                self.assertTrue(ref["lines"][0].startswith(first), ref["lines"][0])
                self.assertTrue(ref["lines"][-1].rstrip().endswith(last), ref["lines"][-1])
                self.assertEqual(len(ref["lines"]), count)
                # `line` really is where that code is in the file.
                actual = self.source.splitlines()[ref["line"] - 1].strip()
                self.assertEqual(actual, ref["lines"][0].strip())

    def test_every_step_id_in_steps_md_is_covered_by_expected(self):
        covered = set(EXPECTED) | set(code_refs.SHARED) | code_refs.NO_CODE
        self.assertEqual(set(step_ids_in_steps_md()), covered)

    def test_claude_done_resolves_to_check_reply(self):
        done = code_refs.code_ref("claude_done", self.source)
        check = code_refs.code_ref("check_reply", self.source)
        self.assertEqual(done, check)
        self.assertEqual(done["marker"], "check_reply")

    def test_claude_decides_has_no_code(self):
        self.assertIsNone(code_refs.code_ref("claude_decides", self.source))

    def test_blank_line_at_top_shifts_every_line_by_one(self):
        shifted = "\n" + self.source
        for step_id in EXPECTED:
            with self.subTest(step_id):
                before = code_refs.code_ref(step_id, self.source)
                after = code_refs.code_ref(step_id, shifted)
                self.assertEqual(after["line"], before["line"] + 1)
                self.assertEqual(after["lines"], before["lines"])


class BadMarkersTest(unittest.TestCase):
    """A broken marker is an error, never silently skipped."""

    def test_duplicate_marker_raises(self):
        src = "# STEP: a\nx = 1\n# STEP: a\ny = 2\n"
        with self.assertRaisesRegex(code_refs.MarkerError, "appears twice"):
            code_refs.find_markers(src)

    def test_missing_marker_raises(self):
        with self.assertRaisesRegex(code_refs.MarkerError, "no '# STEP: nowhere'"):
            code_refs.code_ref("nowhere", "x = 1\n")

    def test_marker_not_directly_above_code_raises(self):
        src = "# STEP: gap\n\nx = 1\n"
        with self.assertRaisesRegex(code_refs.MarkerError, "isn't directly above"):
            code_refs.code_ref("gap", src)


class StepsMdHasNoLineNumbersTest(unittest.TestCase):

    def test_no_hard_coded_line_numbers(self):
        found = re.findall(r"\((?:line|lines) \d+", steps_md())
        self.assertEqual(found, [], "STEPS.md should name markers, not line numbers")


if __name__ == "__main__":
    unittest.main()
