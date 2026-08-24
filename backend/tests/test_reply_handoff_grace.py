"""Regression tests for the reply-handoff grace (production issue #2).

Background (real call 66da2724, 2026-08-24): a stashed fragment ("for us to
look for, like, a new line") settled — its own commit window fully elapsed
— while the agent was still mid-way through an unrelated ~30-second reply.
The watchdog that drains settled fragments checks elapsed-quiet-time against
the fragment's OWN clock, which had already been satisfied for many seconds;
the instant the long reply finished and _bot_speaking flipped false, the
very next 0.25s poll tick fired the next reply immediately. Two full bot
turns landed back to back with nothing in between, which read as the agent
not letting the prospect talk rather than a normal conversation.

Fix: track when the bot's OWN speech last actually ended
(_last_bot_speech_ended_at) and require a minimum breath
(REPLY_HANDOFF_GRACE_SECS) since then before the watchdog is allowed to
drain an already-settled fragment or deferred interruption — regardless of
how long ago the fragment's own timer expired.
"""
from __future__ import annotations

import asyncio
import time

from src.voice.agent_processor import (
    PENDING_FRAGMENT_WATCHDOG_INTERVAL_SECS,
    REPLY_HANDOFF_GRACE_SECS,
    AgentRuntimeProcessor,
)


async def _noop_handle_real_turn(*args, **kwargs):
    return None


def _make_agent(visitor_id: str) -> AgentRuntimeProcessor:
    agent = AgentRuntimeProcessor(visitor_id)
    agent._handle_real_turn = _noop_handle_real_turn
    return agent


async def _run_watchdog_briefly(agent: AgentRuntimeProcessor) -> None:
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


# --- Unit tests on the grace check itself -----------------------------------


def test_grace_elapsed_true_before_the_bot_has_ever_spoken():
    agent = _make_agent("test-handoff-never-spoken")
    assert agent._reply_handoff_grace_elapsed() is True


def test_grace_not_elapsed_immediately_after_the_bot_stops_speaking():
    agent = _make_agent("test-handoff-just-stopped")
    agent._last_bot_speech_ended_at = time.monotonic()
    assert agent._reply_handoff_grace_elapsed() is False


def test_grace_elapsed_once_the_full_window_passes():
    agent = _make_agent("test-handoff-window-passed")
    agent._last_bot_speech_ended_at = time.monotonic() - (REPLY_HANDOFF_GRACE_SECS + 0.1)
    assert agent._reply_handoff_grace_elapsed() is True


# --- Integration: the real polling loop, reproducing the exact call --------


def _wire_settled_fragment(agent: AgentRuntimeProcessor, bot_stopped_secs_ago: float) -> None:
    agent._pending_fragment_text = "for us to look for, like, a new line."
    agent._pending_interruption_text = None
    agent._turn_in_progress = False
    agent._bot_speaking = False
    agent._user_speaking = False
    agent._interrupted_at = None
    agent._last_turn_incomplete = False  # Smart Turn called it COMPLETE
    agent._fragment_backchannel_sent = True
    now = time.monotonic()
    # The fragment's OWN commit window is satisfied many times over —
    # exactly the "settled while the bot was still talking" scenario.
    agent._last_user_speech_ended_at = now - 30.0
    agent._last_fragment_activity = now - 30.0
    agent._turn_floor_started_at = now - 35.0
    agent._last_bot_speech_ended_at = now - bot_stopped_secs_ago


def test_settled_fragment_does_not_fire_the_instant_the_bot_stops_talking():
    async def _run():
        agent = _make_agent("test-handoff-holds")
        _wire_settled_fragment(agent, bot_stopped_secs_ago=0.05)
        await _run_watchdog_briefly(agent)
        assert agent._pending_fragment_text == "for us to look for, like, a new line.", (
            "fired before the reply-handoff grace elapsed"
        )

    asyncio.run(_run())


def test_settled_fragment_fires_once_the_handoff_grace_elapses():
    async def _run():
        agent = _make_agent("test-handoff-fires")
        _wire_settled_fragment(agent, bot_stopped_secs_ago=REPLY_HANDOFF_GRACE_SECS + 0.3)
        await _run_watchdog_briefly(agent)
        assert agent._pending_fragment_text == ""
        assert agent._pending_released_by == "settle"

    asyncio.run(_run())


def test_grace_does_not_apply_before_the_bot_has_ever_spoken_this_call():
    """A first-turn fragment (bot hasn't spoken yet) must not be held back
    by a grace period that has nothing to measure from."""

    async def _run():
        agent = _make_agent("test-handoff-first-turn")
        _wire_settled_fragment(agent, bot_stopped_secs_ago=0)
        agent._last_bot_speech_ended_at = None
        await _run_watchdog_briefly(agent)
        assert agent._pending_fragment_text == ""
        assert agent._pending_released_by == "settle"

    asyncio.run(_run())
