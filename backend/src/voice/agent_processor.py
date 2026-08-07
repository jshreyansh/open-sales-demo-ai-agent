import asyncio
import contextlib
import os
import random
import re
import subprocess
from typing import Dict

import aiohttp
from loguru import logger

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    OutputAudioRawFrame,
    StartFrame,
    TextFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from ..agent.runtime import run_turn
from ..context.store import OPENING_GREETING, get_session

REST_API_URL = "http://localhost:8787"

# One of two alternative ways to fill the "thinking" gap while run_turn()
# resolves — a spoken filler word, or this typing sound, chosen per turn
# (see TYPING_SOUND_PROBABILITY), never both layered together. The sound of
# "still working on it," the same way a support agent typing notes mid-call
# fills a silence naturally instead of leaving dead air.
TYPING_SOUND_PATH = os.path.join(os.path.dirname(__file__), "assets", "typing.mp3")
TYPING_SOUND_PROBABILITY = 0.5
TYPING_SOUND_VOLUME = 0.4
_CHUNK_MS = 20

_typing_pcm_cache: Dict[int, bytes] = {}


def _decode_typing_pcm(sample_rate: int) -> bytes:
    """Decode the typing sound effect to raw 16-bit mono PCM at the pipeline's
    actual output sample rate, once per rate (cheap after the first call —
    cached in-process). Shelling out to ffmpeg rather than adding an audio
    library dependency; it's already on the box and this only runs once."""
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-i", TYPING_SOUND_PATH,
                "-f", "s16le", "-acodec", "pcm_s16le",
                "-ar", str(sample_rate), "-ac", "1",
                "-filter:a", f"volume={TYPING_SOUND_VOLUME}",
                "-",
            ],
            capture_output=True,
            check=True,
        )
        return proc.stdout
    except Exception:
        logger.exception("Failed to decode typing sound effect — skipping it for this session")
        return b""


def _load_typing_pcm(sample_rate: int) -> bytes:
    if sample_rate not in _typing_pcm_cache:
        _typing_pcm_cache[sample_rate] = _decode_typing_pcm(sample_rate)
    return _typing_pcm_cache[sample_rate]


# One of two alternative ways to fill the "thinking" gap while run_turn()
# resolves — a spoken filler word, or the typing sound above, chosen per
# turn, never both. Spoken immediately on hearing a transcript, before
# run_turn() (an LLM round trip) even starts, the same way a person says
# "okay" or "let's see" while they're still forming a real answer, instead of
# going silent for the full 1-3s the LLM call takes. Pushed as its own TTS
# utterance ahead of run_turn() rather than after it, so Cartesia is already
# synthesizing/playing it while run_turn() runs in the background thread.
#
# Split into two pools because a filler that only makes sense as a reply to a
# question ("good question") read as wrong/confusing when the prospect had
# actually just made a statement — QUESTION_FILLERS is only drawn from when
# the transcript actually looks like a question (see _is_question).
NEUTRAL_FILLERS = ["Okay —", "Right —", "Got it —", "I hear you —", "Makes sense —", "Sure —"]
QUESTION_FILLERS = ["Good question —", "Great question —", "Let's see —"]

_QUESTION_STARTERS = frozenset(
    [
        "what", "why", "how", "when", "where", "who", "which", "whose",
        "is", "are", "was", "were", "do", "does", "did",
        "can", "could", "will", "would", "should", "shall",
    ]
)


def _is_question(text: str) -> bool:
    stripped = text.strip()
    if stripped.endswith("?"):
        return True
    first_word = re.split(r"[^a-zA-Z']+", stripped)[0].lower() if stripped else ""
    return first_word in _QUESTION_STARTERS


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
    an actual interruption yet. If that happens while the bot is actually
    speaking, broadcast a real Pipecat interruption, which cuts Cartesia off
    immediately and cancels any in-flight run_turn(). "Actually speaking" is
    tracked via BotStartedSpeakingFrame/BotStoppedSpeakingFrame — pipecat's
    own real playback state — not a length-based time estimate; an earlier
    version guessed speaking duration from text length, which drifted from
    real playback often enough that real interrupt attempts were silently
    dropped (confirmed via production logs: ~1 in 9 genuine attempts missed).

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
        self._bot_speaking = False
        self._last_filler = None
        self._greeted = False
        self._audio_out_sample_rate = 24000  # StartFrame's own default; overwritten once it arrives
        self._hand_raised = False
        self._hand_raise_poll_task: asyncio.Task | None = None
        # True only while a TranscriptionFrame's filler/run_turn/speak
        # sequence is actively running. Lets _poll_hand_raise tell "raised
        # while I'm mid-turn, defer to its natural end" from "raised while
        # I'm just sitting idle" — the latter needs to react immediately, or
        # a hand-raise with no follow-up speech would silently do nothing.
        self._turn_in_progress = False

    def _pick_filler(self, heard_text: str) -> str:
        pool = QUESTION_FILLERS + NEUTRAL_FILLERS if _is_question(heard_text) else NEUTRAL_FILLERS
        choices = [f for f in pool if f != self._last_filler] or pool
        filler = random.choice(choices)
        self._last_filler = filler
        return filler

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, StartFrame):
            # StartFrame is the one guaranteed-first frame every processor in
            # the pipeline receives — forward it before speaking so TTS (and
            # everything else downstream) has already run its own StartFrame
            # setup by the time _greet() pushes real audio-bound frames at it.
            self._audio_out_sample_rate = frame.audio_out_sample_rate
            await self.push_frame(frame, direction)
            if not self._greeted:
                self._greeted = True
                self._hand_raise_poll_task = asyncio.create_task(self._poll_hand_raise())
                await self._greet(direction)
            return

        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStartedSpeakingFrame):
            if self._bot_speaking:
                get_session(self._visitor_id).was_interrupted = True
                await self.broadcast_interruption()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            logger.info(f"[{self._visitor_id}] heard: {frame.text!r}")
            session = get_session(self._visitor_id)
            self._turn_in_progress = True

            try:
                typing_task = None
                if random.random() < TYPING_SOUND_PROBABILITY:
                    # Typing sound this turn, no spoken filler — the two are
                    # alternatives, not layered together.
                    typing_task = asyncio.create_task(self._play_typing_sound(direction))
                else:
                    filler = self._pick_filler(frame.text)
                    await self._speak(filler, direction)

                try:
                    result = await asyncio.to_thread(run_turn, frame.text, session)
                except Exception:
                    logger.exception(f"run_turn failed for visitor {self._visitor_id}")
                    result = {"reply": "Sorry, I lost my train of thought — could you say that again?"}

                if typing_task is not None:
                    # Stop dynamically the moment the real reply is ready, rather
                    # than a fixed-length clip — then a short deliberate beat of
                    # silence so it reads as "finished typing, about to talk,"
                    # not audio cutting off right as speech starts.
                    typing_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await typing_task
                    await asyncio.sleep(1.0)

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
                else:
                    if action:
                        asyncio.create_task(self._report_action(action))
                    asyncio.create_task(self._report_reply(reply))
                    await self._speak(reply, direction)

                if self._hand_raised:
                    # Caught a raise that happened while this turn was
                    # already running — the natural "finished my current
                    # topic" point, not mid-utterance. Hand-raise is
                    # deliberately the non-interrupting alternative to VAD
                    # barge-in: let the explanation finish, then hand off
                    # explicitly instead of auto-continuing to whatever would
                    # come next. (A raise while fully idle is instead caught
                    # and handled directly by _poll_hand_raise.)
                    self._hand_raised = False
                    await self._speak_hand_raise_handoff(direction)
            finally:
                self._turn_in_progress = False
            return

        await self.push_frame(frame, direction)

    async def _greet(self, direction: FrameDirection) -> None:
        # get_session() seeds a brand-new session's history with this exact
        # text (see context/store.py) — calling it here just ensures the
        # session exists yet before the prospect has said anything, so that
        # seeding has already happened by the time run_turn() looks at it.
        get_session(self._visitor_id)
        await self._speak(OPENING_GREETING, direction)
        asyncio.create_task(self._report_reply(OPENING_GREETING))

    async def _play_typing_sound(self, direction: FrameDirection) -> None:
        rate = self._audio_out_sample_rate
        pcm = await asyncio.to_thread(_load_typing_pcm, rate)
        if not pcm:
            return
        chunk_bytes = int(rate * _CHUNK_MS / 1000) * 2  # 16-bit mono
        if chunk_bytes <= 0:
            return
        try:
            while True:
                for i in range(0, len(pcm) - chunk_bytes, chunk_bytes):
                    await self.push_frame(
                        OutputAudioRawFrame(audio=pcm[i : i + chunk_bytes], sample_rate=rate, num_channels=1),
                        direction,
                    )
                    await asyncio.sleep(_CHUNK_MS / 1000)
        except asyncio.CancelledError:
            pass

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

    async def _speak_hand_raise_handoff(self, direction: FrameDirection) -> None:
        handoff = "Yes, go ahead — what's your question?"
        asyncio.create_task(self._report_reply(handoff))
        await self._speak(handoff, direction)

    async def _poll_hand_raise(self) -> None:
        # This process (the voice pipeline, :7860) and the REST API (:8787)
        # that the frontend's hand-raise button posts to are separate
        # processes — this poll is how a click over there becomes something
        # the live call actually reacts to, mirroring the existing
        # voice-action/voice-reply mailbox pattern in server.py, just in the
        # opposite direction.
        try:
            async with aiohttp.ClientSession() as http:
                while True:
                    await asyncio.sleep(1.0)
                    try:
                        async with http.get(
                            f"{REST_API_URL}/internal/hand-raise/{self._visitor_id}",
                            timeout=aiohttp.ClientTimeout(total=3),
                        ) as resp:
                            data = await resp.json()
                            if not data.get("raised"):
                                continue
                            if self._turn_in_progress:
                                # A turn (filler/run_turn/reply) is already
                                # running — let its own end-of-turn check
                                # (in process_frame) catch this instead, so
                                # the handoff waits for the current topic to
                                # actually finish rather than colliding with
                                # it mid-utterance.
                                self._hand_raised = True
                            else:
                                # Genuinely idle — nothing else is going to
                                # trigger a check, so react right here. This
                                # is the case a hand-raise is actually FOR:
                                # the prospect didn't say anything, they just
                                # raised their hand.
                                await self._speak_hand_raise_handoff(FrameDirection.DOWNSTREAM)
                    except Exception:
                        logger.exception(f"Failed to poll hand-raise for visitor {self._visitor_id}")
        except asyncio.CancelledError:
            pass

    async def cleanup(self):
        if self._hand_raise_poll_task is not None:
            self._hand_raise_poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._hand_raise_poll_task
        await super().cleanup()
