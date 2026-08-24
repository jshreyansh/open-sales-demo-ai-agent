"""Regression test for the prefetch clone leaking walkthrough_fired_actions
into the real session (production issue #2, real call ccab533a, 2026-08-24).

Background: _start_prefetch builds a disposable session clone via
dataclasses.replace(session, history=list(session.history)) so a
speculatively-generated beat that's never actually spoken can't pollute the
real session. history got its own list; walkthrough_fired_actions (also a
mutable container) did not, so the clone's set was literally the same
object as the real session's. run_walkthrough_continuation's own
_finalize_turn adds the beat's sub-action to that set the instant it's
computed, before anything is spoken, so a prefetched-but-never-consumed
beat permanently marked its sub-action as fired on the REAL session.

Confirmed live: select-source-custom was prefetched right as
select-source-news finished; the auto-continue beat cap hit first and
returned the floor before that prefetched beat was ever consumed; the tour
then skipped straight from select-source-news to step-brief with no
order-violation warning, because _enforce_step_order's remaining-actions
check correctly (given the corrupted state) saw select-source-custom as
already done.

Fix: give walkthrough_fired_actions its own set() in the clone, the same
way history already gets its own list().
"""
from __future__ import annotations

import asyncio

from src.voice.agent_processor import AgentRuntimeProcessor
from src.context.store import SessionState


def test_prefetch_clone_does_not_share_fired_actions_set_with_real_session():
    async def _run():
        agent = AgentRuntimeProcessor("test-prefetch-fired-actions-isolation")
        session = SessionState()
        session.walkthrough_step = 8
        session.walkthrough_fired_actions = {"step-source", "select-source-dossier", "select-source-news"}

        agent._start_prefetch(session)
        clone = agent._prefetch_session_clone
        assert clone is not None

        # The bug: this used to be the exact same object.
        assert clone.walkthrough_fired_actions is not session.walkthrough_fired_actions

        # Simulate the speculative beat committing "select-source-custom" as
        # fired on the clone (what _finalize_turn does inside
        # run_walkthrough_continuation the instant it decides that beat,
        # before it's ever spoken) — this must never reach the real session.
        clone.walkthrough_fired_actions.add("select-source-custom")
        assert "select-source-custom" not in session.walkthrough_fired_actions

        # Never let the background LLM call actually run; we only care
        # about the clone's construction, not its content.
        agent._prefetch_task.cancel()
        try:
            await agent._prefetch_task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())


def test_prefetch_clone_still_gets_its_own_history_list():
    """history's existing isolation must survive the fix untouched."""

    async def _run():
        agent = AgentRuntimeProcessor("test-prefetch-history-isolation")
        session = SessionState()
        session.walkthrough_step = 8

        agent._start_prefetch(session)
        clone = agent._prefetch_session_clone
        assert clone is not None
        assert clone.history is not session.history

        agent._prefetch_task.cancel()
        try:
            await agent._prefetch_task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())
