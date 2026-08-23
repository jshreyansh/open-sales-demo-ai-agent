"""Regression test for the released_by=None gap fixed in agent_processor.py
(P1 #5): the plain deferred-interruption drain path — draining pending
interruption text when there was no pending fragment to merge it with —
used to leave TurnTelemetry.released_by at its default None because nothing
ever set it on that specific branch. Confirmed as turn 6's real release path
in session afe71838, so an unset released_by there was a real observability
gap, not a theoretical one.

Drives AgentRuntimeProcessor._watch_pending_fragment_stall directly rather
than through a full transport/pipeline: the plain-drain branch and its four
neighbours (fast_track, both merge paths, stall_backstop) all live in that
one polling loop, so isolating this branch means pre-seeding exactly the
state that routes into it and letting one loop iteration run.
"""
from __future__ import annotations

import asyncio
import time

from src.voice.agent_processor import (
    PENDING_FRAGMENT_WATCHDOG_INTERVAL_SECS,
    PENDING_INTERRUPTION_MAX_HOLD_SECS,
    AgentRuntimeProcessor,
)


async def _noop_handle_real_turn(*args, **kwargs):
    return None


def test_plain_deferred_interrupt_drain_sets_released_by():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-released-by")
        agent._telemetry_open()
        agent._handle_real_turn = _noop_handle_real_turn

        # Route into the plain-drain branch specifically: a pending
        # interruption old enough to have hit its MAX_HOLD deadline, and
        # nothing in the fragment buffer to merge it with (that's the
        # *other* branch, deferred_interrupt_merged_with_fragment, already
        # covered — this one was the gap).
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

        assert agent._telemetry is not None, "telemetry record should still be open"
        assert agent._telemetry.released_by == "deferred_interrupt_drain"

    asyncio.run(_run())
