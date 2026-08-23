"""Tests for the Pipecat observability wiring added in bot.py (P1 #5:
UserBotLatencyObserver + the already-running TurnTrackingObserver).

The handlers are plain module-level functions, not closures defined inside
run_bot, specifically so they're testable without standing up a transport,
a pipeline, or a live PipelineWorker.
"""
from __future__ import annotations

import json

from loguru import logger

from src.voice.bot import (
    log_first_bot_speech_latency,
    log_latency_breakdown,
    log_pipeline_turn_ended,
)


class _Metric:
    """Stand-in for a pydantic TTFBBreakdownMetrics/TextAggregationBreakdownMetrics
    instance — only .model_dump() is actually used by log_latency_breakdown."""

    def __init__(self, **kwargs):
        self._data = kwargs

    def model_dump(self):
        return dict(self._data)


class _Breakdown:
    """Stand-in for pipecat's LatencyBreakdown."""

    def __init__(self, user_turn_secs, ttfb, text_aggregation, function_calls):
        self.user_turn_secs = user_turn_secs
        self.ttfb = ttfb
        self.text_aggregation = text_aggregation
        self.function_calls = function_calls


def _capture_logs():
    lines: list[str] = []
    sink_id = logger.add(lambda msg: lines.append(msg.record["message"]), level="INFO")
    return lines, sink_id


def test_log_latency_breakdown_emits_valid_json_with_expected_fields():
    lines, sink_id = _capture_logs()
    try:
        breakdown = _Breakdown(
            user_turn_secs=1.23,
            ttfb=[_Metric(processor="stt", model=None, start_time=1.0, duration_secs=0.2)],
            text_aggregation=_Metric(processor="tts", start_time=1.1, duration_secs=0.05),
            function_calls=[],
        )
        log_latency_breakdown("visitor-abc", breakdown)
    finally:
        logger.remove(sink_id)

    assert len(lines) == 1
    assert lines[0].startswith("PIPELINE_LATENCY ")
    payload = json.loads(lines[0][len("PIPELINE_LATENCY "):])
    assert payload["visitor_id"] == "visitor-abc"
    assert payload["user_turn_secs"] == 1.23
    assert payload["ttfb"][0]["processor"] == "stt"
    assert payload["text_aggregation"]["processor"] == "tts"
    assert payload["function_calls"] == []


def test_log_latency_breakdown_handles_missing_optional_fields():
    # A greeting/first-speech cycle with no user turn, no TTFB collected yet,
    # no aggregation — must not raise on the None cases.
    lines, sink_id = _capture_logs()
    try:
        breakdown = _Breakdown(
            user_turn_secs=None, ttfb=[], text_aggregation=None, function_calls=[]
        )
        log_latency_breakdown("visitor-xyz", breakdown)
    finally:
        logger.remove(sink_id)

    payload = json.loads(lines[0][len("PIPELINE_LATENCY "):])
    assert payload["text_aggregation"] is None
    assert payload["user_turn_secs"] is None
    assert payload["ttfb"] == []


def test_log_first_bot_speech_latency():
    lines, sink_id = _capture_logs()
    try:
        log_first_bot_speech_latency("visitor-1", 2.5)
    finally:
        logger.remove(sink_id)

    assert lines[0] == "PIPELINE_FIRST_SPEECH_LATENCY visitor_id=visitor-1 latency_s=2.500"


def test_log_pipeline_turn_ended():
    lines, sink_id = _capture_logs()
    try:
        log_pipeline_turn_ended("visitor-2", 7, 3.14159, True)
    finally:
        logger.remove(sink_id)

    assert lines[0] == (
        "PIPELINE_TURN_ENDED visitor_id=visitor-2 turn=7 duration_s=3.142 interrupted=True"
    )
