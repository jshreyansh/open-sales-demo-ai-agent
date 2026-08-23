"""Tests for P1 #3: adaptive stall-backstop grace.

Background (production-readiness review, 2026-08-23): the flat
PENDING_FRAGMENT_STALL_GRACE_SECS = 4.0 fires ~once per 6.9 turns across
real calls and cuts a genuinely still-forming thought in roughly 4 of
every 10 firings. Root-cause split found in that review: 62% of firings
never even reach a multi-fragment state — Smart Turn simply never resolves
the verdict to COMPLETE, a classifier-calibration issue explicitly out of
scope here. The other 38% are turns that have already produced multiple
fragments and are still being built — that's what _stall_backstop_grace()
targets, using ONLY this turn's own _burst_fragments (never session
history, per the same review's explicit instruction not to mix this with
the separate, dormant FAST_COMMIT/_fragmentation_protection mechanism).

Required invariants, tested explicitly below:
1. A turn with more demonstrated fragmentation receives more grace.
2. A clean/single-fragment turn is completely unaffected (identical to the
   old flat behavior) -- this is the majority case and must not regress.
3. The grace has a hard ceiling -- no amount of fragmentation earns
   unlimited patience.
4. The two integration tests confirm the ceiling is actually load-bearing
   in the real polling loop, not just in the formula: a multi-fragment
   turn held past the OLD flat 4.0s must still be waiting, and must
   eventually flush once truly past ITS OWN adaptive ceiling.
"""
from __future__ import annotations

import asyncio
import time

from src.voice.agent_processor import (
    PENDING_FRAGMENT_STALL_GRACE_MAX_SECS,
    PENDING_FRAGMENT_STALL_GRACE_SECS,
    PENDING_FRAGMENT_STALL_GRACE_STEP_SECS,
    PENDING_FRAGMENT_WATCHDOG_INTERVAL_SECS,
    AgentRuntimeProcessor,
)


async def _noop_handle_real_turn(*args, **kwargs):
    return None


def _make_agent(visitor_id: str) -> AgentRuntimeProcessor:
    agent = AgentRuntimeProcessor(visitor_id)
    agent._handle_real_turn = _noop_handle_real_turn
    return agent


# --- Unit tests on the formula itself --------------------------------------


def test_single_fragment_is_unchanged_from_the_old_flat_value():
    agent = _make_agent("test-grace-single-fragment")
    agent._burst_fragments = 0
    assert agent._stall_backstop_grace() == PENDING_FRAGMENT_STALL_GRACE_SECS
    agent._burst_fragments = 1
    assert agent._stall_backstop_grace() == PENDING_FRAGMENT_STALL_GRACE_SECS


def test_more_fragments_means_more_grace_monotonically():
    agent = _make_agent("test-grace-monotonic")
    previous = agent._stall_backstop_grace()
    for fragments in range(1, 12):
        agent._burst_fragments = fragments
        current = agent._stall_backstop_grace()
        assert current >= previous, f"grace decreased at fragments={fragments}"
        previous = current


def test_grace_has_a_hard_ceiling_regardless_of_fragment_count():
    agent = _make_agent("test-grace-ceiling")
    for fragments in (5, 20, 100, 10_000):
        agent._burst_fragments = fragments
        assert agent._stall_backstop_grace() <= PENDING_FRAGMENT_STALL_GRACE_MAX_SECS
    agent._burst_fragments = 10_000
    assert agent._stall_backstop_grace() == PENDING_FRAGMENT_STALL_GRACE_MAX_SECS


def test_grace_step_matches_the_documented_formula():
    agent = _make_agent("test-grace-formula")
    agent._burst_fragments = 3
    expected = min(
        PENDING_FRAGMENT_STALL_GRACE_SECS + PENDING_FRAGMENT_STALL_GRACE_STEP_SECS * 2,
        PENDING_FRAGMENT_STALL_GRACE_MAX_SECS,
    )
    assert agent._stall_backstop_grace() == expected


# --- Integration tests through the real polling loop -----------------------


def _wire_for_backstop_path(agent: AgentRuntimeProcessor, held_for_secs: float) -> None:
    agent._burst_fragments = 3
    agent._pending_fragment_text = "still building this thought"
    agent._pending_interruption_text = None
    agent._turn_in_progress = False
    agent._bot_speaking = False
    agent._user_speaking = False
    agent._interrupted_at = None
    agent._fragment_backchannel_sent = True  # skip the backchannel branch
    agent._last_turn_incomplete = True  # force the backstop path, not settle
    now = time.monotonic()
    agent._last_fragment_activity = now - held_for_secs
    agent._last_user_speech_ended_at = now - held_for_secs
    agent._turn_floor_started_at = now - held_for_secs - 5


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


def test_multi_fragment_turn_does_not_flush_at_the_old_flat_grace_point():
    # 3 fragments -> adaptive grace = 4.0 + 1.0*2 = 6.0s. Held for 4.5s:
    # past the OLD flat 4.0s, still well under the new adaptive ceiling.
    async def _run():
        agent = _make_agent("test-grace-not-yet")
        _wire_for_backstop_path(agent, held_for_secs=4.5)
        await _run_watchdog_briefly(agent)
        assert agent._pending_fragment_text == "still building this thought", (
            "flushed too early -- adaptive grace was not applied"
        )

    asyncio.run(_run())


def test_multi_fragment_turn_flushes_once_past_its_own_adaptive_ceiling():
    async def _run():
        agent = _make_agent("test-grace-flushes")
        _wire_for_backstop_path(agent, held_for_secs=6.5)  # past the 6.0s ceiling
        await _run_watchdog_briefly(agent)
        assert agent._pending_fragment_text == ""
        assert agent._pending_released_by == "stall_backstop"

    asyncio.run(_run())
