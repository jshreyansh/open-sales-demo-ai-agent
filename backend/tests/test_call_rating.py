"""Tests for the post-call feedback screen's storage layer (gate_log.py)
and REST endpoints (server.py) — /api/call-rating and /api/call-rating/event.

Uses a temporary sqlite file (never the real app.db), same fixture shape
as test_gate_log_concurrent_writes.py, so these tests can't touch
production data.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.data import gate_log
from src.server import CallRatingEventRequest, CallRatingRequest, log_call_rating_event, submit_call_rating


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_app.db"
    monkeypatch.setattr(gate_log, "DB_PATH", str(db_path))
    gate_log.init_db()
    return db_path


def test_save_and_get_call_rating_round_trips(temp_db):
    gate_log.save_call_rating(
        "visitor-1",
        sentiment="great",
        reason="Answered everything clearly",
        tags=["felt-natural", "answered-clearly"],
        call_duration_secs=612,
        disconnect_reason="visitor_hangup",
        skipped=False,
    )

    result = gate_log.get_call_rating("visitor-1")

    assert result["sentiment"] == "great"
    assert result["reason"] == "Answered everything clearly"
    assert result["tags"] == ["felt-natural", "answered-clearly"]
    assert result["call_duration_secs"] == 612
    assert result["disconnect_reason"] == "visitor_hangup"
    assert result["skipped"] is False


def test_save_call_rating_with_no_tags_round_trips_empty_list(temp_db):
    gate_log.save_call_rating(
        "visitor-2", sentiment="okay", reason=None, tags=None,
        call_duration_secs=200, disconnect_reason="connection_lost", skipped=False,
    )

    result = gate_log.get_call_rating("visitor-2")

    assert result["tags"] == []
    assert result["reason"] is None


def test_save_call_rating_skipped_case(temp_db):
    gate_log.save_call_rating(
        "visitor-3", sentiment=None, reason=None, tags=None,
        call_duration_secs=45, disconnect_reason="visitor_hangup", skipped=True,
    )

    result = gate_log.get_call_rating("visitor-3")

    assert result["skipped"] is True
    assert result["sentiment"] is None


def test_save_call_rating_upserts_on_resubmit(temp_db):
    gate_log.save_call_rating(
        "visitor-4", sentiment="needs_work", reason="slow", tags=[],
        call_duration_secs=100, disconnect_reason="visitor_hangup", skipped=False,
    )
    gate_log.save_call_rating(
        "visitor-4", sentiment="great", reason="actually good", tags=["felt-natural"],
        call_duration_secs=100, disconnect_reason="visitor_hangup", skipped=False,
    )

    result = gate_log.get_call_rating("visitor-4")

    assert result["sentiment"] == "great"
    assert result["reason"] == "actually good"


def test_get_call_rating_returns_none_when_absent(temp_db):
    assert gate_log.get_call_rating("visitor-does-not-exist") is None


def test_log_and_list_call_rating_events(temp_db):
    gate_log.log_call_rating_event("visitor-5", "shown")
    gate_log.log_call_rating_event("visitor-5", "submitted")

    events = [e["event"] for e in gate_log.list_call_rating_events("visitor-5")]

    assert events == ["shown", "submitted"]


def test_submit_call_rating_endpoint_persists_and_logs_submitted_event(temp_db):
    body = CallRatingRequest(
        visitorId="visitor-6", sentiment="okay", reason="fine", tags=["a-bit-slow"],
        callDurationSecs=300, disconnectReason="visitor_hangup", skipped=False,
    )

    result = submit_call_rating(body)

    assert result == {"ok": True}
    assert gate_log.get_call_rating("visitor-6")["sentiment"] == "okay"
    events = [e["event"] for e in gate_log.list_call_rating_events("visitor-6")]
    assert events == ["submitted"]


def test_submit_call_rating_endpoint_skip_persists_and_logs_skipped_event(temp_db):
    body = CallRatingRequest(visitorId="visitor-7", skipped=True, callDurationSecs=10)

    submit_call_rating(body)

    assert gate_log.get_call_rating("visitor-7")["skipped"] is True
    events = [e["event"] for e in gate_log.list_call_rating_events("visitor-7")]
    assert events == ["skipped"]


def test_submit_call_rating_rejects_missing_sentiment_when_not_skipped(temp_db):
    body = CallRatingRequest(visitorId="visitor-8", skipped=False)

    with pytest.raises(HTTPException) as exc_info:
        submit_call_rating(body)

    assert exc_info.value.status_code == 400


def test_submit_call_rating_rejects_invalid_sentiment(temp_db):
    body = CallRatingRequest(visitorId="visitor-9", sentiment="amazing", skipped=False)

    with pytest.raises(HTTPException) as exc_info:
        submit_call_rating(body)

    assert exc_info.value.status_code == 400


def test_call_rating_event_endpoint_logs_shown(temp_db):
    result = log_call_rating_event(CallRatingEventRequest(visitorId="visitor-10", event="shown"))

    assert result == {"ok": True}
    events = [e["event"] for e in gate_log.list_call_rating_events("visitor-10")]
    assert events == ["shown"]
