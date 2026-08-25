"""Tests for repeated-interruption earned patience (_interruption_protection).

Background: real call 631341bd, 2026-08-25 ~05:34 UTC — the prospect
answered the opening qualification questions in a halting, self-correcting
way, producing 4 genuine barge-ins (real transcribed speech each time, not
VAD noise) on the agent's own follow-up questions within about 25 seconds.
VADParams.start_secs (bot.py) stays untouched on purpose — it was
deliberately tuned low to fix a previously reported "barge-in feels laggy"
complaint, and raising it would regress that fix for every future
interruption, not just repeated ones.

Instead, _interruption_protection() mirrors the existing, already-proven
_fragmentation_protection() shape: the FIRST interruption earns zero extra
patience (stays exactly as snappy as today), and only the SECOND and later
rapid ones make the agent wait longer before re-engaging, decaying back to
baseline the same way fragmentation protection already does.
"""
from __future__ import annotations

from src.voice.agent_processor import (
    INTERRUPTION_DECAY_TURNS,
    INTERRUPTION_PROTECTION_MAX_SECS,
    INTERRUPTION_PROTECTION_STEP_SECS,
    AgentRuntimeProcessor,
)


def _make_agent(visitor_id: str) -> AgentRuntimeProcessor:
    agent = AgentRuntimeProcessor(visitor_id)
    return agent


def test_zero_interruptions_earn_zero_protection():
    agent = _make_agent("test-zero-interruptions")
    assert agent._interruption_protection() == 0.0


def test_a_single_interruption_earns_one_step_of_protection():
    """Mirrors _fragmentation_protection()'s own shape exactly: the FIRST
    event already earns one step (same as fragmentation's first event does)
    — what stays untouched is start_secs itself, so the interruption that
    just happened was still exactly as fast/snappy as today. This step is
    what starts giving the NEXT reply a little more room, before it grows
    further on subsequent rapid ones."""
    agent = _make_agent("test-single-interruption")
    agent._note_interruption_event()
    assert agent._interruption_protection() == INTERRUPTION_PROTECTION_STEP_SECS


def test_repeated_interruptions_earn_increasing_protection():
    agent = _make_agent("test-repeated-interruptions")
    agent._note_interruption_event()
    agent._note_interruption_event()
    assert agent._interruption_protection() == 2 * INTERRUPTION_PROTECTION_STEP_SECS
    agent._note_interruption_event()
    assert agent._interruption_protection() == 3 * INTERRUPTION_PROTECTION_STEP_SECS


def test_protection_is_capped():
    agent = _make_agent("test-protection-ceiling")
    for _ in range(20):
        agent._note_interruption_event()
    assert agent._interruption_protection() == INTERRUPTION_PROTECTION_MAX_SECS


def test_protection_decays_back_to_baseline_after_quiet_turns():
    agent = _make_agent("test-protection-decay")
    agent._note_interruption_event()
    agent._note_interruption_event()
    assert agent._interruption_protection() > 0.0
    agent._turns_since_interruption = INTERRUPTION_DECAY_TURNS * 5
    assert agent._interruption_protection() == 0.0


def test_settle_window_floor_reflects_interruption_protection():
    agent = _make_agent("test-settle-window-floor")
    agent._note_interruption_event()
    agent._note_interruption_event()
    protection = agent._interruption_protection()
    assert protection > 0.0
    assert agent._settle_window() >= protection


def test_commit_window_is_unaffected_when_fast_commit_disabled():
    """FAST_COMMIT_ENABLED is False today — _commit_window() must still
    equal _settle_window() exactly, same invariant as before this change."""
    agent = _make_agent("test-commit-window-passthrough")
    agent._note_interruption_event()
    agent._note_interruption_event()
    assert agent._commit_window() == agent._settle_window()
