"""Fake Claude replies built from the real SDK types (anthropic.types).

Using the real types means model_dump(), usage and block fields behave
exactly as in a real run, so traces made in tests look like real traces.
No API calls are ever made.
"""

import os
from unittest import mock

from anthropic.types import (Message, TextBlock, ThinkingBlock, ToolUseBlock,
                             Usage)

FAKE_KEY = "sk-ant-test-FAKE-0000"   # must never appear in a trace

# Import agent safely: skip .env, and give the client a fake key that looks
# real, so a test can prove the key never reaches a trace.
with mock.patch("dotenv.load_dotenv"), \
        mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": FAKE_KEY}):
    import agent  # noqa: E402


def thinking(text="Thinking it over."):
    return ThinkingBlock(type="thinking", thinking=text, signature="SIGNATURE-OPAQUE")


def text(value):
    return TextBlock(type="text", text=value)


def tool_use(tool_id, name, tool_input):
    return ToolUseBlock(type="tool_use", id=tool_id, name=name, input=tool_input)


def reply(*blocks, stop_reason="end_turn", input_tokens=100, output_tokens=20):
    return Message(id="msg_fake", type="message", role="assistant",
                   model=agent.MODEL, content=list(blocks),
                   stop_reason=stop_reason, stop_sequence=None,
                   usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens))


class FakeClaude:
    """Stands in for client.messages. Returns canned replies in order.

    Outer calls (sent with tools) and the grader's inner calls (no tools)
    come from separate queues, so a test lists them independently.
    """

    def __init__(self, outer, inner=()):
        self.outer, self.inner = list(outer), list(inner)
        self.api_key = FAKE_KEY       # like the real client: holds the key

    def create(self, **kwargs):
        queue = self.outer if "tools" in kwargs else self.inner
        item = queue.pop(0)
        if isinstance(item, BaseException):   # a queued error: the call fails
            raise item
        return item


def use_fake(outer, inner=()):
    """Point agent.client at a FakeClaude; returns it."""
    fake = FakeClaude(outer, inner)
    agent.client = type("FakeClient", (), {"messages": fake, "api_key": FAKE_KEY})()
    return fake
