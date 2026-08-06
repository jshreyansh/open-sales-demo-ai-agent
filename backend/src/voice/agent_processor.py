import asyncio
import time

import aiohttp
from loguru import logger

from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from ..agent.runtime import run_turn
from ..context.store import get_session

REST_API_URL = "http://localhost:8787"


def _estimate_speaking_seconds(text: str) -> float:
    """Conservative (slow) estimate of how long TTS will take to speak this
    reply out loud — used only to guess whether a VAD "user started
    speaking" event landed mid-playback (a real interruption) or after Emma
    was already done. Erring slow occasionally mislabels a stray post-reply
    VAD blip as an interruption; erring fast would miss real ones, which is
    worse."""
    return max(1.5, len(text) / 12.0) + 0.3


class AgentRuntimeProcessor(FrameProcessor):
    """Bridges the voice pipeline to the existing Agent Runtime.

    Sits where an LLM service normally would: it takes the STT's finalized
    transcript, calls the exact same `run_turn()` used by the text chat (same
    registry, same session store, same Claude tool-use + keyword fallback),
    and pushes the reply downstream as a TextFrame for TTS to speak.

    If the turn produced a UI action, it's reported to the main REST API
    (a separate process on :8787) so the frontend's existing polling can pick
    it up and drive the product the same way a chat-triggered action does.

    Also handles barge-in: Silero VAD (already in the pipeline) emits
    VADUserStartedSpeakingFrame the moment the visitor starts talking,
    regardless of which STT service is plugged in — Groq's segmented,
    non-streaming nature doesn't block this signal, nobody had wired it to
    an actual interruption yet. If that happens while a reply is still
    (estimated to be) playing, broadcast a real Pipecat interruption, which
    cuts Cartesia off immediately and cancels any in-flight run_turn().

    When a turn includes an action, run_turn() also returns a "lead_in" — a
    short transition ("let me pull that up") meant to be said, then the
    action fires, then "reply" (the actual explanation) follows. This is
    spoken as two separate TTS utterances in that exact order, so the action
    lands deterministically in the gap between them — not guessed at via
    word-level text matching or a fixed delay, both of which were tried and
    didn't hold up.
    """

    def __init__(self, visitor_id: str):
        super().__init__()
        self._visitor_id = visitor_id
        self._speaking_until = 0.0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, VADUserStartedSpeakingFrame):
            if time.monotonic() < self._speaking_until:
                get_session(self._visitor_id).was_interrupted = True
                self._speaking_until = 0.0
                await self.broadcast_interruption()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            logger.info(f"[{self._visitor_id}] heard: {frame.text!r}")
            session = get_session(self._visitor_id)
            try:
                result = await asyncio.to_thread(run_turn, frame.text, session)
            except Exception:
                logger.exception(f"run_turn failed for visitor {self._visitor_id}")
                result = {"reply": "Sorry, I lost my train of thought — could you say that again?"}

            logger.info(f"[{self._visitor_id}] replying: {result!r}")

            action = result.get("action")
            lead_in = result.get("lead_in")
            reply = result["reply"]

            if action and lead_in:
                # Speak the transition first, report the action in the gap,
                # then speak the explanation as its own separate utterance —
                # this is what makes the ordering deterministic instead of a
                # guess based on timing or word matching.
                asyncio.create_task(self._report_reply(lead_in))
                await self._speak(lead_in, direction)
                asyncio.create_task(self._report_action(action))
                asyncio.create_task(self._report_reply(reply))
                await self._speak(reply, direction)
                spoken_text = f"{lead_in} {reply}"
            else:
                if action:
                    asyncio.create_task(self._report_action(action))
                asyncio.create_task(self._report_reply(reply))
                await self._speak(reply, direction)
                spoken_text = reply

            self._speaking_until = time.monotonic() + _estimate_speaking_seconds(spoken_text)
            return

        await self.push_frame(frame, direction)

    async def _speak(self, text: str, direction: FrameDirection) -> None:
        # TTSService only flushes its sentence-aggregation buffer on an
        # LLMFullResponseEndFrame (or EndFrame) — a bare TextFrame gets
        # buffered and never actually synthesized. Bracketing this way is
        # what a real streaming LLM service's output would normally do; we
        # just do it in one shot per utterance since run_turn() already
        # returns complete text.
        await self.push_frame(LLMFullResponseStartFrame(), direction)
        await self.push_frame(TextFrame(text), direction)
        await self.push_frame(LLMFullResponseEndFrame(), direction)

    async def _report_action(self, action: dict) -> None:
        try:
            async with aiohttp.ClientSession() as http:
                await http.post(
                    f"{REST_API_URL}/internal/voice-action",
                    json={"visitorId": self._visitor_id, "action": action},
                    timeout=aiohttp.ClientTimeout(total=3),
                )
        except Exception:
            logger.exception(f"Failed to report voice action for visitor {self._visitor_id}")

    async def _report_reply(self, reply: str) -> None:
        try:
            async with aiohttp.ClientSession() as http:
                await http.post(
                    f"{REST_API_URL}/internal/voice-reply",
                    json={"visitorId": self._visitor_id, "reply": reply},
                    timeout=aiohttp.ClientTimeout(total=3),
                )
        except Exception:
            logger.exception(f"Failed to report voice reply for visitor {self._visitor_id}")
