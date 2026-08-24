"""Regression tests for the voice-lock admission gate (server.py's
claim_voice_lock/release_voice_lock), part of the concurrent-calls plan.

_active_call (a single Optional[Dict]) became _active_calls (a dict keyed
by visitorId) plus two independent admission checks: a hard ceiling
(_MAX_CONCURRENT_CALLS) and a CPU-load threshold (_CPU_LOAD_THRESHOLD_PCT),
mirroring LiveKit's own load_fnc/load_threshold admission pattern. These
tests exist specifically to prove the single-caller case still behaves
identically to the old single-slot lock (case e below), not just that the
new pool mechanics work in isolation — the plan's own explicit regression
requirement.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

import src.server as server
from src.server import VoiceLockRequest, claim_voice_lock, release_voice_lock


@pytest.fixture(autouse=True)
def _isolate_voice_lock_state():
    """_active_calls and _MAX_CONCURRENT_CALLS are module-level globals
    shared with the real app — reset before each test and restore the
    production default (ceiling of 5, validated by the Phase 3 load test
    on 2026-08-24 — see server.py's own comment on _MAX_CONCURRENT_CALLS)
    after, so mutations here can't leak into other test files sharing
    this process."""
    server._active_calls = {}
    yield
    server._active_calls = {}
    server._MAX_CONCURRENT_CALLS = 5


def test_first_claim_succeeds_like_today():
    server._MAX_CONCURRENT_CALLS = 1
    with patch.object(server.psutil, "cpu_percent", return_value=10.0):
        result = claim_voice_lock(VoiceLockRequest(visitorId="v1"))
    assert result == {"ok": True}
    assert "v1" in server._active_calls


def test_second_different_visitor_refused_under_ceiling_of_one():
    """A ceiling of 1 (the old single-slot lock's own behavior, still a
    valid config this pool must support) must refuse a second, different
    visitor outright, not conditioned on CPU."""
    server._MAX_CONCURRENT_CALLS = 1
    with patch.object(server.psutil, "cpu_percent", return_value=10.0):
        claim_voice_lock(VoiceLockRequest(visitorId="v1"))
        result = claim_voice_lock(VoiceLockRequest(visitorId="v2"))
    assert result == {"ok": False}
    assert set(server._active_calls.keys()) == {"v1"}


def test_same_visitor_reclaims_regardless_of_cpu_load():
    """A visitor reclaiming a slot they already hold must always succeed,
    even under a CPU spike that would refuse a brand new claim — this is
    the existing single-caller retry/reconnect flow and must not regress."""
    server._MAX_CONCURRENT_CALLS = 1
    with patch.object(server.psutil, "cpu_percent", return_value=10.0):
        claim_voice_lock(VoiceLockRequest(visitorId="v1"))
    with patch.object(server.psutil, "cpu_percent", return_value=99.0):
        result = claim_voice_lock(VoiceLockRequest(visitorId="v1"))
    assert result == {"ok": True}


def test_new_visitor_refused_when_cpu_over_threshold_under_the_ceiling():
    server._MAX_CONCURRENT_CALLS = 10
    with patch.object(server.psutil, "cpu_percent", return_value=10.0):
        claim_voice_lock(VoiceLockRequest(visitorId="v1"))
    with patch.object(server.psutil, "cpu_percent", return_value=85.0):
        result = claim_voice_lock(VoiceLockRequest(visitorId="v2"))
    assert result == {"ok": False}
    assert "v2" not in server._active_calls


def test_new_visitor_admitted_when_cpu_under_threshold_and_under_ceiling():
    server._MAX_CONCURRENT_CALLS = 10
    with patch.object(server.psutil, "cpu_percent", return_value=10.0):
        claim_voice_lock(VoiceLockRequest(visitorId="v1"))
        result = claim_voice_lock(VoiceLockRequest(visitorId="v2"))
    assert result == {"ok": True}
    assert set(server._active_calls.keys()) == {"v1", "v2"}


def test_claims_up_to_hard_ceiling_succeed_and_next_is_refused_regardless_of_cpu():
    server._MAX_CONCURRENT_CALLS = 3
    with patch.object(server.psutil, "cpu_percent", return_value=5.0):
        for vid in ("v1", "v2", "v3"):
            assert claim_voice_lock(VoiceLockRequest(visitorId=vid)) == {"ok": True}
        # CPU is low, but the ceiling itself must still refuse the 4th.
        result = claim_voice_lock(VoiceLockRequest(visitorId="v4"))
    assert result == {"ok": False}
    assert "v4" not in server._active_calls


def test_release_frees_a_slot_for_a_new_claim():
    server._MAX_CONCURRENT_CALLS = 1
    with patch.object(server.psutil, "cpu_percent", return_value=10.0):
        claim_voice_lock(VoiceLockRequest(visitorId="v1"))
        assert claim_voice_lock(VoiceLockRequest(visitorId="v2")) == {"ok": False}
        release_voice_lock(VoiceLockRequest(visitorId="v1"))
        result = claim_voice_lock(VoiceLockRequest(visitorId="v2"))
    assert result == {"ok": True}
    assert set(server._active_calls.keys()) == {"v2"}


def test_release_is_a_no_op_for_a_visitor_that_does_not_hold_the_lock():
    server._MAX_CONCURRENT_CALLS = 1
    with patch.object(server.psutil, "cpu_percent", return_value=10.0):
        claim_voice_lock(VoiceLockRequest(visitorId="v1"))
    release_voice_lock(VoiceLockRequest(visitorId="v2"))
    assert set(server._active_calls.keys()) == {"v1"}


def test_stale_entry_is_pruned_and_frees_the_ceiling():
    server._MAX_CONCURRENT_CALLS = 1
    with patch.object(server.psutil, "cpu_percent", return_value=10.0):
        claim_voice_lock(VoiceLockRequest(visitorId="v1"))
        server._active_calls["v1"]["claimed_at"] -= server._CALL_LOCK_TTL_SECS + 1
        result = claim_voice_lock(VoiceLockRequest(visitorId="v2"))
    assert result == {"ok": True}
    assert set(server._active_calls.keys()) == {"v2"}


def test_single_caller_flow_end_to_end_matches_todays_behavior():
    """Case (e) from the plan's testing section: claim -> same visitor
    reclaims -> release, at a ceiling of 1, must behave identically to
    the old single-slot lock throughout."""
    server._MAX_CONCURRENT_CALLS = 1
    with patch.object(server.psutil, "cpu_percent", return_value=20.0):
        assert claim_voice_lock(VoiceLockRequest(visitorId="v1")) == {"ok": True}
        assert claim_voice_lock(VoiceLockRequest(visitorId="v1")) == {"ok": True}
        assert claim_voice_lock(VoiceLockRequest(visitorId="v2")) == {"ok": False}
    release_voice_lock(VoiceLockRequest(visitorId="v1"))
    with patch.object(server.psutil, "cpu_percent", return_value=20.0):
        assert claim_voice_lock(VoiceLockRequest(visitorId="v2")) == {"ok": True}
