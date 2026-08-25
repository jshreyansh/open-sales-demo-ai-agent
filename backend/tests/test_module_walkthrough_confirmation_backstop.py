"""Regression test for the single-module walkthrough never actually
starting — confirmed live, call 631341bd, 2026-08-25 ~06:39 UTC: the
prospect said "show me how to create a MagicAvatar," the model opened the
launchpad and asked "Want to walk through it?" (a real, deliberate action
plus a deferring question — exactly instruction 0c's documented pattern).
The prospect said "Yeah." The model then narrated straight into the Brief
step, firing a real action on magicavatar-studio — but never set
start_module_walkthrough on either turn. session.walkthrough_step stayed
None throughout, so the auto-continue scheduler (gated on it) never had
anything to schedule, and the tour went silent until the prospect hung up.

Root cause: pending_walkthrough_request (the existing backstop) is
re-derived fresh from each turn's raw text by _begin_turn and is gone by
the time a bare "Yeah" answers the model's own deferred question — nothing
previously carried the "we just asked permission for module X" fact
forward to the confirmation turn.

Fix: walkthrough_module_awaiting_confirmation, armed by _finalize_turn
when it sees the model defer with a question, resolved on the very next
turn if that turn's own action lands on the matching module's studio page
(corroboration against a genuine decline).
"""
from __future__ import annotations

import asyncio

from src.agent.runtime import _finalize_turn
from src.context.store import SessionState


def test_module_offer_deferred_with_a_question_arms_confirmation():
    session = SessionState()
    session.pending_walkthrough_request = "magicavatar"
    result = {
        "reply": "So this is the MagicAvatar launchpad — it's a three-stage flow. Want to walk through it?",
        "action": {"page": "magicavatar-studio", "component": "launchpad", "method": "open"},
    }

    asyncio.run(_finalize_turn(session, result, persist=False))

    assert session.walkthrough_step is None
    assert session.walkthrough_module_awaiting_confirmation == "magicavatar"


def test_confirmation_turn_starts_the_module_walkthrough_when_action_matches():
    """Reproduces the exact real sequence: the offer turn armed the
    confirmation, then the prospect's bare "Yeah" turn narrates into the
    Brief step without setting start_module_walkthrough itself — the
    backstop must catch this and actually start the module walkthrough."""
    session = SessionState()
    session.walkthrough_module_awaiting_confirmation = "magicavatar"
    result = {
        "reply": "This is the Master wizard — four steps: Brief, Scenes, Options, and Generate.",
        "action": {"page": "magicavatar-studio", "component": "wizard", "method": "step-brief"},
    }

    asyncio.run(_finalize_turn(session, result, persist=False))

    assert session.walkthrough_step == 9
    assert session.walkthrough_scope_end == 9
    assert session.walkthrough_module_awaiting_confirmation is None


def test_confirmation_does_not_fire_when_the_next_action_goes_elsewhere():
    """A genuine decline: the prospect's answer leads the model somewhere
    unrelated (or nowhere at all) instead of into the requested module —
    must not be force-started underneath that."""
    session = SessionState()
    session.walkthrough_module_awaiting_confirmation = "magicavatar"
    result = {
        "reply": "No problem — let's talk pricing instead.",
        "action": {"page": "settings-plans", "component": "plans", "method": "highlight"},
    }

    asyncio.run(_finalize_turn(session, result, persist=False))

    assert session.walkthrough_step is None


def test_confirmation_is_a_no_op_when_nothing_was_armed():
    session = SessionState()
    result = {"reply": "Sure, happy to help.", "action": None}

    asyncio.run(_finalize_turn(session, result, persist=False))

    assert session.walkthrough_step is None
    assert session.walkthrough_module_awaiting_confirmation is None


def test_magicreel_offer_and_confirmation_work_the_same_as_magicavatar():
    """Proves symmetry rather than assuming it — the mechanism is entirely
    data-driven off _MODULE_STUDIO_PAGE / the same {"magicreel": 8,
    "magicavatar": 9} map, but MagicAvatar is the only one a real call
    exercised, so MagicReel gets its own explicit pass end to end."""
    session = SessionState()
    session.pending_walkthrough_request = "magicreel"
    offer = {
        "reply": "So this is the MagicReel studio — a five-stage flow. Want to walk through it?",
        "action": {"page": "magicreel-studio", "component": "launchpad", "method": "open"},
    }
    asyncio.run(_finalize_turn(session, offer, persist=False))
    assert session.walkthrough_step is None
    assert session.walkthrough_module_awaiting_confirmation == "magicreel"

    confirm = {
        "reply": "This is the Source step — pick where the video pulls from.",
        "action": {"page": "magicreel-studio", "component": "wizard", "method": "step-source"},
    }
    asyncio.run(_finalize_turn(session, confirm, persist=False))
    assert session.walkthrough_step == 8
    assert session.walkthrough_scope_end == 8
    assert session.walkthrough_module_awaiting_confirmation is None


def test_does_not_interfere_when_the_model_sets_start_module_walkthrough_itself():
    """The backstop must stay completely out of the way on the happy path —
    if the model correctly sets start_module_walkthrough on the offer turn
    itself (no deferred question needed), nothing here should ever arm, and
    the existing model_field activation proceeds exactly as before this
    change."""
    session = SessionState()
    session.pending_walkthrough_request = "magicavatar"
    result = {
        "reply": "Let's build a MagicAvatar together.",
        "action": {"page": "magicavatar-studio", "component": "launchpad", "method": "open"},
        "start_module_walkthrough": "magicavatar",
    }

    asyncio.run(_finalize_turn(session, result, persist=False))

    assert session.walkthrough_step == 9
    assert session.walkthrough_module_awaiting_confirmation is None


def test_does_not_arm_for_a_full_tour_request():
    """Instruction 0c's deferred-question pattern is specifically about
    single-MODULE ambiguity — a full-tour request has no equivalent
    deferred-confirmation gap and must never arm this mechanism."""
    session = SessionState()
    session.pending_walkthrough_request = "full"
    result = {
        "reply": "Happy to give you the full tour. Want me to start now?",
        "action": None,
    }

    asyncio.run(_finalize_turn(session, result, persist=False))

    assert session.walkthrough_module_awaiting_confirmation is None


def test_does_not_interfere_with_an_already_active_full_tour_reaching_its_own_module_step():
    """The full platform tour naturally passes through steps 8/9 (MagicReel/
    MagicAvatar) on its own — this mechanism must never touch that, since
    it only arms via a fresh pending_walkthrough_request, never via normal
    step progression."""
    session = SessionState()
    session.walkthrough_step = 7
    result = {
        "reply": "This is MagicReel — short-form video built from your brand dossier.",
        "action": {"page": "magicreel-studio", "component": "launchpad", "method": "open"},
        "walkthrough_step": 8,
    }

    asyncio.run(_finalize_turn(session, result, persist=False))

    assert session.walkthrough_step == 8
    assert session.walkthrough_scope_end is None
    assert session.walkthrough_module_awaiting_confirmation is None
