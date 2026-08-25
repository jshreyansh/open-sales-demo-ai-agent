"""Regression test for the frontend's Listening badge (and the visitor's
own mic-live indicator, same underlying signal) never appearing in any
real call, ever — root-caused by reading pipecat's own RTVIObserver and
client-js source, not by guessing:

RTVIObserver (attached by default via PipelineWorker's enable_rtvi=True,
see bot.py) only converts UserStartedSpeakingFrame/UserStoppedSpeakingFrame
into the "user-started-speaking"/"user-stopped-speaking" RTVI messages the
installed @pipecat-ai/client-js actually understands. Its
vad_user_speaking_enabled option (which WOULD react to the raw
VADUserStartedSpeakingFrame this app's VADProcessor emits) defaults to
False, and even if it were turned on, the installed client-js has no
handler at all for that message type ("vad-user-started-speaking").

Nothing in this pipeline otherwise produces the finalized
UserStartedSpeakingFrame/UserStoppedSpeakingFrame — there's no
UserTurnProcessor here, since this app's whole turn-taking system is
custom-built in agent_processor.py, not pipecat's own turn-strategy
framework. So RTVIEvent.UserStartedSpeaking has never once fired on the
client, in any call, regardless of any frontend timing/debounce fix.

Fix: push the finalized frame type as an ADDITIONAL frame (not a
replacement) at the exact same point this processor already tracks real
VAD start/stop for its own purposes, so RTVIObserver's already-enabled
default path picks it up.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from pipecat.frames.frames import (
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection

from src.voice.agent_processor import AgentRuntimeProcessor


def _make_agent(visitor_id: str) -> AgentRuntimeProcessor:
    agent = AgentRuntimeProcessor(visitor_id)
    agent.push_frame = AsyncMock()
    return agent


def test_vad_start_also_pushes_the_finalized_user_started_speaking_frame():
    agent = _make_agent("test-rtvi-start")

    asyncio.run(agent.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM))

    pushed_types = [type(c.args[0]) for c in agent.push_frame.await_args_list]
    assert UserStartedSpeakingFrame in pushed_types
    assert VADUserStartedSpeakingFrame in pushed_types


def test_vad_stop_also_pushes_the_finalized_user_stopped_speaking_frame():
    agent = _make_agent("test-rtvi-stop")

    asyncio.run(agent.process_frame(VADUserStoppedSpeakingFrame(), FrameDirection.DOWNSTREAM))

    pushed_types = [type(c.args[0]) for c in agent.push_frame.await_args_list]
    assert UserStoppedSpeakingFrame in pushed_types
    assert VADUserStoppedSpeakingFrame in pushed_types


def test_original_vad_frame_is_still_forwarded_unchanged():
    """The new push is additive — nothing about the existing VAD-frame
    forwarding (which the rest of this app's own turn-taking logic depends
    on) should change."""
    agent = _make_agent("test-rtvi-passthrough")
    vad_frame = VADUserStartedSpeakingFrame()

    asyncio.run(agent.process_frame(vad_frame, FrameDirection.DOWNSTREAM))

    forwarded = [c.args[0] for c in agent.push_frame.await_args_list if c.args[0] is vad_frame]
    assert len(forwarded) == 1
