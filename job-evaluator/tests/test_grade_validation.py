"""Tests for checking the grader's JSON before it's returned (issue #32).

Fake Claude replies built from real SDK types (tests/fakes.py). No API calls.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import json
import unittest

try:
    import fakes
    from test_tracing import TraceTestCase, kind, EVAL_INPUT, FINAL
except ImportError:  # when run as tests.test_grade_validation
    from tests import fakes
    from tests.test_tracing import TraceTestCase, kind, EVAL_INPUT, FINAL

agent = fakes.agent

# Grader replies that parse as JSON but aren't a valid rating, and what the
# tool must say about each.
BAD = {
    "missing rating":     ('{"reasons": ["remote"]}',
                           "The grader's reply has no 'rating'."),
    "unknown rating":     ('{"rating": "EXCELLENT", "reasons": ["remote"]}',
                           "The grader's rating 'EXCELLENT' isn't one of "
                           "STRONG, WORTH REVIEWING, IGNORE."),
    "non-string rating":  ('{"rating": 5, "reasons": ["remote"]}',
                           "The grader's rating 5 isn't one of "
                           "STRONG, WORTH REVIEWING, IGNORE."),
    "missing reasons":    ('{"rating": "STRONG"}',
                           "The grader's reply has no 'reasons'."),
    "reasons not a list": ('{"rating": "STRONG", "reasons": "remote"}',
                           "The grader's 'reasons' isn't a list of strings."),
    "reasons not strings": ('{"rating": "STRONG", "reasons": ["remote", 3]}',
                            "The grader's 'reasons' isn't a list of strings."),
    "a list":             ('["STRONG", "remote"]',
                           "The grader's reply is a JSON list, not an object."),
    "a string":           ('"STRONG"',
                           "The grader's reply is a JSON str, not an object."),
}

VALID = {
    "plain": {"rating": "WORTH REVIEWING", "reasons": ["remote", "pay"]},
    "extra keys kept": {"rating": "IGNORE", "reasons": [], "confidence": "high"},
}


def evaluate_then_finish(grader_reply):
    return dict(outer=[fakes.reply(fakes.tool_use("toolu_1", "evaluate_job", EVAL_INPUT),
                                   stop_reason="tool_use"),
                       fakes.reply(fakes.text(FINAL))],
                inner=[fakes.reply(fakes.text(grader_reply))])


class GradeProblemTest(unittest.TestCase):
    """The check on its own: a pure function, no run needed."""

    def test_each_bad_grade_names_what_is_wrong(self):
        for label, (reply, problem) in BAD.items():
            with self.subTest(label):
                self.assertEqual(agent.grade_problem(json.loads(reply)), problem)

    def test_valid_grades_have_no_problem(self):
        for label, grade in VALID.items():
            with self.subTest(label):
                self.assertIsNone(agent.grade_problem(grade))

    def test_every_rating_in_the_rubric_is_accepted(self):
        for rating in ("STRONG", "WORTH REVIEWING", "IGNORE"):
            with self.subTest(rating):
                self.assertIn(rating, agent.RUBRIC)
                self.assertIsNone(agent.grade_problem({"rating": rating, "reasons": []}))


class ThroughTheAgentTest(TraceTestCase):

    def test_bad_grade_becomes_an_is_error_tool_result(self):
        for label, (reply, problem) in BAD.items():
            with self.subTest(label):
                final, rec = self.record(**evaluate_then_finish(reply))
                self.assertEqual(final, FINAL)                    # the run continues
                result = next(e for e in rec.events if kind(e) == "tool_result")
                self.assertIs(result["payload"]["is_error"], True)
                self.assertEqual(result["payload"]["content"], f"ValueError: {problem}")

    def test_valid_grade_is_returned_unchanged(self):
        for label, grade in VALID.items():
            with self.subTest(label):
                _, rec = self.record(**evaluate_then_finish(json.dumps(grade)))
                result = next(e for e in rec.events if kind(e) == "tool_result")
                self.assertIs(result["payload"]["is_error"], False)
                self.assertEqual(json.loads(result["payload"]["content"]), grade)

    def test_evaluate_job_called_directly_raises_the_problem(self):
        reply, problem = BAD["unknown rating"]
        fakes.use_fake(outer=[], inner=[fakes.reply(fakes.text(reply))])
        with self.assertRaises(ValueError) as caught:
            agent.evaluate_job(**EVAL_INPUT)
        self.assertEqual(str(caught.exception), problem)


class TraceTest(TraceTestCase):

    def test_bad_grade_records_the_caught_guard_then_the_failed_tool(self):
        reply, problem = BAD["missing reasons"]
        _, rec = self.record(**evaluate_then_finish(reply))
        call = next(e for e in rec.events if kind(e) == "tool_call")
        guard = next(e for e in rec.events if e["guard"] and e["guard"]["name"] == "grade_valid")
        self.assertEqual(guard["step_id"], "invalid_grade")
        self.assertEqual(guard["parent"], call["id"])
        self.assertEqual(guard["guard"]["caught"], True)
        self.assertEqual(guard["guard"]["action"], "error_raised")
        self.assertEqual(guard["guard"]["message"], problem)
        failed = next(e for e in rec.events
                      if e["guard"] and e["guard"]["name"] == "tool_succeeded")
        self.assertEqual(failed["step_id"], "tool_failed")
        self.assertEqual(failed["guard"]["message"], f"ValueError: {problem}")
        self.assertLess(guard["seq"], failed["seq"])

    def test_valid_grade_records_the_check_uncaught(self):
        _, rec = self.record(**evaluate_then_finish(json.dumps(VALID["plain"])))
        guard = next(e for e in rec.events if e["guard"] and e["guard"]["name"] == "grade_valid")
        self.assertEqual(guard["step_id"], "inner_grader")
        self.assertIs(guard["guard"]["caught"], False)
        self.assertIsNone(guard["guard"]["message"])



class AnyCaseTest(TraceTestCase):
    """Issue #42: ratings are accepted in any case and returned in uppercase."""

    CASES = {"strong": "STRONG", "Strong": "STRONG", "worth reviewing": "WORTH REVIEWING",
             "Worth Reviewing": "WORTH REVIEWING", "ignore": "IGNORE", "STRONG": "STRONG"}

    def test_grade_problem_accepts_any_case(self):
        for given in self.CASES:
            with self.subTest(given):
                self.assertIsNone(agent.grade_problem({"rating": given, "reasons": ["x"]}))

    def test_rating_comes_back_uppercase_everything_else_unchanged(self):
        for given, expected in self.CASES.items():
            with self.subTest(given):
                grade = {"rating": given, "reasons": ["remote"], "confidence": "high"}
                _, rec = self.record(**evaluate_then_finish(json.dumps(grade)))
                result = next(e for e in rec.events if kind(e) == "tool_result")
                self.assertIs(result["payload"]["is_error"], False)
                self.assertEqual(json.loads(result["payload"]["content"]),
                                 {**grade, "rating": expected})

    def test_unknown_rating_in_lowercase_is_still_rejected(self):
        problem = agent.grade_problem({"rating": "excellent", "reasons": []})
        self.assertEqual(problem, "The grader's rating 'excellent' isn't one of "
                                  "STRONG, WORTH REVIEWING, IGNORE.")


if __name__ == "__main__":
    unittest.main()
