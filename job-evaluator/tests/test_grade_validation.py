"""Tests for checking the grader's JSON before it's used (issues #32, #26).

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

# Grader replies that parse as JSON but aren't a valid answer, and what the
# tool must say about each. (The grader answers yes or no since #26.)
BAD = {
    "missing answer":     ('{"reasons": ["builds agents"]}',
                           "The grader's reply has no 'answer'."),
    "unknown answer":     ('{"answer": "maybe", "reasons": ["builds agents"]}',
                           "The grader's answer 'maybe' isn't yes or no."),
    "a rating, not an answer": ('{"answer": "STRONG", "reasons": ["builds agents"]}',
                           "The grader's answer 'STRONG' isn't yes or no."),
    "non-string answer":  ('{"answer": true, "reasons": ["builds agents"]}',
                           "The grader's answer True isn't yes or no."),
    "missing reasons":    ('{"answer": "yes"}',
                           "The grader's reply has no 'reasons'."),
    "reasons not a list": ('{"answer": "yes", "reasons": "builds agents"}',
                           "The grader's 'reasons' isn't a list of strings."),
    "reasons not strings": ('{"answer": "yes", "reasons": ["builds agents", 3]}',
                            "The grader's 'reasons' isn't a list of strings."),
    "a list":             ('["yes", "builds agents"]',
                           "The grader's reply is a JSON list, not an object."),
    "a string":           ('"yes"',
                           "The grader's reply is a JSON str, not an object."),
}

# Valid answers and the result evaluate_job returns for each.
VALID = {
    "yes": ({"answer": "yes", "reasons": ["builds agents"]},
            {"rating": "STRONG", "reasons": ["builds agents"]}),
    "no": ({"answer": "no", "reasons": ["manages a sales team"]},
           {"rating": "WORTH REVIEWING", "reasons": ["manages a sales team"]}),
    "extra keys allowed, not passed on": (
        {"answer": "no", "reasons": [], "confidence": "high"},
        {"rating": "WORTH REVIEWING", "reasons": []}),
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
        for label, (grade, _) in VALID.items():
            with self.subTest(label):
                self.assertIsNone(agent.grade_problem(grade))

    def test_the_rubric_asks_for_the_answers_code_maps(self):
        for answer in agent.RATING_FOR_ANSWER:
            with self.subTest(answer):
                self.assertIn(f'"{answer}"', agent.RUBRIC)
        self.assertEqual(agent.RATING_FOR_ANSWER, {"yes": "STRONG", "no": "WORTH REVIEWING"})


class ThroughTheAgentTest(TraceTestCase):

    def test_bad_grade_becomes_an_is_error_tool_result(self):
        for label, (reply, problem) in BAD.items():
            with self.subTest(label):
                final, rec = self.record(**evaluate_then_finish(reply))
                self.assertEqual(final, FINAL)                    # the run continues
                result = next(e for e in rec.events if kind(e) == "tool_result")
                self.assertIs(result["payload"]["is_error"], True)
                self.assertEqual(result["payload"]["content"], f"ValueError: {problem}")

    def test_valid_answer_becomes_the_rating(self):
        for label, (grade, rated) in VALID.items():
            with self.subTest(label):
                _, rec = self.record(**evaluate_then_finish(json.dumps(grade)))
                result = next(e for e in rec.events if kind(e) == "tool_result")
                self.assertIs(result["payload"]["is_error"], False)
                self.assertEqual(json.loads(result["payload"]["content"]), rated)

    def test_evaluate_job_called_directly_raises_the_problem(self):
        reply, problem = BAD["unknown answer"]
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
        _, rec = self.record(**evaluate_then_finish(json.dumps(VALID["yes"][0])))
        guard = next(e for e in rec.events if e["guard"] and e["guard"]["name"] == "grade_valid")
        self.assertEqual(guard["step_id"], "inner_grader")
        self.assertIs(guard["guard"]["caught"], False)
        self.assertIsNone(guard["guard"]["message"])



class AnyCaseTest(TraceTestCase):
    """Issue #42, for the yes/no answer (#26): any case is accepted."""

    CASES = {"yes": "STRONG", "Yes": "STRONG", "YES": "STRONG", " yes ": "STRONG",
             "no": "WORTH REVIEWING", "No": "WORTH REVIEWING", "NO": "WORTH REVIEWING"}

    def test_grade_problem_accepts_any_case(self):
        for given in self.CASES:
            with self.subTest(given):
                self.assertIsNone(agent.grade_problem({"answer": given, "reasons": ["x"]}))

    def test_any_case_answer_gives_the_rating(self):
        for given, expected in self.CASES.items():
            with self.subTest(given):
                grade = {"answer": given, "reasons": ["builds agents"]}
                _, rec = self.record(**evaluate_then_finish(json.dumps(grade)))
                result = next(e for e in rec.events if kind(e) == "tool_result")
                self.assertIs(result["payload"]["is_error"], False)
                self.assertEqual(json.loads(result["payload"]["content"]),
                                 {"rating": expected, "reasons": ["builds agents"]})

    def test_unknown_answer_in_any_case_is_still_rejected(self):
        self.assertEqual(agent.grade_problem({"answer": "Maybe", "reasons": []}),
                         "The grader's answer 'Maybe' isn't yes or no.")


if __name__ == "__main__":
    unittest.main()
