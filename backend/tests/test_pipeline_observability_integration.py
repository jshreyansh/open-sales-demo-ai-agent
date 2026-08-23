"""End-to-end check that the observability wiring (P1 #5) actually gets fed
real data by a real Pipecat pipeline — not just that the logging functions
format things correctly in isolation (see test_pipeline_observability.py).

Uses pipecat.tests.utils.run_test, Pipecat's own harness for this: builds a
real Pipeline + PipelineWorker, attaches our real UserBotLatencyObserver with
our real event handlers from src.voice.bot, and pushes a synthetic frame
sequence shaped like one real conversational turn (user stops speaking ->
STT/LLM/TTS metrics arrive -> bot starts speaking). This is the same
observer class and the same handler functions bot.py wires into the actual
voice pipeline — only the transport and the frame source are fake.

What this does NOT prove: that our production STT/LLM/TTS services emit
MetricsFrame with realistic values, or that VAD/turn timing looks like this
on a real call. That needs a real test call against the running bot with the
resulting log lines inspected — this test proves the wiring plumbing itself
is correct.
"""
from __future__ import annotations

import json
import time

from loguru import logger

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    ClientConnectedFrame,
    Frame,
    MetricsFrame,
    UserStoppedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.metrics.metrics import TTFBMetricsData
from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
from pipecat.pipeline.worker import PipelineParams
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.tests.utils import SleepFrame, run_test

from src.voice.bot import log_first_bot_speech_latency, log_latency_breakdown


class _PassthroughProcessor(FrameProcessor):
    """Stands in for our real `agent`/`tts` pipeline stages — this test is
    about the observer wiring, not agent_processor's own turn logic (that's
    covered separately in test_telemetry_release.py)."""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)


def _capture_logs():
    lines: list[str] = []
    sink_id = logger.add(lambda msg: lines.append(msg.record["message"]), level="INFO")
    return lines, sink_id


async def _run_one_turn_through_real_pipeline():
    latency_observer = UserBotLatencyObserver()
    latency_observer.event_handler("on_latency_breakdown")(
        lambda _observer, breakdown: log_latency_breakdown("integration-test-visitor", breakdown)
    )
    latency_observer.event_handler("on_first_bot_speech_latency")(
        lambda _observer, latency_seconds: log_first_bot_speech_latency(
            "integration-test-visitor", latency_seconds
        )
    )

    now = time.time()
    frames = [
        ClientConnectedFrame(),
        SleepFrame(sleep=0.05),
        VADUserStoppedSpeakingFrame(stop_secs=0.5, timestamp=now),
        MetricsFrame(
            data=[
                TTFBMetricsData(processor="stt_service", model=None, value=0.15),
                TTFBMetricsData(processor="llm_service", model="deepseek-chat", value=0.9),
                TTFBMetricsData(processor="tts_service", model=None, value=0.25),
            ]
        ),
        UserStoppedSpeakingFrame(),
        SleepFrame(sleep=0.05),
        BotStartedSpeakingFrame(),
    ]

    await run_test(
        _PassthroughProcessor(),
        frames_to_send=frames,
        observers=[latency_observer],
        pipeline_params=PipelineParams(enable_metrics=True),
    )


def test_latency_observer_emits_sane_data_through_a_real_pipeline():
    lines, sink_id = _capture_logs()
    try:
        import asyncio

        asyncio.run(_run_one_turn_through_real_pipeline())
    finally:
        logger.remove(sink_id)

    latency_lines = [l for l in lines if l.startswith("PIPELINE_LATENCY ")]
    first_speech_lines = [l for l in lines if l.startswith("PIPELINE_FIRST_SPEECH_LATENCY ")]

    assert len(latency_lines) == 1, f"expected exactly one breakdown, got: {lines}"
    assert len(first_speech_lines) == 1, f"expected exactly one first-speech line, got: {lines}"

    payload = json.loads(latency_lines[0][len("PIPELINE_LATENCY "):])
    assert payload["visitor_id"] == "integration-test-visitor"

    # The three synthetic TTFB metrics must all have made it through the real
    # observer's MetricsFrame handling, unmodified in processor name/value.
    by_processor = {t["processor"]: t["duration_secs"] for t in payload["ttfb"]}
    assert by_processor == {
        "stt_service": 0.15,
        "llm_service": 0.9,
        "tts_service": 0.25,
    }

    # user_turn_secs = time from VADUserStoppedSpeakingFrame's actual silence
    # point to UserStoppedSpeakingFrame — real pipeline plumbing computed
    # this, not something we constructed by hand. Should be small and
    # positive, not None and not implausibly large.
    assert payload["user_turn_secs"] is not None
    assert 0 <= payload["user_turn_secs"] < 5

    assert first_speech_lines[0].startswith("PIPELINE_FIRST_SPEECH_LATENCY visitor_id=integration-test-visitor")
