"""Tests for the adaptive interaction policy (V1) — pace/action_bias
evidence counters, the explicit-demand backstop, and the pre-call
calibration prior.

Background: real call with Jai (2026-08-25), confirmed as his own
feedback — the agent over-explained, kept qualifying past obvious
impatience, and recognized "let's do the demo... I don't have time for
this" without reliably acting on it. This is the fix: a small, decaying
evidence-counter pipeline (same shape as agent_processor.py's
_fragmentation_protection/_interruption_protection) feeding a directive
note into the system prompt, plus an optional pre-call prior that seeds
the counters instead of starting cold.
"""
from __future__ import annotations

import asyncio

from src.agent.runtime import (
    ACTION_BIAS_EVIDENCE_THRESHOLD,
    PACE_EVIDENCE_THRESHOLD,
    _action_bias_state,
    _finalize_turn,
    _interaction_note,
    _pace_state,
    _update_interaction_evidence,
)
from src.context.store import SessionState, start_session


def test_a_single_short_reply_is_weak_evidence():
    session = SessionState()
    _update_interaction_evidence(session, "Okay.")
    assert _pace_state(session) == "normal"
    assert _action_bias_state(session) == "normal"


def test_several_consecutive_short_replies_cross_the_threshold():
    session = SessionState()
    for _ in range(PACE_EVIDENCE_THRESHOLD):
        _update_interaction_evidence(session, "Sure.")
    assert _pace_state(session) == "fast"
    assert _action_bias_state(session) == "high"


def test_a_long_reply_does_not_bump_evidence():
    session = SessionState()
    _update_interaction_evidence(
        session, "I'm trying to understand how the medical review workflow actually works for our team."
    )
    assert session.pace_evidence == 0
    assert session.action_bias_evidence == 0


def test_explicit_demand_alone_crosses_both_thresholds():
    session = SessionState()
    _update_interaction_evidence(session, "Let's do the demo. I don't have time for all this.")
    assert session.pending_action_demand is True
    assert _pace_state(session) == "fast"
    assert _action_bias_state(session) == "high"


def test_evidence_decays_after_several_quiet_turns():
    session = SessionState()
    for _ in range(PACE_EVIDENCE_THRESHOLD):
        _update_interaction_evidence(session, "Sure.")
    assert _pace_state(session) == "fast"

    for _ in range(20):
        _update_interaction_evidence(
            session, "Actually, tell me more about how the compliance review process works end to end."
        )
    assert _pace_state(session) == "normal"
    assert _action_bias_state(session) == "normal"


def test_interaction_note_empty_when_both_dimensions_normal():
    session = SessionState()
    assert _interaction_note(session) == ""


def test_interaction_note_includes_directive_on_explicit_demand():
    session = SessionState()
    _update_interaction_evidence(session, "Just show me already.")
    note = _interaction_note(session)
    assert "directive" in note.lower()
    assert "THIS TURN" in note


def test_finalize_turn_runs_cleanly_with_interaction_evidence_set():
    """The INTERACTION_STATE log line goes through loguru, not stdlib
    logging, so pytest's caplog can't observe it directly — this instead
    confirms _finalize_turn (which computes and logs it) doesn't raise with
    real evidence/demand state set, and that session state ends up correct."""
    session = SessionState()
    session.visitor_id = "test-visitor-interaction-log"
    _update_interaction_evidence(session, "Let's do the demo.")
    result = {"reply": "Sure, let's dive in.", "action": {"page": "content-studio", "component": "magicreel", "method": "open"}}

    final = asyncio.run(_finalize_turn(session, result, persist=False))

    assert final["reply"] == "Sure, let's dive in."
    assert _pace_state(session) == "fast"


def test_pace_prior_fast_seeds_both_counters_above_threshold():
    session = start_session("visitor-prior-fast", pace_prior="fast")
    assert _pace_state(session) == "fast"
    assert _action_bias_state(session) == "high"


def test_pace_prior_self_directed_seeds_only_action_bias():
    session = start_session("visitor-prior-self-directed", pace_prior="self_directed")
    assert _pace_state(session) == "normal"
    assert _action_bias_state(session) == "high"


def test_pace_prior_none_leaves_both_at_baseline():
    session = start_session("visitor-prior-none")
    assert _pace_state(session) == "normal"
    assert _action_bias_state(session) == "normal"
    assert session.pace_evidence == 0
    assert session.action_bias_evidence == 0
