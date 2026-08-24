"""Tests for the filler/backchannel tuning pass:

1. "Mmm —" / "Mm." removed from every pool — a real prospect complaint,
   twice, about that specific word's tone.
2. Every filler and backchannel now carries an explicit neutral emotion
   tag (Cartesia's own docs: prosody is inferred from transcript context,
   and an isolated short utterance has almost none, so it was previously
   unsteered and inconsistent).
3. A cooldown between any two short bridging utterances (filler or
   backchannel, either order) — confirmed live: a backchannel and a
   filler landed close together and read as stammering, not two separate
   deliberate acknowledgments.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

from pipecat.processors.frame_processor import FrameDirection

from src.voice.agent_processor import (
    BACKCHANNELS,
    FLOOR_FILLERS,
    THINKING_FILLERS,
    AgentRuntimeProcessor,
    _CALM_FILLER_EMOTION_TAG,
)


def test_no_isolated_mmm_in_any_pool():
    for pool in (THINKING_FILLERS, FLOOR_FILLERS, BACKCHANNELS):
        assert "Mmm —" not in pool
        assert "Mm." not in pool


def _wire_common_mocks(agent: AgentRuntimeProcessor) -> None:
    agent._consume_turn_stream = AsyncMock(return_value=({"reply": "ok", "action": None}, False))
    agent._speak = AsyncMock()
    agent._speak_reply = AsyncMock()
    agent._advance_after_turn = AsyncMock()
    agent._amend_interrupted_turn = AsyncMock()
    agent._report_reply = AsyncMock()
    agent._report_action = AsyncMock()


def test_filler_skipped_when_a_short_utterance_just_fired():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-filler-cooldown-active")
        _wire_common_mocks(agent)
        agent._last_short_utterance_at = time.monotonic()  # just happened

        await agent._handle_real_turn("hello", FrameDirection.DOWNSTREAM)

        agent._speak.assert_not_called()

    asyncio.run(_run())


def test_filler_fires_with_emotion_tag_when_cooldown_clear():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-filler-cooldown-clear")
        _wire_common_mocks(agent)
        agent._last_short_utterance_at = 0.0  # long ago

        await agent._handle_real_turn("hello", FrameDirection.DOWNSTREAM)

        agent._speak.assert_awaited_once()
        spoken_text = agent._speak.await_args.args[0]
        assert spoken_text.startswith(_CALM_FILLER_EMOTION_TAG)

    asyncio.run(_run())


def _wire_for_backchannel_path(agent: AgentRuntimeProcessor) -> None:
    agent._handle_real_turn = AsyncMock()
    agent._burst_fragments = 1
    agent._pending_fragment_text = "still talking"
    agent._pending_interruption_text = None
    agent._turn_in_progress = False
    agent._bot_speaking = False
    agent._user_speaking = False
    agent._interrupted_at = None
    agent._last_turn_incomplete = True  # skip the settle branch
    agent._fragment_backchannel_sent = False
    now = time.monotonic()
    agent._turn_floor_started_at = now - 4.0  # >= BACKCHANNEL_MIN_FLOOR_HOLD_SECS
    agent._last_user_speech_ended_at = now - 0.5
    agent._last_fragment_activity = now - 1.0  # well under the stall grace


async def _run_watchdog_briefly(agent: AgentRuntimeProcessor) -> None:
    from src.voice.agent_processor import PENDING_FRAGMENT_WATCHDOG_INTERVAL_SECS

    task = asyncio.create_task(agent._watch_pending_fragment_stall())
    try:
        await asyncio.wait_for(task, timeout=PENDING_FRAGMENT_WATCHDOG_INTERVAL_SECS * 3)
    except asyncio.TimeoutError:
        pass
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def test_backchannel_skipped_when_a_filler_just_fired():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-backchannel-cooldown-active")
        agent._speak_without_activity_bump = AsyncMock()
        _wire_for_backchannel_path(agent)
        agent._last_short_utterance_at = time.monotonic()  # a filler just fired

        await _run_watchdog_briefly(agent)

        agent._speak_without_activity_bump.assert_not_called()
        assert agent._fragment_backchannel_sent is False, (
            "must not be marked sent when skipped by cooldown -- this hold may "
            "still be worth a nod once the cooldown clears"
        )

    asyncio.run(_run())


def test_backchannel_fires_with_emotion_tag_when_cooldown_clear():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-backchannel-cooldown-clear")
        agent._speak_without_activity_bump = AsyncMock()
        _wire_for_backchannel_path(agent)
        agent._last_short_utterance_at = 0.0  # long ago

        await _run_watchdog_briefly(agent)

        agent._speak_without_activity_bump.assert_awaited_once()
        spoken_text = agent._speak_without_activity_bump.await_args.args[0]
        assert spoken_text.startswith(_CALM_FILLER_EMOTION_TAG)
        assert agent._fragment_backchannel_sent is True

    asyncio.run(_run())
