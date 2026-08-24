"""Regression test for the walkthrough_awaiting_answer sticky-latch stall
(production issue #2, real call ccab533a, 2026-08-24) — and, more broadly,
for a failure mode confirmed against production logs to have hit nearly
every walkthrough call over the preceding 5 days: "walkthrough latch stuck
for 45s" fired 42 times across 16 distinct visitor sessions (35ad314a,
71c3c369, 92a7ddaf, 7d0018d3, 1a059044, fdd45a9e, 5e1732cb, 073268f8,
0aa0aaeb, 8439c3af, be5a8774, 84938b9b, 3ea86675, d3f3b101, 66da2724,
ccab533a) between 2026-08-20 and 2026-08-24. This was the common case, not
an edge case.

Root cause: walkthrough_awaiting_answer is a sticky latch, cleared ONLY by
the model explicitly re-emitting "resume_walkthrough": true (see
runtime.py's _finalize_turn precedence chain). The auto-continue beat cap
sets this latch and asks "should I continue?" (_return_floor_after_beats);
when the prospect answers "keep going", the model correctly narrates the
next stage's content but does not reliably re-emit "resume_walkthrough" on
that same turn. With nothing else clearing it, _maybe_schedule_auto_continue
silently refuses to schedule anything further (dead air) until the 45s
watchdog backstop eventually force-clears it — by which point, in the
ccab533a call, the prospect had already had to ask "why did you stop?".

Fix: agent_processor.py already computes the one deterministic signal that
answers exactly this — _is_permission_to_continue(text, asked), where
`asked` is true only immediately after the code itself asked "should I
continue?" via _return_floor_after_beats. When that fires, the latch is now
cleared right there in code — the same established pattern _begin_turn's
walkthrough_user_stopped/_is_explicit_resume backstop already uses for the
sibling latch (added after testing showed the model doesn't reliably
re-affirm that one either).
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from pipecat.processors.frame_processor import FrameDirection

from src.context.store import get_session
from src.voice.agent_processor import AgentRuntimeProcessor


def _wire_common_mocks(agent: AgentRuntimeProcessor) -> None:
    agent._consume_turn_stream = AsyncMock(return_value=({"reply": "ok", "action": None}, False))
    agent._speak = AsyncMock()
    agent._speak_reply = AsyncMock()
    agent._advance_after_turn = AsyncMock()
    agent._amend_interrupted_turn = MagicMock()
    agent._report_reply = AsyncMock()
    agent._report_action = AsyncMock()


def test_confirmed_keep_going_clears_the_sticky_awaiting_answer_latch():
    """Reproduces the exact ccab533a sequence: cap hit -> latch set,
    "should I continue?" asked -> prospect says "No. I should continue." ->
    latch must clear right there, without waiting on the model to re-state
    "resume_walkthrough"."""

    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-keep-going-clears-latch")
        _wire_common_mocks(agent)
        session = get_session(agent._visitor_id)
        session.walkthrough_step = 8
        session.walkthrough_awaiting_answer = True
        agent._awaiting_continue_answer = True  # _return_floor_after_beats just asked

        await agent._handle_real_turn("No. I should continue.", FrameDirection.DOWNSTREAM)

        assert session.walkthrough_awaiting_answer is False

    asyncio.run(_run())


def test_bare_yes_also_clears_the_latch_when_the_agent_just_asked():
    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-bare-yes-clears-latch")
        _wire_common_mocks(agent)
        session = get_session(agent._visitor_id)
        session.walkthrough_step = 9
        session.walkthrough_awaiting_answer = True
        agent._awaiting_continue_answer = True

        await agent._handle_real_turn("Yes.", FrameDirection.DOWNSTREAM)

        assert session.walkthrough_awaiting_answer is False

    asyncio.run(_run())


def test_latch_is_left_alone_when_nothing_was_asked():
    """If the latch is set for an unrelated reason (a genuine mid-tour
    interruption the model is still handling) and the prospect's turn
    doesn't read as continuation permission, the fix must not clear it —
    only the model's own "resume_walkthrough" should, exactly as before
    this change."""

    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-latch-untouched")
        _wire_common_mocks(agent)
        session = get_session(agent._visitor_id)
        session.walkthrough_step = 8
        session.walkthrough_awaiting_answer = True
        agent._awaiting_continue_answer = False  # nothing was asked this turn

        await agent._handle_real_turn("What does MLR stand for?", FrameDirection.DOWNSTREAM)

        assert session.walkthrough_awaiting_answer is True

    asyncio.run(_run())


def test_real_question_does_not_clear_the_latch_even_if_agent_just_asked():
    """Answering "should I continue?" with a genuine question instead of a
    go-ahead must not be misread as permission."""

    async def _run():
        agent = AgentRuntimeProcessor("test-visitor-question-not-permission")
        _wire_common_mocks(agent)
        session = get_session(agent._visitor_id)
        session.walkthrough_step = 8
        session.walkthrough_awaiting_answer = True
        agent._awaiting_continue_answer = True

        await agent._handle_real_turn("What does MLR stand for?", FrameDirection.DOWNSTREAM)

        assert session.walkthrough_awaiting_answer is True

    asyncio.run(_run())
