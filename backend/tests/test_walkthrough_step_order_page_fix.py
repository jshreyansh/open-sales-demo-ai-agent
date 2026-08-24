"""Regression test for _enforce_step_order also fixing page/component.

Background (real call 66da2724, 2026-08-24): while on step 9 (MagicAvatar),
the model proposed action {"page": "magicreel-studio", "component": "wizard",
"method": "start-generation"} — an illegally-early sub-action (start-
generation before step-brief/scenes/options) AND the wrong page (MagicReel's,
not MagicAvatar's own magicavatar-studio) at the same time. The existing
order-correction only overwrote "method", producing
{"page": "magicreel-studio", "component": "wizard", "method": "step-brief"} —
a combination that points at nothing real, since MagicReel's own wizard
never registers a "step-brief" handler for MagicAvatar's Brief stage. That's
exactly why nothing changed on screen and the prospect had to say "go back."

MagicReel and MagicAvatar share the same sub-action vocabulary shape
(step-brief, step-generate, start-generation, ...), which is plausibly why
the model confuses the two pages while getting the sub-action name itself
right. Fix: WIZARD_PAGE_BY_STEP gives the correction the canonical
page/component for whichever step is actually active, so it corrects both.
"""
from __future__ import annotations

from src.agent.runtime import _enforce_step_order
from src.agent.walkthrough import WIZARD_PAGE_BY_STEP
from src.context.store import SessionState


def test_wrong_page_and_illegal_method_both_get_corrected_for_magicavatar():
    session = SessionState()
    session.walkthrough_step = 9
    proposed = {"page": "magicreel-studio", "component": "wizard", "method": "start-generation"}

    corrected, was_corrected = _enforce_step_order(session, proposed)

    assert was_corrected is True
    assert corrected == {"page": "magicavatar-studio", "component": "wizard", "method": "step-brief"}


def test_wrong_page_and_illegal_method_both_get_corrected_for_magicreel():
    session = SessionState()
    session.walkthrough_step = 8
    # Same confusion, opposite direction: naming MagicAvatar's page while on
    # MagicReel's own step.
    proposed = {"page": "magicavatar-studio", "component": "wizard", "method": "start-generation"}

    corrected, was_corrected = _enforce_step_order(session, proposed)

    assert was_corrected is True
    assert corrected == {"page": "magicreel-studio", "component": "wizard", "method": "step-source"}


def test_correct_page_is_left_untouched_when_only_method_needs_fixing():
    session = SessionState()
    session.walkthrough_step = 9
    proposed = {"page": "magicavatar-studio", "component": "wizard", "method": "start-generation"}

    corrected, was_corrected = _enforce_step_order(session, proposed)

    assert was_corrected is True
    assert corrected == {"page": "magicavatar-studio", "component": "wizard", "method": "step-brief"}


def test_legal_next_action_passes_through_unchanged():
    session = SessionState()
    session.walkthrough_step = 9
    proposed = {"page": "magicavatar-studio", "component": "wizard", "method": "step-brief"}

    corrected, was_corrected = _enforce_step_order(session, proposed)

    assert was_corrected is False
    assert corrected == proposed


def test_unrelated_action_is_out_of_scope_and_untouched():
    session = SessionState()
    session.walkthrough_step = 9
    proposed = {"page": "mlr-review", "component": "queue", "method": "highlight"}

    corrected, was_corrected = _enforce_step_order(session, proposed)

    assert was_corrected is False
    assert corrected == proposed


def test_already_fired_sub_action_is_a_legitimate_revisit():
    session = SessionState()
    session.walkthrough_step = 9
    session.walkthrough_fired_actions = {"step-brief"}
    proposed = {"page": "magicavatar-studio", "component": "wizard", "method": "step-brief"}

    corrected, was_corrected = _enforce_step_order(session, proposed)

    assert was_corrected is False
    assert corrected == proposed


def test_wizard_page_by_step_covers_both_studio_flow_steps():
    assert WIZARD_PAGE_BY_STEP == {
        8: ("magicreel-studio", "wizard"),
        9: ("magicavatar-studio", "wizard"),
    }
