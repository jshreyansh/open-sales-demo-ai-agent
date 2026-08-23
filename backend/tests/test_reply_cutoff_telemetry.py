"""Regression tests for TurnTelemetry.reply_cutoff_reason.

Before this field existed, two very different situations shared one
unstructured log line with no way to tell them apart after the fact:

- A real barge-in (or a fresher stash superseding an auto-continue beat)
  cutting a reply short -- completely normal conversation, not a bug.
- The fast incremental JSON decoder disagreeing with the authoritative
  parse partway through generation -- a real decoding bug that silently
  truncates what the prospect hears, with nothing left to explain why.

Confirmed live: a real call hit the second case 12 times in nine minutes
with nothing in telemetry distinguishing it from ordinary interruptions.
These tests drive _consume_turn_stream directly with a synthetic event
stream to prove each case is now labeled correctly.
"""
from __future__ import annotations

import asyncio

from pipecat.processors.frame_processor import FrameDirection

from src.voice.agent_processor import AgentRuntimeProcessor


async def _events(*items):
    for item in items:
        yield item


def test_stream_mismatch_labeled_correctly_when_nothing_interrupted():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-cutoff-mismatch")
        agent._telemetry_open()

        stream = _events(
            ("reply_delta", "some partial text with no sentence end yet"),
            ("done_fallback", {"reply": "the full authoritative reply", "action": None}),
        )
        result, already_spoken = await agent._consume_turn_stream(stream, FrameDirection.DOWNSTREAM)

        assert already_spoken is True
        assert agent._telemetry.reply_cutoff_reason == "stream_mismatch"

    asyncio.run(_run())


def test_real_interruption_labeled_as_interrupted_not_stream_mismatch():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-cutoff-interrupted")
        agent._telemetry_open()
        agent._interrupted_this_turn = True  # a real barge-in already happened

        stream = _events(
            ("lead_in", "Sure, let me show you"),
            ("done_fallback", {"reply": "whatever would have been said", "action": None}),
        )
        result, already_spoken = await agent._consume_turn_stream(stream, FrameDirection.DOWNSTREAM)

        assert already_spoken is True
        assert agent._telemetry.reply_cutoff_reason == "interrupted"

    asyncio.run(_run())


def test_clean_turn_leaves_cutoff_reason_none():
    """A normal, fully-streamed reply must not be mislabeled either way."""

    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-cutoff-clean")
        agent._telemetry_open()
        agent._speak = _no_op_speak(agent)

        stream = _events(
            ("reply_delta", "A complete sentence. "),
            ("done_streamed", {"reply": "A complete sentence.", "action": None}),
        )
        result, already_spoken = await agent._consume_turn_stream(stream, FrameDirection.DOWNSTREAM)

        assert agent._telemetry.reply_cutoff_reason is None

    asyncio.run(_run())


def _no_op_speak(agent: AgentRuntimeProcessor):
    async def _speak(text, direction):
        agent._speech_finished.set()

    return _speak
