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
import json
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
from pipecat.observers.user_bot_latency_observer import UserBotLatencyObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.cartesia.tts import CartesiaTTSService, GenerationConfig
# Imported defensively. The Deepgram SDK is an optional extra, and a
# top-level import of it took production down: the box didn't have
# deepgram-sdk installed, this line raised ImportError at module scope, and
# the voicebot crash-looped — taking voice out entirely rather than falling
# back to Groq the way STT_PROVIDER was designed to.
#
# The fallback below is a RUNTIME choice, so it can only help if this module
# actually finishes importing. Optional dependencies therefore have to fail
# soft here, not hard.
try:
    from pipecat.services.deepgram.stt import DeepgramSTTService
except ImportError as _dg_err:  # pragma: no cover - depends on install extras
    DeepgramSTTService = None
    _DEEPGRAM_IMPORT_ERROR = str(_dg_err)
else:
    _DEEPGRAM_IMPORT_ERROR = None
from pipecat.services.groq.stt import GroqSTTService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner

from ..agent.runtime import generate_call_summary
from ..context.store import start_session
from ..data import gate_log
from ..data.email import send_summary_email
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


def log_latency_breakdown(visitor_id: str, breakdown) -> None:
    """Logs UserBotLatencyObserver's on_latency_breakdown event. Module-level
    (not a closure in run_bot) so it's independently testable without
    standing up a pipeline. Pipecat's event-handler dispatch already runs
    this as its own asyncio task rather than inline in the frame path (see
    BaseObject._call_event_handler) — still kept to a single json.dumps and
    one logger.info call so it stays negligible either way."""
    logger.info(
        "PIPELINE_LATENCY "
        + json.dumps(
            {
                "visitor_id": visitor_id,
                "user_turn_secs": breakdown.user_turn_secs,
                "ttfb": [t.model_dump() for t in breakdown.ttfb],
                "text_aggregation": (
                    breakdown.text_aggregation.model_dump()
                    if breakdown.text_aggregation
                    else None
                ),
                "function_calls": [f.model_dump() for f in breakdown.function_calls],
            },
            separators=(",", ":"),
            default=str,
        )
    )


def log_first_bot_speech_latency(visitor_id: str, latency_seconds: float) -> None:
    logger.info(
        f"PIPELINE_FIRST_SPEECH_LATENCY visitor_id={visitor_id} "
        f"latency_s={latency_seconds:.3f}"
    )


def log_pipeline_turn_ended(
    visitor_id: str, turn_count: int, duration: float, was_interrupted: bool
) -> None:
    logger.info(
        f"PIPELINE_TURN_ENDED visitor_id={visitor_id} turn={turn_count} "
        f"duration_s={duration:.3f} interrupted={was_interrupted}"
    )


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
            # to_thread because Postmark goes out over blocking `requests`,
            # same reasoning as generate_call_summary above. The send never
            # raises (it swallows and returns None) and is idempotent against
            # the summary_emails table, so neither a dead mail provider nor a
            # second teardown can break the hang-up path or double-mail
            # anyone.
            await asyncio.to_thread(send_summary_email, visitor_id, summary)
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
    # stop_secs 1.0 -> 0.3.
    #
    # This was 1.0 for a good reason at the time: without it, a natural
    # breath split one sentence into several transcripts, each answered
    # separately. That reason is gone. The consolidation window in
    # agent_processor.py now accumulates fragments and answers once, so
    # fragmentation is handled a layer up — and holding VAD at 1.0s on top
    # of it means the SAME SILENCE IS COUNTED TWICE:
    #
    #   1.0s (VAD decides speech ended) + 1.5s (consolidation decides the
    #   thought ended) = 2.5s of real silence before she says anything.
    #
    # The consolidation window is the honest "are they finished" timer —
    # it measures human pause length. VAD's only remaining jobs are
    # detecting barge-in (start_secs, untouched) and telling Deepgram when
    # to Finalize. Both want VAD to notice quickly, not slowly.
    #
    # 0.3 rather than 0.0: still enough to debounce a clipped word, and it
    # keeps the Finalize signal from firing mid-sentence on every pause.
    #
    # Dropping it did NOT go cleanly the first time, and the reason is worth
    # keeping. Lowering stop_secs silently changed what the word "fragment"
    # meant one layer up: the consolidation window grew itself on each
    # fragment on the theory that a fragment implied a deliberate pause, and
    # at 0.3 a fragment became a breath instead. One ordinary sentence then
    # produced four of them, drove the window to its 2.6s ceiling, and
    # restarted the clock on every breath — measured median went 4.0s to
    # 7.6s, worse than the 1.0 it replaced.
    #
    # The fix was not to put stop_secs back. It was to make that window key
    # off the measured gap between fragments (FRAGMENT_PAUSE_MIN_GAP_SECS in
    # agent_processor.py) so it responds to how the human actually paused
    # rather than to how VAD happened to segment. Both layers are now free
    # to be tuned independently, which is what the split was supposed to buy
    # in the first place — so if you retune this number, that invariant is
    # the one to re-check.
    vad = VADProcessor(vad_analyzer=SileroVADAnalyzer(params=VADParams(start_secs=0.12, stop_secs=0.3)))
    # `prompt` is Whisper's standard vocabulary-biasing hint — it doesn't
    # force these words, just nudges ambiguous audio toward them. Added
    # after a real call transcribed "give me a walkthrough" as "give me a
    # vote" — nothing in the audio pipeline knew "walkthrough" was even a
    # plausible word in this domain. Kept short and product-specific rather
    # than a long list, since Whisper's prompt has real diminishing returns
    # (and a hard length cap) past a short, high-value set.
    # Words the demo depends on and that generic models reliably mangle.
    # Real transcripts from Groq: "magic real lot" (MagicReel), "ContentIQ,
    # Ss.", "What do you do Shifiona?" — a prospect hearing the agent
    # confidently misname its own product is a credibility problem, not a
    # cosmetic one.
    STT_KEYTERMS = [
        "SwishX", "MagicReel", "MagicAvatar", "MagicChart", "Content Studio",
        "MLR", "dossier", "HCP", "Fiona", "Tecentriq", "walkthrough",
    ]

    # Deepgram by default, Groq as the escape hatch.
    #
    # These are architecturally different, not interchangeable: Groq's is a
    # SegmentedSTTService (buffers audio, transcribes once VAD declares the
    # segment over) while Deepgram's is a live streaming service that does
    # its own endpointing. Everything in AgentRuntimeProcessor keys off WHEN
    # a finalized transcript arrives, so the swap is a real change to turn
    # timing, not a drop-in.
    #
    # The division of labour that makes it safe: Deepgram decides WHAT WORDS
    # were said; this pipeline keeps deciding WHEN TO RESPOND. Deepgram is
    # configured to finalize eagerly (short endpointing) and the
    # consolidation window in agent_processor.py accumulates whatever
    # fragments result and answers once. More, earlier fragments are exactly
    # what that window was built for, so Deepgram's endpointing never
    # competes with Smart Turn.
    #
    # interim_results stays off: only finalized TranscriptionFrames drive a
    # turn here, and emitting interims would add frames the pipeline
    # deliberately ignores.
    #
    # STT_PROVIDER=groq reverts instantly with no code change — this is a
    # paid dependency on a live demo, so a billing lapse or an outage should
    # be one env var away from working, not a redeploy.
    _stt_provider = (os.getenv("STT_PROVIDER") or "deepgram").strip().lower()
    _deepgram_key = os.getenv("DEEPGRAM_API_KEY")
    if _stt_provider == "deepgram" and _deepgram_key and DeepgramSTTService is None:
        # Configured for Deepgram, credentialed for it, but the SDK isn't
        # installed. Say so loudly and take Groq — a degraded ear beats a
        # dead pipeline.
        logger.error(
            f"STT_PROVIDER=deepgram and DEEPGRAM_API_KEY is set, but the Deepgram SDK is "
            f"missing ({_DEEPGRAM_IMPORT_ERROR}). Falling back to Groq. "
            f"Fix with: pip install deepgram-sdk"
        )
    if _stt_provider == "deepgram" and _deepgram_key and DeepgramSTTService is not None:
        stt = DeepgramSTTService(
            api_key=_deepgram_key,
            settings=DeepgramSTTService.Settings(
                model="nova-3",
                language="en",
                smart_format=True,
                punctuate=True,
                # ON, deliberately. This was False in the first pass, which
                # was backwards: utterance_end_ms REQUIRES interim results
                # (Deepgram's docs are explicit), and interim decoding is
                # what lets Deepgram commit a final the instant speech ends
                # rather than starting work then. The pipeline still only
                # ACTS on finalized TranscriptionFrames — InterimTranscription
                # frames are ignored downstream — so this costs nothing here
                # and unlocks the two signals below.
                interim_results=True,
                # nova-3 keyterm prompting — biases decoding toward these
                # exact strings.
                keyterm=STT_KEYTERMS,
                # speech_final fires on a detected pause (tens-to-hundreds of
                # ms). Cheap and fast.
                endpointing=300,
                # UtteranceEnd is the safety net speech_final doesn't give
                # you: it works off word TIMINGS rather than volume, so it
                # still fires in a noisy room where a silence-based endpoint
                # never triggers. Deepgram documents exactly this failure
                # mode, and a noisy room is the normal case for a live demo.
                utterance_end_ms=1000,
            ),
        )
        logger.info(f"STT: deepgram nova-3 ({len(STT_KEYTERMS)} keyterms)")
    else:
        stt = GroqSTTService(
            api_key=os.getenv("GROQ_API_KEY"),
            prompt=", ".join(STT_KEYTERMS),
        )
        logger.info(
            "STT: groq whisper"
            + ("" if _stt_provider == "groq" else " (deepgram key missing — fell back)")
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
    # Passed the agent so it can timestamp the first real output audio frame of
    # each turn — see turn_telemetry.py. Without this, acoustic TTFA has no
    # source in the pipeline at all and we'd be left reporting TTS enqueue time
    # as though it were audio.
    tts_level_reporter = TTSLevelReporter(agent)

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

    # Pipeline-level latency, independent of our own turn-taking telemetry
    # (turn_telemetry.py) — that module knows WHY our logic released a turn;
    # this observer knows the raw wall-clock cost of each service in between
    # (STT/LLM/TTS TTFB, text aggregation) from MetricsFrames the pipeline
    # already emits (enable_metrics=True below). Kept as two separate log
    # streams rather than merged into one record: correlating by visitor_id
    # and rough timestamp is enough to reconstruct a call, and forcing a
    # shared turn id between a Pipecat-native observer and our own turn
    # counter would require threading state neither side otherwise needs.
    latency_observer = UserBotLatencyObserver()
    latency_observer.event_handler("on_latency_breakdown")(
        lambda _observer, breakdown: log_latency_breakdown(visitor_id, breakdown)
    )
    latency_observer.event_handler("on_first_bot_speech_latency")(
        lambda _observer, latency_seconds: log_first_bot_speech_latency(visitor_id, latency_seconds)
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        observers=[latency_observer],
    )

    # TurnTrackingObserver is already created internally (enable_turn_tracking
    # defaults to True) but nothing was consuming it — this just attaches
    # logging to pipeline-native turn boundaries, a cross-check independent
    # of our own settle/stall-backstop/fast-track release logic.
    if worker.turn_tracking_observer is not None:
        worker.turn_tracking_observer.event_handler("on_turn_ended")(
            lambda _observer, turn_count, duration, was_interrupted: log_pipeline_turn_ended(
                visitor_id, turn_count, duration, was_interrupted
            )
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
