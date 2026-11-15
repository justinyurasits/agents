"""Tests for record.py: run a scenario, save it, check it (issue #53).

Fake Claude replies built from real SDK types (tests/fakes.py), so no API
calls and no key. Files go to a temporary folder, never to recordings/ or
docs/.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import copy
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout

try:
    import fakes
    from test_tracing import TraceTestCase
except ImportError:  # when run as tests.test_record
    from tests import fakes
    from tests.test_tracing import TraceTestCase

import record  # noqa: E402  (after fakes, so agent is imported safely)

agent = fakes.agent
SCENARIOS = record.load_scenarios()
BY_ID = {s["id"]: s for s in SCENARIOS}
YES = '{"answer": "yes", "reasons": ["Builds agents hands-on"]}'
FINAL = "Done."


def tool_turn(*calls):
    """One Claude reply asking for these tools: (id, name, input) each."""
    return fakes.reply(*(fakes.tool_use(*c) for c in calls), stop_reason="tool_use")


def done():
    return fakes.reply(fakes.text(FINAL))


EVAL = {"company": "Northwind Labs", "role_title": "AI Agent Architect",
        "job_description": "Design agent workflows.", "remote": True,
        "compensation": "$200,000–$240,000 base"}
FLAG = {"company": "Northwind Labs", "role_title": "AI Agent Architect",
        "missing_info": "compensation"}


class RecordTestCase(TraceTestCase):
    """Runs record.main against a temp folder with a fake client."""

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "recordings")
        self.docs = os.path.join(self.tmp.name, "SCENARIOS.md")
        self.scenarios_file = record.SCENARIOS_FILE

    def tearDown(self):
        self.tmp.cleanup()
        super().tearDown()

    def run_record(self, argv, outer=(), inner=()):
        self.fake = fakes.use_fake(outer=outer, inner=inner)
        self.calls = []
        create = self.fake.create
        self.fake.create = lambda **kw: self.calls.append(kw) or create(**kw)
        printed = []
        code = record.main(argv, scenarios_file=self.scenarios_file, directory=self.dir,
                           docs_path=self.docs, out=printed.append)
        return code, "\n".join(printed)

    def saved(self, sid):
        with open(record.recording_path(sid, self.dir), encoding="utf-8") as f:
            return json.load(f)


class AcceptanceTest(RecordTestCase):
    """The acceptance criteria in issue #53, one test each."""

    def test_scenario_1_strong_is_saved_and_passes(self):
        code, printed = self.run_record(["1"], outer=[tool_turn(("toolu_1", "evaluate_job", EVAL)), done()],
                                        inner=[fakes.reply(fakes.text(YES))])
        self.assertEqual(code, 0)
        self.assertIn("PASS", printed)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "scenario-01.json")))
        saved = self.saved(1)
        self.assertIs(saved["mismatch"], False)
        self.assertEqual(saved["check"]["actual"], {"tools": ["evaluate_job"], "outcome": ["STRONG"]})
        self.assertEqual(saved["scenario"], "scenario-1")
        self.assertEqual(saved["events"][0]["payload"]["job_text"], BY_ID[1]["posting"])

    def test_different_path_is_saved_as_a_mismatch_naming_both_tools(self):
        code, printed = self.run_record(["1"], outer=[tool_turn(("toolu_1", "flag_for_review", FLAG)), done()])
        self.assertEqual(code, 1)
        self.assertIn("MISMATCH", printed)
        self.assertIn("expected evaluate_job; got flag_for_review", printed)
        saved = self.saved(1)
        self.assertIs(saved["mismatch"], True)
        self.assertIs(saved["check"]["mismatch"], True)
        self.assertIn("tools: expected evaluate_job; got flag_for_review",
                      saved["check"]["differences"])
        self.assertIn("outcome: expected STRONG; got flagged", saved["check"]["differences"])
        # Every step is still there: the whole trace, through the final answer.
        steps = [e["step_id"] for e in saved["events"]]
        for step in ("agent_starts", "send_to_claude", "run_tools", "results_back",
                     "answer_returned"):
            self.assertIn(step, steps)
        self.assertEqual(saved["result"]["ended_by"], "end_turn")

    def test_mismatched_run_keeps_its_errors(self):
        # A path with an error in it: the grader's reply is broken, Claude gives up.
        code, _ = self.run_record(["1"], outer=[tool_turn(("toolu_1", "evaluate_job", EVAL)), done()],
                                  inner=[fakes.reply(fakes.text("not json"))])
        self.assertEqual(code, 1)
        saved = self.saved(1)
        self.assertEqual(saved["check"]["actual"]["outcome"], ["no rating"])
        caught = [e for e in saved["events"] if e["guard"] and e["guard"]["caught"]]
        self.assertEqual([e["step_id"] for e in caught], ["tool_failed"])

    def test_scenario_6_records_the_injected_fault_the_guard_the_error_and_the_finish(self):
        code, printed = self.run_record(
            ["6"],
            outer=[tool_turn(("toolu_1", "evaluate_job", EVAL)),     # fails (injected)
                   tool_turn(("toolu_2", "evaluate_job", EVAL)),     # Claude retries
                   done()],
            inner=[fakes.reply(fakes.text(YES)), fakes.reply(fakes.text(YES))])
        self.assertEqual(code, 0, printed)
        saved = self.saved(6)
        self.assertEqual(saved["fault"], "tool_fails")
        injected = [e for e in saved["events"] if e["injected"]]
        fault = next(e for e in injected if e["payload"] and "grader_reply" in e["payload"])
        self.assertEqual(fault["payload"]["fault"], "tool_fails")
        guard = next(e for e in injected if e["guard"] and e["guard"]["caught"])
        self.assertEqual((guard["step_id"], guard["guard"]["name"]), ("tool_failed", "tool_succeeded"))
        error = next(e for e in injected if e["payload"] and e["payload"].get("is_error") is True)
        self.assertEqual(error["payload"]["tool_use_id"], "toolu_1")
        self.assertEqual(saved["result"]["ended_by"], "end_turn")
        # The retry is counted once, so this run passes.
        self.assertEqual(saved["check"]["actual"], {"tools": ["evaluate_job"], "outcome": ["STRONG"]})

    def test_editing_a_posting_updates_scenarios_md(self):
        edited = copy.deepcopy(SCENARIOS)
        edited[0]["posting"] = "Edited Co — AI Lead\nLocation: Remote (US)\nCompensation: $250K"
        self.scenarios_file = os.path.join(self.tmp.name, "scenarios.json")
        with open(self.scenarios_file, "w", encoding="utf-8") as f:
            json.dump(edited, f, ensure_ascii=False)
        self.run_record(["1"], outer=[tool_turn(("toolu_1", "evaluate_job", EVAL)), done()],
                        inner=[fakes.reply(fakes.text(YES))])
        with open(self.docs, encoding="utf-8") as f:
            doc = f.read()
        self.assertIn("```text\nEdited Co — AI Lead\nLocation: Remote (US)\nCompensation: $250K\n```", doc)
        self.assertNotIn("Northwind Labs builds workflow software", doc)
        self.assertEqual(doc, record.render_scenarios_md(edited))

    def test_unknown_id_lists_the_valid_ids_and_runs_nothing(self):
        code, printed = self.run_record(["42"])
        self.assertEqual(code, 2)
        self.assertEqual(printed, "No scenario 42. Valid ids: 1, 2, 3, 4, 5, 6, 7, 8, 9.")
        self.assertEqual(self.calls, [])                  # no API call
        self.assertFalse(os.path.exists(self.dir))        # nothing saved
        self.assertFalse(os.path.exists(self.docs))       # docs untouched


class CompareTest(unittest.TestCase):
    """actual() and differences() on their own."""

    def test_retries_count_once_but_order_of_different_tools_matters(self):
        got = {"tools": ["evaluate_job"], "outcome": ["stopped"]}
        self.assertEqual(record.differences({"tools": ["evaluate_job"], "outcome": "stopped"}, got), [])
        swapped = {"tools": ["flag_for_review", "evaluate_job"], "outcome": ["flagged", "STRONG"]}
        self.assertTrue(record.differences(BY_ID[4]["expect"], swapped))

    def test_any_accepted_result_passes(self):
        for outcome in ("STRONG", "WORTH REVIEWING", "no rating"):
            with self.subTest(outcome):
                got = {"tools": ["evaluate_job"], "outcome": [outcome]}
                self.assertEqual(record.differences(BY_ID[6]["expect"], got), [])
        got = {"tools": ["evaluate_job"], "outcome": ["IGNORE"]}
        diffs = record.differences(BY_ID[6]["expect"], got)
        self.assertEqual(len(diffs), 1)
        self.assertIn("matched none of the accepted results", diffs[0])

    def test_every_scenario_has_a_valid_expect(self):
        allowed = {"STRONG", "WORTH REVIEWING", "IGNORE", "flagged", "stopped", "no rating"}
        for s in SCENARIOS:
            with self.subTest(s["id"]):
                for option in record._as_list(s["expect"]):
                    self.assertEqual(set(option), {"tools", "outcome"})
                    self.assertLessEqual(set(record._as_list(option["outcome"])), allowed)


class StoppedAndJoinedTest(RecordTestCase):

    def test_a_stopped_run_is_stopped(self):
        _, _ = self.run_record(["9"], outer=[fakes.reply(fakes.text("Here"), stop_reason="max_tokens")])
        self.assertEqual(self.saved(9)["check"]["actual"], {"tools": [], "outcome": ["stopped"]})
        self.assertIs(self.saved(9)["mismatch"], False)

    def test_two_postings_are_sent_together_and_both_outcomes_count(self):
        code, printed = self.run_record(
            # Scenario 4's path since research_company (#65): rate the first
            # posting and research the second in one reply, then flag it.
            ["4"], outer=[tool_turn(("toolu_1", "evaluate_job", EVAL),
                                    ("toolu_2", "research_company",
                                     {"company": "Fernhollow Insurance", "role_level": "Lead PM"})),
                          tool_turn(("toolu_3", "flag_for_review", FLAG)),
                          done()],
            inner=[fakes.reply(fakes.text(YES))])
        self.assertEqual(code, 0, printed)
        sent = self.calls[0]["messages"][0]["content"]
        first, second = BY_ID[4]["posting"]
        self.assertIn(first + agent.POSTING_SEPARATOR + second, sent)
        self.assertEqual(self.saved(4)["check"]["actual"]["outcome"], ["STRONG", "flagged"])


class DocsInSyncTest(unittest.TestCase):

    def test_committed_scenarios_md_matches_scenarios_json(self):
        with open(record.SCENARIOS_MD, encoding="utf-8") as f:
            self.assertEqual(f.read(), record.render_scenarios_md(SCENARIOS))


class ChooseRunTest(unittest.TestCase):

    def test_agent_scenario_option_joins_several_postings_too(self):
        job, _, _ = agent.choose_run(["--scenario", "4"])
        self.assertEqual(job, agent.scenario_job_text(BY_ID[4]))
        self.assertIsInstance(job, str)



class CommittedRecordingsTest(unittest.TestCase):
    """The recordings the page plays (#104): each made from committed code,
    stamped with a commit in this repo's history, and passing its scenario."""

    def recordings(self):
        for sc in record.load_scenarios():
            with open(record.recording_path(sc["id"]), encoding="utf-8") as f:
                yield sc, json.load(f)

    def test_no_recording_is_marked_uncommitted(self):
        for sc, trace in self.recordings():
            with self.subTest(scenario=sc["id"]):
                self.assertIs(trace["git_dirty"], False, f"scenario {sc['id']} says it ran uncommitted code")

    @unittest.skipIf(shutil.which("git") is None, "git isn't installed")
    def test_every_recording_names_a_commit_in_this_repos_history(self):
        for sc, trace in self.recordings():
            with self.subTest(scenario=sc["id"]):
                # merge-base --is-ancestor: exit 0 when the commit is in HEAD's history.
                found = subprocess.run(["git", "merge-base", "--is-ancestor", trace["git_commit"], "HEAD"],
                                       cwd=os.path.dirname(record.__file__), capture_output=True)
                self.assertEqual(found.returncode, 0, f"scenario {sc['id']}: {trace['git_commit']} isn't in history")

    def test_every_committed_recording_passes_its_scenario(self):
        for sc, trace in self.recordings():
            with self.subTest(scenario=sc["id"]):
                self.assertEqual(record.differences(sc["expect"], record.actual(trace)), [])
                self.assertFalse(trace.get("mismatch"))


if __name__ == "__main__":
    unittest.main()
