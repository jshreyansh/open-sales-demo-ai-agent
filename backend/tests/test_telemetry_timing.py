"""Regression test for corrupted t_user_speech_start on turns whose fragment
accumulation survives past an unrelated neighboring turn's own telemetry
close — the same overlap that broke released_by (see
test_telemetry_release.py), but here it corrupts the timing marks
themselves rather than the release-path label.

Before this fix, _telemetry_open() marked t_user_speech_start as "now"
whenever it happened to run — correct only when self._telemetry survives
continuously from this utterance's first VAD-start through to commit. When
an unrelated, overlapping turn's own finally-block closed telemetry first
(confirmed live: visitor d3f3b101, turns 7/18/20), _handle_real_turn's own
_telemetry_open() call reopens a fresh record at COMMIT time, marking
t_user_speech_start there instead of at the utterance's real start —
producing negative user_speech_ms and an inflated turn_commit_latency_ms
that actually just measures how late the reopen was, not anything about the
conversation.

Fix: self._current_utterance_started_at, a durable attribute independent of
self._telemetry's own lifecycle (same pattern already used for
t_user_speech_end via self._last_user_speech_ended_at). Set on VAD-start,
first-write-wins within a burst; _telemetry_open() copies from it instead of
marking "now"; consumed and reset once _handle_real_turn has read it into
whatever record ends up live.
"""
from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock

from loguru import logger

from pipecat.processors.frame_processor import FrameDirection

from src.voice.agent_processor import AgentRuntimeProcessor


def _capture_logs():
    lines: list[str] = []
    sink_id = logger.add(lambda msg: lines.append(msg.record["message"]), level="INFO")
    return lines, sink_id


def test_user_speech_start_survives_telemetry_closed_by_an_unrelated_turn_first():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-timing")
        agent._consume_turn_stream = AsyncMock(
            return_value=({"reply": "ok", "action": None}, False)
        )
        agent._speak_reply = AsyncMock()
        agent._speak = AsyncMock()
        agent._advance_after_turn = AsyncMock()
        agent._amend_interrupted_turn = MagicMock()
        agent._report_reply = AsyncMock()
        agent._report_action = AsyncMock()

        # The real utterance's first (and only) fragment starts here — same
        # as a real VADUserStartedSpeakingFrame would set.
        real_speech_start = time.monotonic()
        agent._current_utterance_started_at = real_speech_start
        agent._telemetry_open()

        # An unrelated neighboring turn's own finally-block closes telemetry
        # while this utterance is still logically "in flight" — exactly
        # what turn 17 did to turn 18's still-forming record in production.
        agent._telemetry_close()
        assert agent._telemetry is None, "precondition: telemetry must be closed here"
        # But the durable start time must NOT have been touched by that close.
        assert agent._current_utterance_started_at == real_speech_start

        await asyncio.sleep(0.05)  # a real, measurable gap before speech "ends"
        agent._last_user_speech_ended_at = time.monotonic()
        agent._pending_released_by = "settle"

        lines, sink_id = _capture_logs()
        try:
            await agent._handle_real_turn("some trailing utterance", FrameDirection.DOWNSTREAM)
        finally:
            logger.remove(sink_id)

        telemetry_lines = [l for l in lines if l.startswith("TURN_TELEMETRY ")]
        assert len(telemetry_lines) == 1
        payload = json.loads(telemetry_lines[0][len("TURN_TELEMETRY "):])

        assert payload["user_speech_ms"] is not None
        assert payload["user_speech_ms"] >= 0, f"user_speech_ms went negative: {payload}"
        # Loose upper bound: this whole test sleeps ~50ms total, so anything
        # near a full second would mean the wrong (much later) timestamp got
        # used for t_user_speech_start.
        assert payload["user_speech_ms"] < 1000, f"suspiciously large: {payload}"

        # Read-then-clear: must not leak into the next burst.
        assert agent._current_utterance_started_at is None

    asyncio.run(_run())


def test_multi_fragment_burst_keeps_first_fragment_as_start():
    """A second VAD-start mid-burst (a later fragment) must NOT overwrite
    the first fragment's start — first-write-wins within one burst, same as
    the pre-existing (correct) behavior for the continuously-open case."""

    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-multi-fragment")
        first_start = time.monotonic()
        agent._current_utterance_started_at = first_start
        agent._telemetry_open()

        await asyncio.sleep(0.02)
        # Simulate a second fragment's VAD-start arriving mid-burst: the real
        # handler only sets this if None, so it should stay untouched here.
        if agent._current_utterance_started_at is None:
            agent._current_utterance_started_at = time.monotonic()

        assert agent._current_utterance_started_at == first_start
        assert agent._telemetry.t_user_speech_start == first_start

    asyncio.run(_run())
