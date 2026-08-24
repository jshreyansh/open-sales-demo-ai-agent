"""Regression tests for released_by=None gaps in TurnTelemetry.

Two things are covered, because they're two different failure modes that
turned out to share one fix:

1. The plain deferred-interruption drain never set released_by at all
   (the original, narrowly-scoped bug).

2. Writing self._telemetry.released_by = "..." directly at the release
   call site — the pattern the other five branches (settle, fast_track,
   stall_backstop, both merge paths) already used, and the pattern the
   drain branch was given in an earlier, insufficient fix — silently no-ops
   whenever self._telemetry happens to be None at that exact moment. That
   isn't rare: turns overlap in this app (interruptions, regenerated
   replies), so an unrelated, still-finishing turn's own
   `finally: self._telemetry_close()` can clear self._telemetry while THIS
   utterance's fragments are still accumulating. Confirmed live on
   deployed production (visitor d3f3b101, turns 7/18/20 all released_by=
   None) — turn 18 in particular went through the completely normal
   "settled — answering once" path and still lost its label, because a
   slow-to-resolve neighbouring turn (17, interrupted and regenerated)
   closed telemetry out from under its fragment accumulation first.

The fix: a plain instance attribute (self._pending_released_by), set at
each release call site same as before, but *applied* to whatever telemetry
record turns out to be open only after _telemetry_open() has run inside
_handle_real_turn — guaranteeing a live record exists by then, fresh or
continued, regardless of what happened to self._telemetry in the meantime.
Same set-before-call/read-once-after shape already used for
_pending_low_confidence_continuation, and for the same reason: don't
thread a new _handle_real_turn parameter through 6 call sites.
"""
from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock

from loguru import logger

from pipecat.processors.frame_processor import FrameDirection

from src.voice.agent_processor import (
    PENDING_FRAGMENT_WATCHDOG_INTERVAL_SECS,
    PENDING_INTERRUPTION_MAX_HOLD_SECS,
    AgentRuntimeProcessor,
)


async def _noop_handle_real_turn(*args, **kwargs):
    return None


def _capture_logs():
    lines: list[str] = []
    sink_id = logger.add(lambda msg: lines.append(msg.record["message"]), level="INFO")
    return lines, sink_id


def test_plain_deferred_interrupt_drain_sets_pending_released_by():
    """The drain branch itself: does it still correctly flag its release
    shape? (Whether that flag survives to the emitted record is a separate
    question, covered below — this only checks the branch's own behavior.)"""

    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-released-by")
        agent._telemetry_open()
        agent._handle_real_turn = _noop_handle_real_turn

        agent._pending_interruption_text = "hello, are you still there"
        agent._pending_interruption_since = (
            time.monotonic() - PENDING_INTERRUPTION_MAX_HOLD_SECS - 1
        )
        agent._pending_fragment_text = ""
        agent._turn_in_progress = False
        agent._bot_speaking = False
        agent._user_speaking = False

        task = asyncio.create_task(agent._watch_pending_fragment_stall())
        try:
            await asyncio.wait_for(
                task, timeout=PENDING_FRAGMENT_WATCHDOG_INTERVAL_SECS * 6
            )
        except asyncio.TimeoutError:
            pass
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert agent._pending_released_by == "deferred_interrupt_drain"

    asyncio.run(_run())


def test_released_by_survives_telemetry_closed_by_an_unrelated_turn_first():
    """Recreates the actual production failure (visitor d3f3b101, turn 18):
    telemetry for this utterance was opened, then closed by some other,
    unrelated turn's own finally-block before this one reached
    _handle_real_turn. released_by must still land correctly on the fresh
    record _handle_real_turn opens next — this is the case the old
    "write self._telemetry.released_by directly at the call site" pattern
    could never handle, no matter which of the 6 branches it was in.

    Everything past run_turn_stream/_consume_turn_stream is mocked out —
    this test is about the telemetry lifecycle, not reply generation or
    speech."""

    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-reopen")
        agent._consume_turn_stream = AsyncMock(
            return_value=({"reply": "ok", "action": None}, False)
        )
        agent._speak_reply = AsyncMock()
        agent._speak = AsyncMock()
        agent._advance_after_turn = AsyncMock()
        agent._amend_interrupted_turn = AsyncMock()
        agent._report_reply = AsyncMock()
        agent._report_action = AsyncMock()

        # An unrelated earlier turn opened telemetry (as a real VAD-start
        # would) and then fully closed it — exactly what a slow, interrupted
        # neighboring turn does in production.
        agent._telemetry_open()
        agent._telemetry_close()
        assert agent._telemetry is None, "precondition: telemetry must be closed here"

        # Set by the release call site (settle, in this recreation) before
        # calling _handle_real_turn — same as the real code now does.
        agent._pending_released_by = "settle"

        lines, sink_id = _capture_logs()
        try:
            await agent._handle_real_turn("some trailing utterance", FrameDirection.DOWNSTREAM)
        finally:
            logger.remove(sink_id)

        telemetry_lines = [l for l in lines if l.startswith("TURN_TELEMETRY ")]
        assert len(telemetry_lines) == 1, f"expected one emitted record, got: {lines}"
        payload = json.loads(telemetry_lines[0][len("TURN_TELEMETRY "):])
        assert payload["released_by"] == "settle"
        # The read-then-clear discipline: must not leak into a next turn.
        assert agent._pending_released_by is None

    asyncio.run(_run())


def test_no_pending_released_by_fails_safe():
    """If some future call site forgets to set self._pending_released_by,
    _handle_real_turn must not crash — released_by just stays None, same as
    it always defaulted to. Silent-but-honest, not a new failure mode."""

    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-no-pending")
        agent._consume_turn_stream = AsyncMock(
            return_value=({"reply": "ok", "action": None}, False)
        )
        agent._speak_reply = AsyncMock()
        agent._speak = AsyncMock()
        agent._advance_after_turn = AsyncMock()
        agent._amend_interrupted_turn = AsyncMock()
        agent._report_reply = AsyncMock()
        agent._report_action = AsyncMock()

        assert agent._pending_released_by is None

        lines, sink_id = _capture_logs()
        try:
            await agent._handle_real_turn("some utterance", FrameDirection.DOWNSTREAM)
        finally:
            logger.remove(sink_id)

        telemetry_lines = [l for l in lines if l.startswith("TURN_TELEMETRY ")]
        assert len(telemetry_lines) == 1
        payload = json.loads(telemetry_lines[0][len("TURN_TELEMETRY "):])
        assert payload["released_by"] is None

    asyncio.run(_run())
