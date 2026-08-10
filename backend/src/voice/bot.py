"""Voice entrypoint for the demo agent.

Runs as its own Pipecat server, separate from the REST API (server.py, port
8787). STT (Groq/Whisper) -> AgentRuntimeProcessor (calls the same
run_turn() the text chat uses) -> TTS (Cartesia) -> back to the browser.

Transport is a plain WebSocket (not WebRTC): audio travels as regular
WebSocket frames over ordinary TCP/HTTPS, which passes through a standard
HTTP load balancer or reverse proxy untouched. WebRTC's raw UDP media
stream doesn't — that matters the moment this runs anywhere that isn't
literally the same machine as the browser (e.g. behind an AWS ALB in a
private subnet, which is exactly the deployment this was switched for).
The cost is a bit more latency than a direct UDP path; against the
multi-second LLM+TTS latency already in this pipeline, it's not
noticeable.
"""

import asyncio
import os

import aiohttp
from dotenv import load_dotenv

# Must run before importing anything that transitively touches agent.runtime —
# that module reads ANTHROPIC_API_KEY/DEEPSEEK_API_KEY from os.environ at
# module import time (top-level code, not inside a function), so it only gets
# one chance to see them. Importing agent_processor (which imports
# agent.runtime) before this line silently bakes in _client = None for the
# lifetime of the process — no exception, no error, just the dumb keyword
# fallback forever. This exact bug shipped once already; don't reorder these.
load_dotenv()

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.cartesia.tts import CartesiaTTSService, GenerationConfig
from pipecat.services.groq.stt import GroqSTTService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner

from ..context.store import start_session
from .agent_processor import (
    IDLE_CHECK_INTERVAL_SECS,
    IDLE_TIMEOUT_SECS,
    AgentRuntimeProcessor,
    TTSLevelReporter,
)

REST_API_URL = "http://localhost:8787"

transport_params = {
    # serializer must match the client's default (@pipecat-ai/websocket-transport's
    # WebSocketTransport uses ProtobufFrameSerializer unless told otherwise) — the
    # two ends need to agree on the wire format, this isn't set automatically for
    # the plain "websocket" transport the way it is for the telephony ones.
    "websocket": lambda: FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        serializer=ProtobufFrameSerializer(),
    ),
}


async def _release_voice_lock(visitor_id: str) -> None:
    # Frees the single-call gate (see server.py's _active_call) the moment
    # a call actually ends, rather than leaving the next caller to wait out
    # its TTL safety net. Best-effort: if this fails, the TTL still
    # recovers it eventually. Shared by on_client_disconnected and
    # _watch_idle so both teardown paths release it the same way.
    try:
        async with aiohttp.ClientSession() as http:
            await http.post(
                f"{REST_API_URL}/api/voice-lock/release",
                json={"visitorId": visitor_id},
                timeout=aiohttp.ClientTimeout(total=3),
            )
    except Exception:
        logger.exception(f"Failed to release voice lock for visitor {visitor_id}")


async def _watch_idle(agent: AgentRuntimeProcessor, worker: PipelineWorker, visitor_id: str) -> None:
    """Ends the call after IDLE_TIMEOUT_SECS of total silence from both
    sides — someone who mutes and walks away without hanging up would
    otherwise hold this box's one call slot indefinitely. Lives here, not
    on AgentRuntimeProcessor, because actually tearing down the call needs
    `worker`: pushing an EndFrame from mid-pipeline was tried first and
    doesn't work — it only closes half of the WebSocket client's shared
    "leave counter" (confirmed by reading pipecat's actual client wrapper
    source: disconnect() only takes effect once both the input and output
    transport sides have released it), so the socket silently stayed open.
    worker.cancel() is the same, already-correct teardown path the hangup
    button already uses, which pushes a CancelFrame through the whole
    pipeline and properly closes both sides.

    Sleeps almost all the time — only wakes every IDLE_CHECK_INTERVAL_SECS
    to compare two timestamps read from `agent` — so this can't add latency
    to the actual conversation; the only work on the live audio/frame path
    is the one-line timestamp bumps already in AgentRuntimeProcessor.
    """
    try:
        while True:
            await asyncio.sleep(IDLE_CHECK_INTERVAL_SECS)
            if agent.seconds_since_activity() < IDLE_TIMEOUT_SECS:
                continue
            logger.info(f"[{visitor_id}] idle for {IDLE_TIMEOUT_SECS}s, ending call")
            await agent.speak_idle_farewell()
            # Give TTS a moment to actually start (BotStartedSpeakingFrame
            # lags slightly behind pushing the text) before polling for it
            # to finish — otherwise this could see "not speaking yet" and
            # cut the farewell off before a word of it plays. Capped at ~10s
            # total so a stuck flag can't wedge this task forever.
            await asyncio.sleep(0.5)
            for _ in range(95):
                if not agent.is_bot_speaking():
                    break
                await asyncio.sleep(0.1)
            await worker.cancel()
            await _release_voice_lock(visitor_id)
            return
    except asyncio.CancelledError:
        pass


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    visitor_id = "voice-test"
    visitor_name = None
    visitor_company = None
    visitor_email = None
    body = getattr(runner_args, "body", None)
    if isinstance(body, dict) and body.get("visitorId"):
        visitor_id = body["visitorId"]
        visitor_name = body.get("name") or None
        visitor_company = body.get("company") or None
        visitor_email = body.get("email") or None
    else:
        # The plain-WebSocket runner path has no body/metadata channel at
        # all (unlike the old WebRTC /start flow) — visitorId (and, if given
        # on Meeting Mode's pre-join screen, name/company/email) travel as
        # query params on the WebSocket URL itself instead (see
        # frontend/src/lib/pipecatClient.ts).
        ws = getattr(runner_args, "websocket", None)
        query_params = getattr(ws, "query_params", {}) if ws else {}
        if query_params.get("visitorId"):
            visitor_id = query_params["visitorId"]
        visitor_name = query_params.get("name") or None
        visitor_company = query_params.get("company") or None
        visitor_email = query_params.get("email") or None

    # Seeds *this process's* session store with a personalized greeting
    # before AgentRuntimeProcessor/_greet ever touch it — server.py (the
    # REST API, port 8787) is a separate OS process with its own separate
    # in-memory session store, so anything captured there (see
    # POST /api/session/start) never reaches this one on its own. Only a
    # no-op for fields that are None (falls back to the generic greeting,
    # and _company_note in runtime.py just stays silent about company/email).
    start_session(visitor_id, visitor_name, visitor_company, visitor_email)

    # VAD is its own pipeline stage in this Pipecat version — it's what turns
    # raw audio into VADUserStartedSpeakingFrame/VADUserStoppedSpeakingFrame,
    # which GroqSTTService (a SegmentedSTTService) needs to know when to
    # buffer and when to send a segment off for transcription. Without this
    # stage, audio flows through the pipeline but STT never fires — which is
    # exactly what happened before this was added.
    #
    # stop_secs defaults to 0.2 — short enough that a normal mid-sentence
    # pause reads as "stopped speaking," chopping one utterance into several
    # segments each sent to the agent as an independent message. 0.8 gives
    # room for a natural breath without making replies feel sluggish.
    vad = VADProcessor(vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.8)))
    stt = GroqSTTService(api_key=os.getenv("GROQ_API_KEY"))
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        settings=CartesiaTTSService.Settings(
            voice=os.getenv("CARTESIA_VOICE_ID"),
            # Default pace read as sluggish on a live call; 1.3 then read as
            # too rushed. 1.15 is a middle ground — a noticeable pickup over
            # default without tipping into unnatural. Valid range per
            # Cartesia is [0.6, 1.5].
            generation_config=GenerationConfig(speed=1.15),
        ),
    )
    agent = AgentRuntimeProcessor(visitor_id)
    # Reports the agent's real speaking loudness to the client alongside its
    # audio — see TTSLevelReporter's docstring for why this exists (its
    # synthesized speech has no MediaStreamTrack the frontend could
    # otherwise measure directly, unlike the visitor's own mic).
    tts_level_reporter = TTSLevelReporter()

    pipeline = Pipeline(
        [
            transport.input(),
            vad,
            stt,
            agent,
            tts,
            tts_level_reporter,
            transport.output(),
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )
    idle_watch_task = asyncio.create_task(_watch_idle(agent, worker, visitor_id))

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client):
        logger.info(f"Voice client connected: {visitor_id}")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client):
        logger.info(f"Voice client disconnected: {visitor_id}")
        idle_watch_task.cancel()
        await worker.cancel()
        await _release_voice_lock(visitor_id)

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
