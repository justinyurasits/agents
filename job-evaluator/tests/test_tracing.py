"""Tests for the trace recorder and core events (issue #28, part B of #1).

Fake Claude replies built from real SDK types (tests/fakes.py). No API calls.
Run from job-evaluator/:  python -m unittest discover -s tests -v
"""

import json
import os
import re
import tempfile
import unittest
from unittest import mock

try:
    import fakes
except ImportError:  # when run as tests.test_tracing
    from tests import fakes

agent = fakes.agent
import code_refs  # noqa: E402
import tracing    # noqa: E402

JOB = "Northwind Labs — AI Agent Architect\nRemote (US)\n$200,000–$240,000 base"
EVAL_INPUT = {"company": "Northwind Labs", "role_title": "AI Agent Architect",
              "job_description": "Design agentic workflows."}
FLAG_INPUT = {"company": "Fabrikam", "role_title": "Analyst", "missing_info": "compensation"}
GRADE = '{"rating": "WORTH REVIEWING", "reasons": ["remote", "pay"]}'
FINAL = "Northwind Labs: worth reviewing."

# A clean run, as STEPS.md describes it: (pass, step_id, crossing kind).
# Guard events show as ("guard", <name>).
CLEAN_SEQUENCE = [
    (0, "agent_starts", None),
    (0, "conversation_setup", None),
    (1, "send_to_claude", ("guard", "pass_count")),
    (1, "send_to_claude", "api_request"),
    (1, "send_to_claude", ("guard", "api_call_succeeded")),
    (1, "claude_decides", "api_response"),
    (1, "check_reply", ("guard", "stop_reason")),
    (1, "check_reply", ("guard", "max_tokens")),
    (1, "save_turn", None),
    (1, "run_tools", ("guard", "tool_exists")),
    (1, "run_tools", "tool_call"),
    (1, "inner_grader", "inner_api_request"),
    (1, "inner_grader", "inner_api_response"),
    (1, "inner_grader", ("guard", "max_tokens")),
    (1, "run_tools", ("guard", "tool_succeeded")),
    (1, "run_tools", "tool_result"),
    (1, "results_back", None),
    (2, "send_to_claude", ("guard", "pass_count")),
    (2, "send_to_claude", "api_request"),
    (2, "send_to_claude", ("guard", "api_call_succeeded")),
    (2, "claude_decides", "api_response"),
    (2, "claude_done", ("guard", "stop_reason")),
    (2, "answer_returned", ("guard", "final_text_present")),
    (2, "answer_returned", None),
]


def kind(e):
    """An event's crossing kind, or ("guard", name) for a guard event."""
    if e["guard"]:
        return ("guard", e["guard"]["name"])
    return (e["crossing"] or {}).get("kind")


class TraceTestCase(unittest.TestCase):

    def setUp(self):
        self.real_client = agent.client
        quiet = mock.patch("builtins.print")
        quiet.start()
        self.addCleanup(quiet.stop)
        self.addCleanup(setattr, agent, "client", self.real_client)

    def record(self, outer, inner=(), job=JOB):
        fakes.use_fake(outer, inner)
        rec = tracing.Recorder(scenario="test", git=("abc1234", False))
        final = agent.run_agent(job, recorder=rec)
        return final, rec

    def clean_run(self):
        return self.record(
            outer=[fakes.reply(fakes.thinking("The posting has pay and remote; I can rate it."),
                               fakes.text("I'll rate this."),
                               fakes.tool_use("toolu_1", "evaluate_job", EVAL_INPUT),
                               stop_reason="tool_use", input_tokens=812, output_tokens=143),
                   fakes.reply(fakes.text(FINAL), input_tokens=1000, output_tokens=60)],
            inner=[fakes.reply(fakes.text(GRADE))])


class CleanRunTest(TraceTestCase):

    def test_every_step_both_passes_in_order(self):
        final, rec = self.clean_run()
        self.assertEqual(final, FINAL)
        got = [(e["pass"], e["step_id"], kind(e)) for e in rec.events]
        self.assertEqual(got, CLEAN_SEQUENCE)

    def test_covers_every_steps_md_step_except_inner_and_error_cases(self):
        _, rec = self.clean_run()
        with open(code_refs.AGENT_PATH.replace("agent.py", "docs/STEPS.md"), encoding="utf-8") as f:
            step_ids = set(re.findall(r"^Step id: `(\w+)`$", f.read(), re.M))
        not_in_clean_run = {"tool_failed", "unknown_tool", "reply_cut_off", "pass_cap",
                            "grader_cut_off", "api_call_failed", "no_final_answer"}
        self.assertEqual({e["step_id"] for e in rec.events}, step_ids - not_in_clean_run)

    def test_seq_and_ids(self):
        _, rec = self.clean_run()
        self.assertEqual([e["seq"] for e in rec.events], list(range(1, len(rec.events) + 1)))
        self.assertEqual([e["id"] for e in rec.events], [f"e{n}" for n in range(1, len(rec.events) + 1)])

    def test_every_event_has_every_key(self):
        _, rec = self.clean_run()
        for e in rec.events:
            with self.subTest(e["id"]):
                self.assertEqual(tuple(e), tracing.EVENT_KEYS)
                if e["crossing"]:
                    self.assertIn(e["crossing"]["kind"], tracing.CROSSING_KINDS)
                self.assertIs(e["injected"], False)

    def test_code_refs_match_the_markers(self):
        _, rec = self.clean_run()
        source = code_refs.load_source()
        for e in rec.events:
            with self.subTest(e["id"]):
                self.assertEqual(e["code"], code_refs.code_ref(e["step_id"], source))
        decides = [e for e in rec.events if e["step_id"] == "claude_decides"]
        self.assertTrue(all(e["code"] is None for e in decides))


class PayloadTest(TraceTestCase):

    def test_api_request_has_system_tool_names_and_messages_at_that_moment(self):
        _, rec = self.clean_run()
        requests = [e for e in rec.events if kind(e) == "api_request"]
        for e in requests:
            p = e["payload"]
            self.assertEqual(p["system"], agent.SYSTEM_PROMPT)
            self.assertEqual(p["tools"], ["evaluate_job", "flag_for_review"])
            self.assertEqual(p["model"], agent.MODEL)
            self.assertEqual(p["max_tokens"], agent.MAX_TOKENS)
        # Snapshot, not a live reference: pass 1 sent 1 message, pass 2 sent 3.
        self.assertEqual([len(e["payload"]["messages"]) for e in requests], [1, 3])

    def test_api_response_has_every_block_stop_reason_and_tokens(self):
        _, rec = self.clean_run()
        first = next(e for e in rec.events if e["step_id"] == "claude_decides")
        self.assertEqual(first["payload"]["stop_reason"], "tool_use")
        self.assertEqual([b["type"] for b in first["payload"]["content"]],
                         ["thinking", "text", "tool_use"])
        self.assertEqual(first["tokens"], {"input": 812, "output": 143})

    def test_thinking_block_is_in_the_trace_without_its_signature(self):
        _, rec = self.clean_run()
        dump = json.dumps(rec.to_dict())
        self.assertIn("The posting has pay and remote; I can rate it.", dump)
        self.assertNotIn("SIGNATURE-OPAQUE", dump)

    def test_tool_call_and_result(self):
        _, rec = self.clean_run()
        call = next(e for e in rec.events if (e["crossing"] or {}).get("kind") == "tool_call")
        result = next(e for e in rec.events if (e["crossing"] or {}).get("kind") == "tool_result")
        self.assertEqual(call["payload"], {"tool": "evaluate_job", "tool_use_id": "toolu_1",
                                           "arguments": EVAL_INPUT})
        self.assertEqual(call["crossing"], {"from": "python", "to": "tool", "kind": "tool_call"})
        self.assertEqual(result["crossing"], {"from": "tool", "to": "python", "kind": "tool_result"})
        self.assertIs(result["payload"]["is_error"], False)
        self.assertEqual(json.loads(result["payload"]["content"])["rating"], "WORTH REVIEWING")

    def test_failed_tool_result_is_recorded_as_error(self):
        _, rec = self.record(
            outer=[fakes.reply(fakes.tool_use("toolu_1", "evaluate_job", EVAL_INPUT),
                               stop_reason="tool_use"),
                   fakes.reply(fakes.text("The grader failed."))],
            inner=[fakes.reply(fakes.text("not json"))])
        result = next(e for e in rec.events if (e["crossing"] or {}).get("kind") == "tool_result")
        self.assertIs(result["payload"]["is_error"], True)
        self.assertIn("JSONDecodeError", result["payload"]["content"])


class MessagesChangeTest(TraceTestCase):

    def test_each_message_changing_step_adds_the_right_number(self):
        # Two tools in one reply: results still go back as ONE new message.
        _, rec = self.record(
            outer=[fakes.reply(fakes.tool_use("toolu_a", "flag_for_review", FLAG_INPUT),
                               fakes.tool_use("toolu_b", "flag_for_review", FLAG_INPUT),
                               stop_reason="tool_use"),
                   fakes.reply(fakes.text("Both flagged."))])
        changes = [e for e in rec.events if e["messages_after"] is not None]
        self.assertEqual([e["step_id"] for e in changes],
                         ["conversation_setup", "save_turn", "results_back"])
        for e in changes:
            with self.subTest(e["step_id"]):
                self.assertEqual(len(e["messages_after"]) - len(e["messages_before"]), 1)
                self.assertEqual(e["messages_after"][:-1], e["messages_before"])
        results_msg = changes[-1]["messages_after"][-1]
        self.assertEqual(results_msg["role"], "user")
        self.assertEqual([r["tool_use_id"] for r in results_msg["content"]], ["toolu_a", "toolu_b"])

    def test_steps_that_dont_change_messages_have_none(self):
        _, rec = self.clean_run()
        for e in rec.events:
            if e["step_id"] not in ("conversation_setup", "save_turn", "results_back"):
                self.assertIsNone(e["messages_before"])
                self.assertIsNone(e["messages_after"])


class EndingsTest(TraceTestCase):

    def test_end_turn(self):
        _, rec = self.clean_run()
        self.assertEqual(rec.result, {"ended_by": "end_turn", "text": FINAL})
        self.assertEqual(rec.events[-1]["step_id"], "answer_returned")

    def test_cut_off_reply(self):
        final, rec = self.record(outer=[fakes.reply(fakes.text("Here is my"),
                                                    stop_reason="max_tokens")])
        self.assertEqual(rec.result["ended_by"], "max_tokens")
        self.assertEqual(rec.events[-1]["step_id"], "reply_cut_off")
        self.assertEqual(rec.events[-1]["payload"]["text"], final)

    def test_pass_cap(self):
        never_done = [fakes.reply(fakes.tool_use(f"toolu_{n}", "flag_for_review", FLAG_INPUT),
                                  stop_reason="tool_use") for n in range(agent.MAX_PASSES)]
        final, rec = self.record(outer=never_done)
        self.assertEqual(rec.result, {"ended_by": "pass_cap", "text": final})
        self.assertEqual(rec.events[-1]["step_id"], "pass_cap")
        self.assertEqual(rec.events[-1]["pass"], agent.MAX_PASSES)


class SecretsAndFileTest(TraceTestCase):

    def test_no_api_key_anywhere_in_the_trace(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": fakes.FAKE_KEY}):
            _, rec = self.clean_run()
            with tempfile.TemporaryDirectory() as d:
                path = rec.write(d)
                with open(path, encoding="utf-8") as f:
                    text = f.read()
        self.assertNotIn("sk-ant", text)

    def test_writer_refuses_a_trace_containing_sk_ant(self):
        # Something that looks like a key got into the run's data: no file.
        _, rec = self.record(outer=[fakes.reply(fakes.text("ok"))],
                             job="Posting text sk-ant-api03-LEAKED")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "sk-ant"):
                rec.write(d)
            self.assertEqual(os.listdir(d), [])

    def test_file_name_and_top_level_shape(self):
        _, rec = self.clean_run()
        with tempfile.TemporaryDirectory() as d:
            path = rec.write(d)
            self.assertRegex(os.path.basename(path), r"^test-\d{8}-\d{6}\.json$")
            with open(path, encoding="utf-8") as f:
                trace = json.load(f)
        self.assertEqual(list(trace), ["trace_version", "scenario", "started_at", "git_commit",
                                       "git_dirty", "model", "limits", "tools", "events", "result"])
        self.assertEqual(trace["git_commit"], "abc1234")
        self.assertEqual(trace["limits"], {"max_passes": 10, "max_tokens": 2000})
        self.assertEqual([t["name"] for t in trace["tools"]], ["evaluate_job", "flag_for_review"])
        self.assertIn("description", trace["tools"][0])   # full definitions, stored once
        self.assertEqual(trace["events"], rec.events)


class NoRecorderTest(TraceTestCase):

    def test_run_agent_without_a_recorder_is_unchanged(self):
        fakes.use_fake(outer=[fakes.reply(fakes.text(FINAL))])
        self.assertEqual(agent.run_agent(JOB), FINAL)


if __name__ == "__main__":
    unittest.main()
