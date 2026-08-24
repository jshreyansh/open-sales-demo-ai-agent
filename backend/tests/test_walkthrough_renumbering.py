"""Regression tests for the walkthrough renumbering (9 steps -> 13).

Brand Dossiers, Brand Dossier detail, Content Library, and Settings ->
Integrations were inserted into the scripted full-platform tour, which
pushed Content Studio through Home wrap-up from steps 2-9 to steps 4-13,
and moved the two studio sub-beat flows (MagicReel/MagicAvatar) from
indices 6/7 to 8/9. That renumbering touches several places in runtime.py
that hardcode the studio-flow step indices as a literal tuple/dict
((6, 7) -> (8, 9), {"magicreel": 6, "magicavatar": 7} -> {...: 8, ...: 9})
rather than deriving them — a mechanical sed-style change with real risk of
a missed occurrence silently breaking the sub-beat pacing that took several
rounds of real-call fixes to get right earlier this project. These tests
exist so a missed occurrence fails loudly here instead of in a live call.
"""
from __future__ import annotations

import asyncio

from src.agent.walkthrough import (
    STEP_SUB_ACTIONS,
    WALKTHROUGH_STEPS,
    WALKTHROUGH_STEPS_BY_INDEX,
    sub_beat_for,
)
from src.agent.runtime import _finalize_turn, _walkthrough_note
from src.context.store import SessionState


def test_step_indices_are_contiguous_one_to_thirteen():
    assert [s.index for s in WALKTHROUGH_STEPS] == list(range(1, 14))


def test_expected_titles_at_expected_positions():
    expected = {
        1: "Overview",
        2: "Brand Dossiers",
        3: "Brand Dossier detail",
        4: "Content Studio",
        8: "MagicReel flow",
        9: "MagicAvatar flow",
        10: "MLR tab",
        11: "Content Library",
        12: "Settings — Integrations & Plug-ins",
        13: "Home wrap-up",
    }
    for index, title in expected.items():
        assert WALKTHROUGH_STEPS_BY_INDEX[index].title == title


def test_step_sub_actions_keyed_by_new_studio_flow_indices():
    assert set(STEP_SUB_ACTIONS.keys()) == {8, 9}
    assert STEP_SUB_ACTIONS[8][0] == "step-source"
    assert STEP_SUB_ACTIONS[9][0] == "step-brief"


def test_new_tour_steps_only_highlight_never_open_granular_actions():
    # Explicit product decision: the tour shows the MLR queue and the
    # Content Library grid, but never opens a specific submission's detail
    # panel or a library item's preview modal — those stay ask-only actions
    # the agent can still reach off-script, just not forced into the tour.
    mlr_step = WALKTHROUGH_STEPS_BY_INDEX[10]
    library_step = WALKTHROUGH_STEPS_BY_INDEX[11]
    assert mlr_step.action == {"page": "mlr-review", "component": "queue", "method": "highlight"}
    assert library_step.action == {"page": "content-library", "component": "grid", "method": "highlight"}


def test_start_module_walkthrough_magicreel_enters_at_step_eight():
    session = SessionState()
    result = {"start_module_walkthrough": "magicreel", "reply": "Let's build a MagicReel."}
    asyncio.run(_finalize_turn(session, result, persist=False))
    assert session.walkthrough_step == 8
    assert session.walkthrough_scope_end == 8


def test_start_module_walkthrough_magicavatar_enters_at_step_nine():
    session = SessionState()
    result = {"start_module_walkthrough": "magicavatar", "reply": "Let's build a MagicAvatar."}
    asyncio.run(_finalize_turn(session, result, persist=False))
    assert session.walkthrough_step == 9
    assert session.walkthrough_scope_end == 9


def test_module_scoped_magicreel_walkthrough_ends_at_its_own_boundary():
    # A MagicReel-only run (scope_end=8) trying to advance to step 9
    # (MagicAvatar) must end the walkthrough instead of wandering into the
    # rest of the platform — this is the exact guard that used to be keyed
    # off the old (6, 7) indices.
    session = SessionState()
    session.walkthrough_step = 8
    session.walkthrough_scope_end = 8
    asyncio.run(_finalize_turn(session, {"walkthrough_step": 9, "reply": "Wrapping up MagicReel."}, persist=False))
    assert session.walkthrough_step is None
    assert session.walkthrough_scope_end is None


def test_full_tour_start_walkthrough_begins_at_step_one():
    session = SessionState()
    asyncio.run(_finalize_turn(session, {"start_walkthrough": True, "reply": "Here's a quick tour."}, persist=False))
    assert session.walkthrough_step == 1
    assert session.walkthrough_scope_end is None


def test_walkthrough_note_resolves_sub_beat_for_step_eight():
    session = SessionState()
    session.walkthrough_step = 8
    note = _walkthrough_note(session)
    assert "MagicReel flow" in note
    # No sub-actions fired yet -> the exact next one is the first in the list.
    assert "step-source" in note


def test_sub_beat_for_known_and_unknown_actions():
    assert sub_beat_for("step-source") is not None
    assert sub_beat_for("select-source-dossier") is not None
    assert sub_beat_for("not-a-real-action") is None
    assert sub_beat_for(None) is None


def test_overview_guidance_names_brand_dossiers_not_content_studio():
    """Regression for session 66da2724: the model said "I'll start with the
    Content Studio" in its overview reply — true under the OLD 9-step order
    (Content Studio was step 2) but wrong now that Brand Dossiers goes
    first. The overview guidance must say so explicitly rather than let the
    model infer it from PRODUCT_OVERVIEW's own emphasis on Content Studio."""
    overview = WALKTHROUGH_STEPS_BY_INDEX[1].guidance
    assert "Brand Dossiers" in overview
    assert "Content Studio" in overview  # named specifically as NOT first
