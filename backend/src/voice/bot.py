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
import random

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

from ..agent.runtime import generate_call_summary
from ..context.store import start_session
from ..data import gate_log
from .agent_processor import (
    IDLE_CHECK_INTERVAL_SECS,
    IDLE_CHECKIN_THRESHOLD_SECS,
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


async def _save_call_summary(visitor_id: str) -> None:
    """Fired as a background task from on_client_disconnected, right when a
    call actually ends, so the AI call summary (see runtime.py's
    generate_call_summary) is normally already cached by the time an admin
    looks at this visitor in /admin — the endpoint there only needs its
    on-demand fallback for the rare case this hasn't finished yet. Runs the
    underlying LLM call in a thread since the Anthropic SDK call it makes is
    synchronous/blocking, and this must not stall the event loop other
    in-flight work (idle-watch teardown, voice-lock release above) runs on."""
    try:
        summary = await asyncio.to_thread(generate_call_summary, visitor_id)
        if summary:
            gate_log.save_call_summary(visitor_id, summary)
    except Exception:
        logger.exception(f"Failed to generate/save call summary for visitor {visitor_id}")


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

    Also fires one short spoken check-in (agent.speak_idle_checkin) the
    first time idle time crosses IDLE_CHECKIN_THRESHOLD_SECS — filling the
    otherwise-dead air before the real IDLE_TIMEOUT_SECS farewell, the way
    a real rep breaks a long silence once rather than saying nothing until
    hanging up (and not more than once — a rep doesn't keep asking "still
    there?" every 15 seconds either). `checkin_owed` tracks whether this
    idle streak still owes its one nudge, jittered by a few seconds at
    streak-start so it doesn't land on the exact same second every call;
    it's reset whenever agent.last_activity_timestamp() changes (real
    activity happened — a fresh streak starts, the nudge is owed again).
    Compares the raw timestamp, not the derived seconds-since-activity
    value — an earlier version compared the derived value and an
    automated stress test caught it silently swallowing a reset that
    happened while this loop was blocked inside its own
    await agent.speak_idle_checkin() call (see last_activity_timestamp's
    docstring for why the derived value can't reliably catch that).

    seconds_since_activity() reads _last_activity — the SAME clock
    _watch_auto_continue_stall uses, deliberately: a visitor silently
    listening to an active, still-progressing walkthrough is real
    engagement, not abandonment, and this clock has to see it that way or
    the farewell fires mid-walkthrough (confirmed live: a call where the
    visitor said one thing, then just listened to seven straight
    walkthrough beats for two minutes — real, continuous progress the
    whole time — still got disconnected as abandoned, back when this read
    a visitor-only clock instead). The one thing that must NOT bump this
    clock is the check-in/farewell's own speech — agent.speak_idle_checkin/
    speak_idle_farewell guard that themselves (see
    _speak_without_activity_bump's docstring), so this loop's view of
    elapsed idle time is never thrown off by the utterances it triggers.
    """
    checkin_threshold = IDLE_CHECKIN_THRESHOLD_SECS + random.uniform(-3, 3)
    checkin_owed = True
    last_activity_ts = agent.last_activity_timestamp()
    try:
        while True:
            await asyncio.sleep(IDLE_CHECK_INTERVAL_SECS)
            current_ts = agent.last_activity_timestamp()
            if current_ts != last_activity_ts:
                # Real activity landed at some point since the last poll —
                # new streak, the nudge is owed again.
                last_activity_ts = current_ts
                checkin_threshold = IDLE_CHECKIN_THRESHOLD_SECS + random.uniform(-3, 3)
                checkin_owed = True
            idle_for = agent.seconds_since_activity()

            if idle_for >= IDLE_TIMEOUT_SECS:
                logger.info(f"[{visitor_id}] idle for {IDLE_TIMEOUT_SECS}s, ending call")
                await agent.speak_idle_farewell()
                # speak_idle_farewell (via _speak_without_activity_bump) already
                # waits for its own playback to finish, so this is a fast no-op
                # in the common case — kept as a safety net in case that wait
                # was ever cut short for some reason.
                for _ in range(95):
                    if not agent.is_bot_speaking():
                        break
                    await asyncio.sleep(0.1)
                await worker.cancel()
                await _release_voice_lock(visitor_id)
                asyncio.create_task(_save_call_summary(visitor_id))
                return

            # The mid-silence check-in used to fire here. Removed.
            #
            # It read as nagging rather than attentive. Real sessions kept
            # landing it at the worst possible moments: while the prospect
            # was still mid-sentence (speak_idle_checkin has no guards at
            # all — it never checked whether anyone was talking), while they
            # watched a rendered video with nothing to say, and — the one
            # that decided it — 35 seconds after a prospect deliberately
            # asked for quiet to do some work. Being asked "still there?"
            # right after saying "give me a minute" is worse than silence.
            #
            # A real rep in that situation says nothing. So now the call
            # simply stays quiet and, if nobody speaks for
            # IDLE_TIMEOUT_SECS, hangs up with the farewell below —
            # one clean ending instead of a nag followed by an ending.
            #
            # speak_idle_checkin() itself is left in place on the processor:
            # nothing calls it, and deleting it would also drop the
            # transcript-persistence pattern that the farewell still relies
            # on. checkin_owed/checkin_threshold below are now unused but
            # kept so the streak-reset bookkeeping above reads unchanged.
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
    # segments each sent to the agent as an independent message. 1.0 gives
    # more room than the original 0.8 for a natural breath (or a second
    # voice chiming in) to land inside the same segment instead of becoming
    # its own separate transcript — see AgentRuntimeProcessor's turn-lock,
    # which is the other half of handling overlapping speech; this just
    # reduces how often it needs to kick in.
    #
    # start_secs defaults to 0.2 — how long a real barge-in has to wait
    # before VAD will even declare "user started speaking" at all. Measured
    # on a real interrupted call: once VAD fires, broadcast_interruption
    # cuts audio in ~5ms — the entire perceived "lag before it goes silent"
    # people notice on barge-in is this confirmation window, not anything
    # downstream. Trimmed to 0.12 to make barge-in read as prompt rather
    # than laggy; kept above 0 (rather than removed entirely) since that's
    # the debounce against false-triggering on a breath/cough/mic bleed —
    # the exact false-VAD problem this pipeline already fought once. Re-test
    # for false positives before trimming further.
    vad = VADProcessor(vad_analyzer=SileroVADAnalyzer(params=VADParams(start_secs=0.12, stop_secs=1.0)))
    # `prompt` is Whisper's standard vocabulary-biasing hint — it doesn't
    # force these words, just nudges ambiguous audio toward them. Added
    # after a real call transcribed "give me a walkthrough" as "give me a
    # vote" — nothing in the audio pipeline knew "walkthrough" was even a
    # plausible word in this domain. Kept short and product-specific rather
    # than a long list, since Whisper's prompt has real diminishing returns
    # (and a hard length cap) past a short, high-value set.
    stt = GroqSTTService(
        api_key=os.getenv("GROQ_API_KEY"),
        prompt="SwishX, walkthrough, MagicReel, MagicAvatar, Content Studio, MLR, dossier",
    )
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
        asyncio.create_task(_save_call_summary(visitor_id))

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
