"""Voice entrypoint for the demo agent.

Runs as its own Pipecat server, separate from the REST API (server.py, port
8787). STT (Groq/Whisper) -> AgentRuntimeProcessor (calls the same
run_turn() the text chat uses) -> TTS (Cartesia) -> back to the browser.

Run standalone to verify the voice loop works before wiring it into the
actual React frontend — Pipecat's runner serves a prebuilt WebRTC test page
for exactly this:

    source .venv/bin/activate
    python -m src.voice.bot

Then open the URL it prints (defaults to http://localhost:7860).
"""

import os

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
from pipecat.services.cartesia.tts import CartesiaTTSService, GenerationConfig
from pipecat.services.groq.stt import GroqSTTService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner

from .agent_processor import AgentRuntimeProcessor

transport_params = {
    "webrtc": lambda: TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    visitor_id = "voice-test"
    body = getattr(runner_args, "body", None)
    if isinstance(body, dict) and body.get("visitorId"):
        visitor_id = body["visitorId"]

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

    pipeline = Pipeline(
        [
            transport.input(),
            vad,
            stt,
            agent,
            tts,
            transport.output(),
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client):
        logger.info(f"Voice client connected: {visitor_id}")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client):
        logger.info(f"Voice client disconnected: {visitor_id}")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)
    await runner.run()


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
