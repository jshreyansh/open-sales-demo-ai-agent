"""Regression tests for the pricing-question navigation backstop
(production issue, real call 535e606c, 2026-08-24).

Background: the prospect asked a specific pricing question ("what's the
pricing... 15 licenses... discount for tenure") and got a purely verbal
answer with action: None — the existing Plans page/registry action never
fired. A vaguer later question ("what are the pricing plans") happened to
trigger navigation to the same page. Same intent, inconsistent result,
entirely at the model's discretion — nothing in the system prompt actually
tells it pricing words should also open the page.

Fix: a deterministic backstop, same shape as the existing
_explicit_walkthrough_request/pending_walkthrough_request pattern — detect
pricing intent from the prospect's own words in _begin_turn, and force the
Plans page open in _stream_with_claude/_select_with_claude ONLY if the
model chose no action at all this turn (its own choice to navigate
somewhere else always wins).
"""
from __future__ import annotations

import asyncio

from src.agent.runtime import _PRICING_INTENT, _begin_turn, _pricing_backstop_action
from src.context.store import SessionState


# --- _PRICING_INTENT regex ---------------------------------------------------


def test_matches_the_exact_real_call_phrasing():
    assert _PRICING_INTENT.search(
        "No. I would love know, basically, what's the pricing and how much would it be"
    )
    assert _PRICING_INTENT.search("I do you have any plans you can show me? What are the pricing plan?")
    assert _PRICING_INTENT.search("I just wanted to talk something about the commercials.")


def test_matches_every_requested_keyword():
    for word in ("pricing", "commercials", "plans", "subscription", "money", "cost"):
        assert _PRICING_INTENT.search(f"what about {word}"), word


def test_bare_plan_followed_by_to_for_on_is_not_pricing_intent():
    assert not _PRICING_INTENT.search("what's the plan to migrate our existing content")
    assert not _PRICING_INTENT.search("what's the plan for next quarter")
    assert not _PRICING_INTENT.search("what's your plan on onboarding")


def test_bare_plans_without_a_verb_still_counts():
    assert _PRICING_INTENT.search("do you have any plans you can show me")


def test_unrelated_text_does_not_match():
    assert not _PRICING_INTENT.search("can you show me the MLR approval queue")


# --- _pricing_backstop_action ------------------------------------------------


def test_forces_plans_page_when_pending_and_not_already_there():
    session = SessionState()
    session.pending_pricing_request = True
    session.current_page = "content-studio"

    action = _pricing_backstop_action(session)

    assert action == {"page": "settings-plans", "component": "plans", "method": "highlight"}


def test_does_nothing_when_no_pricing_intent_was_heard():
    session = SessionState()
    session.pending_pricing_request = False

    assert _pricing_backstop_action(session) is None


def test_does_not_re_navigate_when_already_on_the_plans_page():
    session = SessionState()
    session.pending_pricing_request = True
    session.current_page = "settings-plans"

    assert _pricing_backstop_action(session) is None


# --- _begin_turn wiring -------------------------------------------------


def test_begin_turn_sets_pending_pricing_request_from_the_raw_message():
    session = SessionState()
    asyncio.run(_begin_turn(session, "what's the pricing and how much would it be"))
    assert session.pending_pricing_request is True


def test_begin_turn_clears_pending_pricing_request_for_an_unrelated_message():
    session = SessionState()
    session.pending_pricing_request = True  # leftover from a previous turn
    asyncio.run(_begin_turn(session, "can you show me the MLR approval queue"))
    assert session.pending_pricing_request is False
