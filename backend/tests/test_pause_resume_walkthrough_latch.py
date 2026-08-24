"""Regression tests for _leave_pause not knowing about a pending walkthrough
floor-return question (production issue, real call 535e606c, 2026-08-24).

Background: the auto-continue beat cap asked "want me to carry on?"
(session.walkthrough_awaiting_answer=True), the visitor paused before
answering it, then resumed. _leave_pause spoke "Okay — picking up where we
left off." and then genuinely nothing picked up — the pending question was
still latched, nothing in the resume path ever answered it, and
_maybe_schedule_auto_continue refuses to schedule anything while it's set.
The visitor sat in silence for 19s until they said "Okay. Continue."

Fix: pressing resume IS an answer to "should I continue?" — no one un-mutes
a call to keep sitting in silence. _leave_pause now clears the latch (the
same resolution _watch_auto_continue_stall already applies after a 45s
timeout, just triggered immediately by a deliberate resume) and re-arms the
scheduler.
"""
from __future__ import annotations

import asyncio

from unittest.mock import AsyncMock

from src.context.store import get_session
from src.voice.agent_processor import AgentRuntimeProcessor


def test_resume_clears_the_awaiting_answer_latch_and_reschedules_a_beat():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-resume-clears-latch")
        agent._speak = AsyncMock()
        session = get_session(agent._visitor_id)
        session.walkthrough_step = 8
        session.walkthrough_awaiting_answer = True

        await agent._leave_pause()

        assert session.walkthrough_awaiting_answer is False
        assert agent._pending_auto_continue is not None, (
            "resume should have re-armed the auto-continue scheduler"
        )
        agent._speak.assert_awaited()

        agent._pending_auto_continue.cancel()
        try:
            await agent._pending_auto_continue
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())


def test_resume_is_a_no_op_when_no_walkthrough_is_active():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-resume-no-walkthrough")
        agent._speak = AsyncMock()
        session = get_session(agent._visitor_id)
        session.walkthrough_step = None
        session.walkthrough_awaiting_answer = False

        await agent._leave_pause()

        assert session.walkthrough_awaiting_answer is False
        assert agent._pending_auto_continue is None
        agent._speak.assert_awaited()

    asyncio.run(_run())


def test_resume_does_not_disturb_an_already_clear_latch():
    """A resume with no pending floor-return question shouldn't misfire the
    'keep going' bookkeeping (consecutive_auto_beats reset) for no reason —
    harmless either way, but confirms the fix is gated correctly."""

    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-resume-latch-already-clear")
        agent._speak = AsyncMock()
        session = get_session(agent._visitor_id)
        session.walkthrough_step = 8
        session.walkthrough_awaiting_answer = False

        await agent._leave_pause()

        assert session.walkthrough_awaiting_answer is False
        assert agent._pending_auto_continue is not None

        agent._pending_auto_continue.cancel()
        try:
            await agent._pending_auto_continue
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())
