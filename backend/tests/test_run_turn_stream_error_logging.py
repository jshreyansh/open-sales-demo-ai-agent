"""Regression test for P0 #2: logger.exception() was called AFTER the
except block that caught run_turn_stream's failure had already exited,
so sys.exc_info() was already cleared by Python and every occurrence
logged "NoneType: None" instead of the real traceback — useless for
diagnosing what actually failed in production.

Two distinct cases used to share one (broken) log line and are now split:
1. run_turn_stream() actually raises -> logged inside the except block,
   with a real traceback.
2. run_turn_stream() ends with no exception but also no result (its own
   comment: "shouldn't happen") -> logged as a plain error, not a fake
   exception, since logging .exception() here would always print
   "NoneType: None" regardless of where it's placed (there's nothing to
   report a traceback for).

Fallback behavior (the apology reply, already_spoken=False) is
deliberately unchanged in both tests — this is a logging-only fix.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from loguru import logger

from pipecat.processors.frame_processor import FrameDirection

from src.voice.agent_processor import AgentRuntimeProcessor


def _wire_common_mocks(agent: AgentRuntimeProcessor) -> None:
    agent._speak_reply = AsyncMock()
    agent._speak = AsyncMock()
    agent._advance_after_turn = AsyncMock()
    agent._amend_interrupted_turn = MagicMock()
    agent._report_reply = AsyncMock()
    agent._report_action = AsyncMock()


def test_real_exception_produces_a_real_traceback_not_nonetype_none():
    async def _raising_consume_turn_stream(*args, **kwargs):
        raise ValueError("boom - simulated run_turn_stream failure")

    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-logexc")
        agent._consume_turn_stream = _raising_consume_turn_stream
        _wire_common_mocks(agent)

        records = []
        sink_id = logger.add(lambda msg: records.append(msg.record), level="ERROR")
        try:
            await agent._handle_real_turn("hello", FrameDirection.DOWNSTREAM)
        finally:
            logger.remove(sink_id)

        with_exception = [r for r in records if r["exception"] is not None]
        assert len(with_exception) == 1, f"expected exactly one record carrying a real exception: {records}"
        exc = with_exception[0]["exception"]
        # The actual proof: a real exception type/value survived to the log,
        # not "NoneType: None" (which is what exc.type is None would mean).
        assert exc.type is ValueError
        assert "boom - simulated run_turn_stream failure" in str(exc.value)

        # Behavior unchanged: still falls back to the same apology, still
        # not already_spoken (checked indirectly via _speak_reply having
        # been called with the fallback text).
        agent._speak_reply.assert_awaited()
        spoken_text = agent._speak_reply.await_args.args[0]
        assert spoken_text == "Sorry, I lost my train of thought — could you say that again?"

    asyncio.run(_run())


def test_silent_failure_with_no_exception_logs_as_error_not_exception():
    async def _silently_returns_none(*args, **kwargs):
        return None, False

    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-silentfail")
        agent._consume_turn_stream = _silently_returns_none
        _wire_common_mocks(agent)

        records = []
        sink_id = logger.add(lambda msg: records.append(msg.record), level="ERROR")
        try:
            await agent._handle_real_turn("hello", FrameDirection.DOWNSTREAM)
        finally:
            logger.remove(sink_id)

        assert len(records) == 1, f"expected exactly one error record, got: {records}"
        # No exception occurred here - must not be mislabeled as one.
        assert records[0]["exception"] is None
        assert records[0]["level"].name == "ERROR"

        agent._speak_reply.assert_awaited()
        spoken_text = agent._speak_reply.await_args.args[0]
        assert spoken_text == "Sorry, I lost my train of thought — could you say that again?"

    asyncio.run(_run())
