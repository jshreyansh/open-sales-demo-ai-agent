"""Regression test for the walkthrough_awaiting_answer latch getting SET
without anything left to answer — confirmed live, call 631341bd,
2026-08-25 ~05:39 UTC: the prospect said "Can you go back," the model
revisited an already-fired step-script sub-action and replied with a flat
statement ("Here's the Script stage again — the structure, length, and the
generated draft pull straight from the brief."), no question anywhere in
it — but also set walkthrough_awaiting_answer=true in its own tool output.
Nothing was left for the prospect to answer, so the auto-continue
scheduler (gated on this flag) never fired again, and the tour sat silent
for the full 45s stall-watchdog window before self-healing.

Root cause: walkthrough_awaiting_answer was fully model-elected — nothing
checked whether the model's own reply text actually handed the floor over
before trusting its claim. Fix: only honor the model's election when
corroborated by _reply_hands_over_the_floor (the same deterministic
"ends on a question" signal already used a few lines below to SET this
flag when the model forgets to ask it explicitly).
"""
from __future__ import annotations

import asyncio

from src.agent.runtime import _finalize_turn
from src.context.store import SessionState


def test_model_elected_pause_on_a_non_question_reply_is_ignored():
    """Reproduces 631341bd exactly: a revisit of an already-fired sub-action,
    a flat non-question reply, and the model claiming a pause anyway — the
    latch must NOT get stuck on nothing to answer."""
    session = SessionState()
    session.walkthrough_step = 8
    session.walkthrough_awaiting_answer = False
    session.walkthrough_fired_actions = {"step-source", "step-brief", "step-script"}
    result = {
        "reply": "Here's the Script stage again — the structure, length, and the generated draft pull straight from the brief.",
        "action": {"page": "magicreel-studio", "component": "wizard", "method": "step-script"},
        "walkthrough_awaiting_answer": True,
    }

    asyncio.run(_finalize_turn(session, result, persist=False))

    assert session.walkthrough_awaiting_answer is False


def test_model_elected_pause_on_a_genuine_question_still_latches():
    """No regression on the legitimate case: the model asking a real
    clarifying question and electing a pause must still hold the tour,
    exactly as before this fix."""
    session = SessionState()
    session.walkthrough_step = 8
    session.walkthrough_awaiting_answer = False
    session.walkthrough_fired_actions = {"step-source"}
    result = {
        "reply": "Quick check before I continue — do you want the HD tier or cinematic 4K?",
        "action": None,
        "walkthrough_awaiting_answer": True,
    }

    asyncio.run(_finalize_turn(session, result, persist=False))

    assert session.walkthrough_awaiting_answer is True
