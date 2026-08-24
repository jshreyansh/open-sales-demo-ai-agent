"""Regression tests for the walkthrough_awaiting_answer latch getting stuck
despite the model's own current turn proving forward progress — confirmed
live TWICE, in two different calls, at two different granularities:

1. call 535e606c, 2026-08-24 ~10:22 UTC, step 8 (sub-action level): a
   narration reply ended on "Does that map to where you're at?", the
   prospect answered "Yes.", and the very next turn fired a genuinely new
   step-generate sub-action — objective proof forward progress resumed —
   while the latch stayed stuck for 16s until the prospect asked why
   nothing was happening.
2. call 66da2724, 2026-08-24 ~02:47-02:48 UTC, step 10 (macro-step level):
   same shape, but the proof was the walkthrough advancing from step 10 to
   11 instead of a sub-action firing. The 45s stall watchdog had to force-
   clear it.

In both cases the ONLY things wired to release this latch were a bare
continuation phrase or the auto-continue cap's own specific confirmation
(_is_permission_to_continue's `asked` gate) — a short affirmative
answering an ORDINARY question (not the cap's own) satisfies neither, even
when the model's own next action already proves the pause is resolved.

Fix: trust the model's own current-turn result as proof, not the
prospect's exact wording — clear the latch if this turn either fires a
step 8/9 sub-action that hasn't already fired this run, or advances
session.walkthrough_step to a genuinely later value.
"""
from __future__ import annotations

from src.agent.runtime import _finalize_turn
from src.context.store import SessionState


def test_stuck_latch_clears_when_this_turn_fires_a_new_sub_action():
    session = SessionState()
    session.walkthrough_step = 8
    session.walkthrough_awaiting_answer = True
    session.walkthrough_fired_actions = {
        "step-source", "select-source-dossier", "select-source-news", "select-source-custom",
        "step-brief", "brief-audience", "brief-voice-language", "brief-brand-product",
        "step-script", "generate-script", "step-scenes",
    }
    result = {
        "reply": "This is the Generate stage — pick your render tier here, HD or premium cinematic, before we fire it off.",
        "action": {"page": "magicreel-studio", "component": "wizard", "method": "step-generate"},
    }

    _finalize_turn(session, result, persist=False)

    assert session.walkthrough_awaiting_answer is False


def test_latch_stays_set_when_no_new_action_fires_this_turn():
    session = SessionState()
    session.walkthrough_step = 8
    session.walkthrough_awaiting_answer = True
    session.walkthrough_fired_actions = {"step-source"}
    result = {"reply": "Sure, happy to explain that further.", "action": None}

    _finalize_turn(session, result, persist=False)

    assert session.walkthrough_awaiting_answer is True


def test_does_not_clear_for_a_revisit_of_an_already_fired_action():
    session = SessionState()
    session.walkthrough_step = 8
    session.walkthrough_awaiting_answer = True
    session.walkthrough_fired_actions = {"step-source", "select-source-dossier"}
    result = {
        "reply": "Sure, here's the dossier option again.",
        "action": {"page": "magicreel-studio", "component": "wizard", "method": "select-source-dossier"},
    }

    _finalize_turn(session, result, persist=False)

    assert session.walkthrough_awaiting_answer is True


def test_relatches_if_the_same_turn_also_ends_on_a_fresh_question():
    """Ordering check: the release must run BEFORE floor handover, so a
    turn that both makes real progress AND asks a brand new question still
    correctly holds for that new question."""
    session = SessionState()
    session.walkthrough_step = 8
    session.walkthrough_awaiting_answer = True
    session.walkthrough_fired_actions = {"step-source"}
    result = {
        "reply": "The dossier option pulls from your approved claims library. Want me to keep going?",
        "action": {"page": "magicreel-studio", "component": "wizard", "method": "select-source-dossier"},
    }

    _finalize_turn(session, result, persist=False)

    assert session.walkthrough_awaiting_answer is True


def test_action_alone_outside_steps_eight_and_nine_does_not_clear_the_latch():
    """A highlight/open action on a non-wizard step is not, by itself,
    proof of forward progress the way a NEW sub-action inside steps 8/9
    is — only an actual step advance counts outside the wizard."""
    session = SessionState()
    session.walkthrough_step = 3
    session.walkthrough_awaiting_answer = True
    result = {"reply": "Sure.", "action": {"page": "home", "component": "hero", "method": "highlight"}}

    _finalize_turn(session, result, persist=False)

    assert session.walkthrough_awaiting_answer is True
    assert session.walkthrough_step == 3


def test_stuck_latch_clears_when_this_turn_advances_the_macro_step():
    """Real call 66da2724, ~02:48:30 UTC: step 10 -> 11 while the latch was
    stuck, at the macro-step level rather than a step 8/9 sub-action."""
    session = SessionState()
    session.walkthrough_step = 10
    session.walkthrough_awaiting_answer = True
    result = {
        "reply": "This is every video generated on the platform so far — you can see the finished pieces.",
        "action": {"page": "content-library", "component": "grid", "method": "highlight"},
        "walkthrough_step": 11,
    }

    _finalize_turn(session, result, persist=False)

    assert session.walkthrough_step == 11
    assert session.walkthrough_awaiting_answer is False


def test_latch_stays_set_when_the_macro_step_does_not_advance():
    session = SessionState()
    session.walkthrough_step = 10
    session.walkthrough_awaiting_answer = True
    result = {"reply": "Sure, let me explain that further.", "action": None}

    _finalize_turn(session, result, persist=False)

    assert session.walkthrough_step == 10
    assert session.walkthrough_awaiting_answer is True


def test_relatches_if_macro_step_advance_also_ends_on_a_fresh_question():
    """Same ordering guarantee as the sub-action case, at the macro-step
    level: real progress plus a brand new question must still hold for
    that new question, matching the real transcript verbatim (66da2724,
    ~02:48:30 UTC) where this exact reply also asked 'Want one to play?'."""
    session = SessionState()
    session.walkthrough_step = 10
    session.walkthrough_awaiting_answer = True
    result = {
        "reply": "This is every video generated on the platform so far. Want one to play?",
        "action": {"page": "content-library", "component": "grid", "method": "highlight"},
        "walkthrough_step": 11,
    }

    _finalize_turn(session, result, persist=False)

    assert session.walkthrough_step == 11
    assert session.walkthrough_awaiting_answer is True


def test_does_not_clear_when_the_latch_was_not_actually_set():
    """No-op check: nothing should break when this fires against a session
    where the latch was already False."""
    session = SessionState()
    session.walkthrough_step = 8
    session.walkthrough_awaiting_answer = False
    session.walkthrough_fired_actions = {"step-source"}
    result = {
        "reply": "The dossier option pulls from your approved claims library.",
        "action": {"page": "magicreel-studio", "component": "wizard", "method": "select-source-dossier"},
    }

    _finalize_turn(session, result, persist=False)

    assert session.walkthrough_awaiting_answer is False
