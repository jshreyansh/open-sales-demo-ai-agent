"""Regression test for the walkthrough ending with no closing question —
confirmed live, call 631341bd, 2026-08-25 ~05:42 UTC: the Home wrap-up
step's own guidance (walkthrough.py) already tells the model to ask
whether question 5 (connecting with a rep for next steps) still hasn't
come up, but the model's actual reply just said "That's the whole platform
in a nutshell" and stopped — no question, no action. The prospect hung up
27 seconds later.

Fix: a deterministic backstop in _finalize_turn — when end_walkthrough
resolves true this turn and session.qual_next_step_response is still
empty, append a fixed closing question to the reply rather than trusting
the model to remember on this one call-critical turn.
"""
from __future__ import annotations

import asyncio

from src.agent.runtime import _finalize_turn
from src.context.store import SessionState


def test_end_walkthrough_appends_closing_question_when_q5_never_came_up():
    session = SessionState()
    session.walkthrough_step = 13
    session.qual_next_step_response = ""
    result = {
        "reply": "That's the whole platform in a nutshell.",
        "action": {"page": "home", "component": "insights", "method": "highlight"},
        "end_walkthrough": True,
    }

    final = asyncio.run(_finalize_turn(session, result, persist=False))

    assert "next steps" in final["reply"].lower()
    assert final["reply"].startswith("That's the whole platform in a nutshell.")
    assert session.walkthrough_step is None


def test_end_walkthrough_leaves_reply_untouched_when_q5_already_answered():
    session = SessionState()
    session.walkthrough_step = 13
    session.qual_next_step_response = "Yes, connect me with a rep"
    result = {
        "reply": "That's the whole platform in a nutshell.",
        "action": {"page": "home", "component": "insights", "method": "highlight"},
        "end_walkthrough": True,
    }

    final = asyncio.run(_finalize_turn(session, result, persist=False))

    assert final["reply"] == "That's the whole platform in a nutshell."


def test_reply_untouched_when_walkthrough_does_not_end():
    session = SessionState()
    session.walkthrough_step = 8
    session.qual_next_step_response = ""
    result = {
        "reply": "This is the Generate stage.",
        "action": {"page": "magicreel-studio", "component": "wizard", "method": "step-generate"},
    }

    final = asyncio.run(_finalize_turn(session, result, persist=False))

    assert final["reply"] == "This is the Generate stage."
