import array
import asyncio
import contextlib
import random
import re
import time
import uuid
from typing import Optional

import aiohttp
from loguru import logger

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    OutputTransportMessageFrame,
    StartFrame,
    TextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from ..agent.runtime import run_turn_stream, run_walkthrough_continuation
from ..context.store import OPENING_GREETING, get_session

# Short "breathing room" between one walkthrough beat finishing and the next
# starting on its own — long enough that an interruption landing right after
# the bot stops speaking still lands cleanly (see AgentRuntimeProcessor's
# VADUserStartedSpeakingFrame handling, which cancels a pending auto-continue
# the instant real speech starts), short enough that it still reads as one
# continuous presenter talking, not "waiting for a response" silence.
AUTO_CONTINUE_PAUSE_SECS = 0.1

# Safety-net poll interval for _watch_auto_continue_stall (see that method's
# docstring) — cheap (a few attribute reads), so this doesn't need to be
# tight; it only affects how quickly a dead auto-continue chain gets
# noticed and revived, not anything on the live speaking path.
AUTO_CONTINUE_WATCHDOG_INTERVAL_SECS = 2.0
# How long things must have been quiet (no VAD/turn activity) before the
# watchdog will self-heal a stalled chain — long enough that a real
# in-progress utterance (VAD fired, transcript still pending) isn't mistaken
# for a dead chain.
AUTO_CONTINUE_STALL_GRACE_SECS = 2.0

REST_API_URL = "http://localhost:8787"

# Ends the call after this much total silence from both sides — someone who
# mutes and walks away without hanging up would otherwise hold this box's
# one call slot (see server.py's single-call gate) indefinitely. 2 minutes,
# not longer: every extra idle minute is a minute the whole demo is
# unusable for the next visitor, and two full silent minutes on a live
# voice call is already a strong abandonment signal — normal conversation
# has pauses, not two straight minutes where neither side says anything.
IDLE_TIMEOUT_SECS = 120
# How often the background watcher (see bot.py's run_bot) wakes up to
# check — cheap (one timestamp comparison), so this doesn't need to be
# tight; it only affects how quickly an abandoned call is caught, not
# anything in the live path.
IDLE_CHECK_INTERVAL_SECS = 15

# Fills the "thinking" gap while run_turn() resolves (an LLM round trip,
# ~1-3s). Spoken immediately on hearing a transcript, before run_turn() even
# starts, the same way a person says "hmm" or "let's see" while they're still
# forming a real answer, instead of going silent for the full 1-3s the LLM
# call takes. Pushed as its own TTS utterance ahead of run_turn() rather than
# after it, so Cartesia is already synthesizing/playing it while run_turn()
# runs in the background thread.
#
# A non-speech "typing sound" effect used to be an alternative to this,
# coin-flipped per turn — removed. No production voice-agent platform
# researched (Vapi, Retell, Bland, LiveKit, Agora, Pipecat's own examples)
# uses a keyboard-clack sound for this; every one uses short spoken filler
# instead, and a literal typing noise from a voice-only persona read as more
# confusing than reassuring. Spoken filler only, always.
#
# Phrases lean toward short listening/processing sounds ("Hmm —", "Mhm —")
# rather than task-acknowledgement phrasing ("Got it —", "I hear you —",
# "Makes sense —") — the latter read as a support-workflow bot confirming
# receipt of a ticket, not a person still thinking. Matches the pattern
# ChatGPT's own voice mode and Agora's Conversational AI filler-word feature
# both use: short, replaceable, no immediate repeat (see _pick_filler).
#
# Split into two pools because a filler that only makes sense as a reply to a
# question ("good question") read as wrong/confusing when the prospect had
# actually just made a statement — QUESTION_FILLERS is only drawn from when
# the transcript actually looks like a question (see _is_question).
NEUTRAL_FILLERS = ["Okay —", "Right —", "Sure —", "Hmm —", "Mhm —", "Let me see —"]
QUESTION_FILLERS = ["Good question —", "Great question —", "Let's see —"]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    """Rough sentence splitter — good enough for spoken replies (short,
    plain punctuation), not meant to handle abbreviations or edge cases a
    real NLP sentence tokenizer would. Used by _speak_reply so a hand-raise
    mid-reply can interrupt at a sentence boundary instead of only after the
    whole thing."""
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text.strip()) if p.strip()]
    return parts or [text]


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

    Also holds a turn-lock (_turn_in_progress) so a second person talking on
    the same call while one turn is still being answered doesn't spawn a
    second, independent run_turn() — Pipecat frames arrive one at a time
    already, so there was never a race here, but nothing was actually
    guarding against two *sequential, back-to-back* full turns either: a
    finalized TranscriptionFrame that lands while _turn_in_progress is still
    true is dropped rather than answered, since there's no per-speaker
    identity on this WebSocket transport to know whether it's a genuine
    follow-up from the same visitor or crosstalk from someone else in the
    room (real barge-in — interrupting the bot while it's actively
    speaking — is the separate, already-correct VADUserStartedSpeakingFrame
    path above; this only covers a second transcript finalizing while the
    bot itself is still silently working on the first one).
    """

    def __init__(self, visitor_id: str):
        super().__init__()
        self._visitor_id = visitor_id
        self._bot_speaking = False
        self._last_filler = None
        self._greeted = False
        self._audio_out_sample_rate = 24000  # StartFrame's own default; overwritten once it arrives
        # Mirrors the backend's current hand-raise state (see server.py's
        # _hand_raise_state) — the visitor controls this directly via a
        # toggle button, not a timer, so this only ever changes on the next
        # poll after an actual click.
        self._hand_raised = False
        # Whether the handoff line has already been spoken for the CURRENT
        # raise — set the moment it's spoken, reset back to False whenever
        # the raise transitions low->high (a fresh raise) or high->low (the
        # visitor lowered it, so the next raise starts clean). This is what
        # makes a raise get exactly one handoff no matter how long it stays
        # up or how many poll ticks see it, instead of repeating.
        self._hand_ack_sent = False
        self._hand_raise_poll_task: asyncio.Task | None = None
        # Set on BotStartedSpeakingFrame, cleared on BotStoppedSpeakingFrame —
        # lets _speak_reply wait for one sentence's real playback to actually
        # finish before speaking the next, so a hand-raise mid-reply can be
        # caught at the next sentence boundary instead of only after the
        # whole explanation. Starts set (idle = "nothing playing").
        self._speech_finished = asyncio.Event()
        self._speech_finished.set()
        # True only while a TranscriptionFrame's filler/run_turn/speak
        # sequence is actively running. Lets _poll_hand_raise tell "raised
        # while I'm mid-turn, defer to its natural end" from "raised while
        # I'm just sitting idle" — the latter needs to react immediately, or
        # a hand-raise with no follow-up speech would silently do nothing.
        self._turn_in_progress = False
        # Set the moment a real barge-in (VADUserStartedSpeakingFrame while
        # actually speaking) fires, reset at the start of each new turn.
        # broadcast_interruption() only cuts off whatever's already in the
        # Pipecat pipeline (the sentence currently playing) — it can't stop
        # this processor's own sentence-by-sentence loops (_speak_reply,
        # _run_turn_streamed's _flush_ready_sentences) from queuing up the
        # NEXT sentence right after. Those loops check this flag themselves
        # to stop speaking early instead of talking over the interruption.
        self._interrupted_this_turn = False
        # Bumped on any real speech from either side (see BotStartedSpeakingFrame/
        # VADUserStartedSpeakingFrame below) — read via seconds_since_activity()
        # by bot.py's idle watcher to detect an abandoned call. A plain
        # timestamp write is the only per-frame cost, so tracking this adds
        # no measurable latency to the actual conversation.
        self._last_activity = time.monotonic()
        # The scheduled "speak the next walkthrough beat on your own" task
        # (see _maybe_schedule_auto_continue) — held so it can be cancelled
        # the instant real speech starts (VADUserStartedSpeakingFrame below)
        # or a real turn begins (TranscriptionFrame handler), rather than
        # firing on top of/racing against something the prospect actually
        # said. None whenever nothing is scheduled.
        self._pending_auto_continue: Optional[asyncio.Task] = None
        # See _watch_auto_continue_stall's docstring — self-healing safety
        # net for the case above where a pending beat gets cancelled by a
        # VAD trigger that never turns into a real transcript.
        self._auto_continue_watchdog_task: Optional[asyncio.Task] = None
        # True between VADUserStartedSpeakingFrame and VADUserStoppedSpeakingFrame —
        # ground truth for "is the visitor currently mid-utterance," independent
        # of _last_activity's timestamp. A real sentence can easily take
        # several seconds to say and transcribe; _watch_auto_continue_stall
        # must never reschedule while this is True, no matter how long it's
        # been, or it races ahead of speech that just hasn't finished yet.
        self._user_speaking = False
        # A real interruption's transcript that queue_frame() had to drop
        # because it landed while a beat was still mid-turn — see
        # queue_frame's docstring. Stashed here instead of discarded, and
        # replayed as a real turn the moment the in-flight beat finishes
        # (see _maybe_replay_pending_interruption), so a genuine barge-in's
        # actual words are never just thrown away.
        self._pending_interruption_text: Optional[str] = None

    def _pick_filler(self, heard_text: str) -> str:
        pool = QUESTION_FILLERS + NEUTRAL_FILLERS if _is_question(heard_text) else NEUTRAL_FILLERS
        choices = [f for f in pool if f != self._last_filler] or pool
        filler = random.choice(choices)
        self._last_filler = filler
        return filler

    async def queue_frame(self, frame, direction=FrameDirection.DOWNSTREAM, callback=None):
        # This — not a check inside process_frame() — is where the turn-lock
        # actually has to live. Pipecat drains its internal process queue one
        # frame at a time, fully awaiting each process_frame() call before
        # dequeuing the next, so by the time a second TranscriptionFrame that
        # arrived mid-turn is finally dequeued, the first turn has always
        # already finished and _turn_in_progress is back to False — a guard
        # placed in process_frame() would never fire. queue_frame() is called
        # by the upstream STT stage in real time as each segment finalizes,
        # independent of whether this processor's own process_frame() is
        # still busy, which is what makes checking the lock here actually
        # correct: it sees the true state at the moment the frame arrives,
        # not at the moment it's eventually processed.
        if isinstance(frame, TranscriptionFrame) and frame.text.strip() and self._turn_in_progress:
            # Always stash, never drop — this used to be conditional on
            # self._interrupted_this_turn (only stash if THIS turn was the
            # one VAD marked as interrupted), which sounds right but isn't:
            # _interrupted_this_turn resets at the start of every new turn,
            # while the transcript that explains a barge-in routinely arrives
            # several seconds later (STT lag) — long enough, especially at
            # today's fast auto-continue pacing, for a fresh, never-interrupted
            # beat to already be running by the time it lands. The flag was
            # answering "was THIS turn interrupted" when the real question is
            # "did the person say something that hasn't been answered yet" —
            # true regardless of which turn happens to be running when it
            # finally arrives. Any transcript reaching here at all means real
            # speech happened while we were mid-turn; _advance_after_turn
            # replays it as a real turn the instant the in-flight beat ends,
            # so it's always heard and answered instead of silently skipped.
            logger.info(f"[{self._visitor_id}] stashing transcript mid-turn: {frame.text!r}")
            self._pending_interruption_text = frame.text
            return
        await super().queue_frame(frame, direction, callback)

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
                self._auto_continue_watchdog_task = asyncio.create_task(self._watch_auto_continue_stall())
                await self._greet(direction)
            return

        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
            self._speech_finished.clear()
            self._last_activity = time.monotonic()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
            self._speech_finished.set()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._last_activity = time.monotonic()
            self._user_speaking = True
            # Real speech starting is the single clearest "abort whatever's
            # scheduled" signal there is — cancel a pending auto-continue
            # here regardless of whether the bot is currently mid-sentence
            # (the _bot_speaking branch below) or was about to speak again
            # after its pause (this branch also covers that case, since the
            # pause is exactly when _bot_speaking is False but a beat is
            # still queued up).
            self._cancel_pending_auto_continue()
            if self._bot_speaking:
                get_session(self._visitor_id).was_interrupted = True
                self._interrupted_this_turn = True
                await self.broadcast_interruption()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStoppedSpeakingFrame):
            # Marks "no longer mid-utterance" for _watch_auto_continue_stall
            # (see its docstring) — also re-bumps _last_activity so the
            # watchdog's grace period restarts from when the person actually
            # finished talking (covering STT's own processing lag) rather
            # than from when they started, which is what let it race ahead
            # of a still-in-progress sentence earlier tonight.
            self._user_speaking = False
            self._last_activity = time.monotonic()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            await self._handle_real_turn(frame.text, direction)
            return

        await self.push_frame(frame, direction)

    async def _handle_real_turn(self, text: str, direction: FrameDirection) -> None:
        """Processes one real turn — the prospect's actual words — through
        run_turn_stream and out to speech. Shared by the TranscriptionFrame
        handler above (a transcript arriving live) and _advance_after_turn
        below (a transcript that had to be stashed because it arrived mid-
        beat — see queue_frame's docstring — replayed here the moment it's
        safe to). Exactly the same handling either way: the model should
        never be able to tell the difference from its own side."""
        logger.info(f"[{self._visitor_id}] heard: {text!r}")
        session = get_session(self._visitor_id)
        # Defensive second cancellation point — VAD-start and an STT
        # segment finalizing aren't the same frame/timing, so this isn't
        # redundant with the VADUserStartedSpeakingFrame branch; a real turn
        # starting for any reason must never race against a scheduled
        # auto-continue.
        self._cancel_pending_auto_continue()
        self._turn_in_progress = True
        self._interrupted_this_turn = False

        try:
            filler = self._pick_filler(text)
            await self._speak(filler, direction)

            try:
                result, already_spoken = await self._consume_turn_stream(run_turn_stream(text, session), direction)
            except Exception:
                result, already_spoken = None, False

            if result is None:
                # Real turn, so unlike auto-continue this must always
                # say something — either the try above raised, or
                # run_turn_stream() somehow ended without a terminal
                # event (shouldn't happen, but never leave a real
                # prospect met with silence over it).
                logger.exception(f"run_turn_stream failed for visitor {self._visitor_id}")
                result = {"reply": "Sorry, I lost my train of thought — could you say that again?"}
                already_spoken = False

            logger.info(f"[{self._visitor_id}] replying: {result!r}")

            if not already_spoken:
                # Streaming never got far enough to speak anything at all
                # this turn (the exception above, or run_turn_stream
                # itself fell all the way back to done_fallback before
                # yielding a single event) — fall back to the exact same
                # one-shot speaking this pipeline always used before
                # streaming existed.
                action = result.get("action")
                lead_in = result.get("lead_in")
                reply = result["reply"]

                if action and lead_in:
                    asyncio.create_task(self._report_reply(lead_in))
                    await self._speak(lead_in, direction)
                    asyncio.create_task(self._report_action(action))
                    asyncio.create_task(self._report_reply(reply))
                    await self._speak_reply(reply, direction)
                else:
                    if action:
                        asyncio.create_task(self._report_action(action))
                    asyncio.create_task(self._report_reply(reply))
                    await self._speak_reply(reply, direction)

            if self._hand_raised and not self._hand_ack_sent:
                # Either a raise landed right as the last sentence
                # finished (too late for _speak_reply's own per-sentence
                # check to catch), or the whole reply was one sentence to
                # begin with. Either way, this is the natural end-of-turn
                # point to hand off — _speak_reply already handles the
                # mid-reply case by breaking early and handing off itself,
                # which sets _hand_ack_sent so this doesn't double-fire.
                await self._speak_hand_raise_handoff(direction)

            await self._advance_after_turn(session, direction)
        finally:
            self._turn_in_progress = False

    async def _advance_after_turn(self, session, direction: FrameDirection) -> None:
        """Called at the end of every turn — real or auto-continued — instead
        of calling _maybe_schedule_auto_continue directly. Checks for a
        stashed dropped-interruption transcript first (see queue_frame's
        docstring): if one landed while this turn was in flight, replay it
        as the next real turn right now instead of scheduling the next
        scripted beat, so a genuine barge-in never just gets silently
        skipped over in favor of the tour continuing on schedule."""
        pending = self._pending_interruption_text
        if pending is not None:
            self._pending_interruption_text = None
            await self._handle_real_turn(pending, direction)
            return
        self._maybe_schedule_auto_continue(session, direction)

    async def _greet(self, direction: FrameDirection) -> None:
        # get_session() creates a brand-new session seeded with OPENING_GREETING
        # if one doesn't exist yet (see context/store.py) — but for Meeting
        # Mode, the frontend's pre-join screen already called start_session()
        # with the visitor's name moments earlier, which seeds a personalized
        # greeting instead. Either way, speak back whatever text actually got
        # seeded rather than the generic constant, so the personalized case
        # is heard, not silently discarded.
        session = get_session(self._visitor_id)
        greeting = session.history[0].text if session.history else OPENING_GREETING
        await self._speak(greeting, direction)
        asyncio.create_task(self._report_reply(greeting))

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

    async def _speak_reply(self, text: str, direction: FrameDirection) -> None:
        """Like _speak, but one sentence at a time — waiting for each
        sentence's real playback to finish (via _speech_finished, set/cleared
        off BotStartedSpeakingFrame/BotStoppedSpeakingFrame) before starting
        the next. This is what lets a hand-raise mid-reply interrupt at the
        sentence boundary it happened in, instead of only ever being noticed
        after the entire explanation has already been spoken."""
        for sentence in _split_sentences(text):
            if self._interrupted_this_turn:
                return
            self._speech_finished.clear()
            await self._speak(sentence, direction)
            await self._speech_finished.wait()
            if self._interrupted_this_turn:
                return
            if self._hand_raised and not self._hand_ack_sent:
                await self._speak_hand_raise_handoff(direction)
                return

    async def _consume_turn_stream(self, stream, direction: FrameDirection) -> tuple[Optional[dict], bool]:
        """Consumes a run_turn_stream()/run_walkthrough_continuation() event
        stream (see runtime.py — both share the exact same event contract)
        for one turn, speaking (and reporting) lead_in/action/reply as their
        events arrive instead of waiting for a single blocking call to
        finish. Preserves the exact same ordering guarantees the
        non-streaming path always had — lead_in is fully spoken before the
        action is reported (so the frontend's UI never changes mid-
        transition-phrase), and the action is reported before the reply
        that explains it. Generalized from a real-turn-only helper (it used
        to build `run_turn_stream(text, session)` itself) to also drive
        auto-continue's `run_walkthrough_continuation(session)` — the
        speaking/interruption logic below is identical either way, only
        which generator produces the events differs, so the caller now
        builds and passes that generator in.

        Returns (result, already_spoken). already_spoken is True whenever
        ANYTHING about this turn (lead_in, action, or any reply text) was
        already spoken/reported live during this call — the caller must NOT
        speak result's contents again in that case. It's False only when
        nothing was spoken at all (an immediate failure before any event
        arrived, or the stream fell straight to done_fallback with nothing
        having streamed) — the one case where it's safe for the caller to
        speak result from scratch, the same one-shot way this pipeline has
        always spoken a reply.

        result can be None — unlike the old version, this no longer
        manufactures a fallback apology itself, since that's the wrong
        behavior for auto-continue (better to silently skip a beat than
        speak an apology unprompted); each caller decides what None means
        for it. See the two call sites.

        A stream that fails PARTWAY THROUGH — after lead_in/action, or some
        reply text, was already spoken — is deliberately NOT retried with a
        fresh, independent LLM call the way run_turn_stream's own internal
        fallback does for a failure at the very start. A fresh call would
        produce an unrelated reply that could contradict what was just
        heard (a different or no action at all, disagreeing content) —
        worse than the turn just ending a little short. See the
        any_speech_started handling below.
        """
        pending_text = ""
        any_speech_started = False
        result: Optional[dict] = None
        reply_fully_spoken_live = False
        # Set once a hand-raise or barge-in ends this turn's speech early.
        # From then on the loop below keeps consuming run_turn_stream()
        # silently (no more _speak calls) instead of abandoning it — ending
        # the `async for` early via `return` would tear down the generator
        # before it reaches its own _finalize_turn() call (see runtime.py),
        # which is what persists the agent's reply onto session.history and
        # the transcript log. Skipping that left an interrupted turn's user
        # message with no matching agent reply in history at all — confirmed
        # via a real interrupted call, not just reasoned about — so the
        # model would have no memory of ever having replied. Draining
        # instead of abandoning keeps history correct while still cutting
        # audio off immediately.
        stopped_speaking_early = False

        async def _flush_ready_sentences(final: bool) -> bool:
            """Speaks whatever's newly complete in pending_text (all but a
            possibly-still-growing last fragment, unless final=True, in
            which case everything left over is spoken as the last piece).
            Returns True if a hand-raise OR a real barge-in interrupted
            mid-flush (mirrors _speak_reply's own early-return behavior) —
            the caller stops treating this turn as still-speaking either
            way, it just doesn't speak a handoff line for a barge-in."""
            nonlocal pending_text
            if final:
                chunks = [pending_text] if pending_text.strip() else []
                pending_text = ""
            else:
                sentences = _split_sentences(pending_text) if pending_text.strip() else []
                chunks = sentences[:-1]
                pending_text = sentences[-1] if sentences else ""
            for sentence in chunks:
                if not sentence.strip():
                    continue
                if self._interrupted_this_turn:
                    return True
                self._speech_finished.clear()
                await self._speak(sentence, direction)
                await self._speech_finished.wait()
                if self._interrupted_this_turn:
                    return True
                if self._hand_raised and not self._hand_ack_sent:
                    await self._speak_hand_raise_handoff(direction)
                    return True
            return False

        async for event in stream:
            kind = event[0]
            if stopped_speaking_early:
                # Still need `result` from the terminal event below so the
                # stream reaches its own _finalize_turn() call — just don't
                # speak or report anything more for this turn.
                if kind in ("done_streamed", "done_fallback"):
                    result = event[1]
                continue
            if kind == "lead_in":
                if self._interrupted_this_turn:
                    stopped_speaking_early = True
                    continue
                any_speech_started = True
                asyncio.create_task(self._report_reply(event[1]))
                await self._speak(event[1], direction)
            elif kind == "action":
                asyncio.create_task(self._report_action(event[1]))
            elif kind == "reply_delta":
                any_speech_started = True
                pending_text += event[1]
                if await _flush_ready_sentences(final=False):
                    stopped_speaking_early = True
            elif kind in ("done_streamed", "done_fallback"):
                result = event[1]
                if kind == "done_streamed":
                    asyncio.create_task(self._report_reply(result["reply"]))
                    if await _flush_ready_sentences(final=True):
                        stopped_speaking_early = True
                    else:
                        reply_fully_spoken_live = True

        if stopped_speaking_early or (any_speech_started and not reply_fully_spoken_live):
            logger.warning(
                f"[{self._visitor_id}] streaming turn spoke something before falling back — "
                "not re-speaking the independently-regenerated fallback reply"
            )
            return result, True

        return result, reply_fully_spoken_live

    def _cancel_pending_auto_continue(self) -> None:
        """Aborts a scheduled-but-not-yet-fired auto-continue beat (see
        _maybe_schedule_auto_continue) — called the instant real speech
        starts or a real turn begins, so a queued continuation never fires
        on top of / races against something the prospect actually said.
        Safe to call when nothing is pending."""
        if self._pending_auto_continue is not None:
            self._pending_auto_continue.cancel()
            self._pending_auto_continue = None

    def _maybe_schedule_auto_continue(self, session, direction: FrameDirection) -> None:
        """Called at the end of every real AND auto-continued turn.
        Schedules the next walkthrough beat to speak on its own after a
        short pause, unless the tour just ended or the model is waiting on
        a real answer to a genuine interruption (see
        SessionState.walkthrough_awaiting_answer and _walkthrough_note's
        interruption rule in runtime.py) — this is what makes "give me a
        walkthrough" keep going without the prospect needing to prompt
        every single beat, while still actually pausing for a real question
        instead of talking over it."""
        if session.walkthrough_step is None or session.walkthrough_awaiting_answer:
            return
        # Only one continuation is ever in flight/pending at a time — a
        # fresh schedule call (from the auto-continue turn that's about to
        # finish and chain into the next one) replacing an old reference is
        # fine, since the old task, by definition, already fired by the
        # time this runs again.
        self._pending_auto_continue = asyncio.create_task(self._auto_continue_after_pause(session, direction))

    async def _watch_auto_continue_stall(self) -> None:
        """Self-healing safety net for the auto-continue chain.

        _cancel_pending_auto_continue() (called from the VADUserStartedSpeakingFrame
        handler above) fires eagerly on ANY VAD trigger, including ones that
        never turn into a real TranscriptionFrame — background noise, a
        breath, a cough, mic bleed. That eagerness is correct: it's what
        keeps a genuine barge-in from racing against a queued beat. But it
        means a false trigger cancels the pending continuation with nothing
        left to reschedule it — every reschedule point (_maybe_schedule_auto_continue)
        only runs at the end of a turn that actually happened, and a false
        trigger produces no turn at all. Without this, that one false
        positive silently ends the tour for the rest of the call, with
        nothing to show for it until the 120s idle timeout (bot.py's
        _watch_idle) finally hangs up.

        Polls the same way _watch_idle does: cheap, infrequent, just a
        handful of attribute reads. Only reschedules when everything reads
        as genuinely idle — walkthrough active, not waiting on a real
        interruption answer, no turn running, bot not speaking, nothing
        already pending, and quiet for a full grace period (so a real
        utterance still being transcribed is never mistaken for a dead
        chain)."""
        try:
            while True:
                await asyncio.sleep(AUTO_CONTINUE_WATCHDOG_INTERVAL_SECS)
                session = get_session(self._visitor_id)
                if session.walkthrough_step is None or session.walkthrough_awaiting_answer:
                    continue
                if self._turn_in_progress or self._bot_speaking:
                    continue
                if self._pending_auto_continue is not None:
                    continue
                if self._user_speaking:
                    # VAD still thinks someone's mid-utterance — a real
                    # sentence can easily run past the grace period below,
                    # and racing ahead here is exactly what silently
                    # discarded a real interruption earlier tonight (see
                    # queue_frame's docstring). Wait for VADUserStoppedSpeakingFrame,
                    # however long that takes, before ever reconsidering.
                    continue
                if time.monotonic() - self._last_activity < AUTO_CONTINUE_STALL_GRACE_SECS:
                    continue
                logger.warning(f"[{self._visitor_id}] auto-continue chain stalled at step {session.walkthrough_step}, self-healing")
                self._maybe_schedule_auto_continue(session, FrameDirection.DOWNSTREAM)
        except asyncio.CancelledError:
            pass

    async def _auto_continue_after_pause(self, session, direction: FrameDirection) -> None:
        try:
            await asyncio.sleep(AUTO_CONTINUE_PAUSE_SECS)
        except asyncio.CancelledError:
            return
        # Re-check right before firing, not just at schedule time — real
        # speech (or a real turn starting for any other reason) between
        # scheduling and now must win. _cancel_pending_auto_continue already
        # covers the common case (it cancels this task outright); this is a
        # defensive second check for the narrow window where the task is
        # already past its cancellation point but hasn't started speaking.
        if self._turn_in_progress or self._bot_speaking:
            # Bail without firing this beat, but still clear the reference —
            # this task is done either way, and leaving a stale non-None
            # reference here would permanently convince
            # _watch_auto_continue_stall something is still pending when
            # nothing actually is, blocking it from ever self-healing.
            self._pending_auto_continue = None
            return
        self._pending_auto_continue = None
        await self.auto_continue_walkthrough(session, direction)

    async def auto_continue_walkthrough(self, session, direction: FrameDirection) -> None:
        """Speaks the next walkthrough beat on the agent's own initiative —
        the auto-continue counterpart to the TranscriptionFrame handler's
        real-turn path above, driving run_walkthrough_continuation() (see
        runtime.py) through the same _consume_turn_stream() both paths
        share. Unlike a real turn: no "heard:" log (nothing was heard), no
        opening filler phrase (there's no "prospect just spoke" moment to
        bridge from — it should just start talking), and a None result
        means silently skip this beat rather than speak an apology (see
        _consume_turn_stream's docstring). Sets _turn_in_progress the same
        way a real turn does, so the existing barge-in path (which gates on
        _bot_speaking, not on how the speech started) interrupts an
        auto-continued beat exactly the same as it would a real one — no
        new interruption logic needed for this case."""
        self._turn_in_progress = True
        self._interrupted_this_turn = False
        try:
            try:
                result, already_spoken = await self._consume_turn_stream(
                    run_walkthrough_continuation(session), direction
                )
            except Exception:
                logger.exception(f"[{self._visitor_id}] walkthrough auto-continue failed, skipping this beat")
                return

            if result is None:
                # Both the streaming and non-streaming paths inside
                # run_walkthrough_continuation() failed (already logged
                # there). Silently skip rather than speak anything wrong or
                # retry in a tight loop.
                return

            logger.info(f"[{self._visitor_id}] auto-continuing: {result!r}")

            if not already_spoken:
                action = result.get("action")
                lead_in = result.get("lead_in")
                reply = result["reply"]
                if action and lead_in:
                    asyncio.create_task(self._report_reply(lead_in))
                    await self._speak(lead_in, direction)
                    asyncio.create_task(self._report_action(action))
                    asyncio.create_task(self._report_reply(reply))
                    await self._speak_reply(reply, direction)
                else:
                    if action:
                        asyncio.create_task(self._report_action(action))
                    asyncio.create_task(self._report_reply(reply))
                    await self._speak_reply(reply, direction)

            if self._hand_raised and not self._hand_ack_sent:
                await self._speak_hand_raise_handoff(direction)

            await self._advance_after_turn(session, direction)
        finally:
            self._turn_in_progress = False

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
        # Set before speaking, not after — this is the single gate that
        # stops a raise from getting handed off twice (once mid-reply via
        # _speak_reply, once more at end-of-turn, or twice across repeated
        # polls while it's still held up).
        self._hand_ack_sent = True
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
        #
        # Unlike the old version, the backend's hand-raise state is no
        # longer a one-shot flag consumed on first read — it's the visitor's
        # own toggle (see MeetingShell's button), which stays raised until
        # they click it again. So this loop tracks transitions itself
        # (low->high is a fresh raise, high->low means they lowered it) and
        # relies on _hand_ack_sent to make sure a raise that stays up for
        # many poll ticks only ever gets handed off once.
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
                            raised = bool(data.get("raised"))
                    except Exception:
                        logger.exception(f"Failed to poll hand-raise for visitor {self._visitor_id}")
                        continue

                    if raised != self._hand_raised:
                        # Either edge (fresh raise, or the visitor lowering
                        # it) resets the ack gate — a fresh raise deserves
                        # its own handoff, and lowering it is what makes the
                        # *next* raise fresh again. Only a real transition
                        # does this; polling the same still-raised state
                        # tick after tick must not re-open the gate.
                        self._hand_ack_sent = False
                    if raised and not self._hand_raised:
                        # Counts as activity even though it's not speech — a
                        # hand-raise is a genuine engagement signal, and
                        # someone who just raised their hand shouldn't get
                        # idled out from under them before they even speak.
                        self._last_activity = time.monotonic()
                    self._hand_raised = raised

                    if self._hand_raised and not self._hand_ack_sent and not self._turn_in_progress:
                        # Genuinely idle when the raise landed — nothing else
                        # is going to trigger a check (the mid-reply case is
                        # instead caught inside _speak_reply, and the
                        # end-of-turn case right after it returns), so react
                        # here. This is the case a hand-raise is actually
                        # FOR: the prospect didn't say anything, they just
                        # raised their hand.
                        await self._speak_hand_raise_handoff(FrameDirection.DOWNSTREAM)
        except asyncio.CancelledError:
            pass

    def seconds_since_activity(self) -> float:
        """Read by bot.py's idle watcher (see run_bot) — kept here because
        this is the processor that actually observes real speech from both
        sides (BotStartedSpeakingFrame/VADUserStartedSpeakingFrame above),
        not something the watcher could track on its own."""
        return time.monotonic() - self._last_activity

    def is_bot_speaking(self) -> bool:
        """Also read by bot.py's idle watcher, to know when a farewell it
        asked for has actually finished playing before it tears down the
        call — see speak_idle_farewell."""
        return self._bot_speaking

    async def speak_idle_farewell(self) -> None:
        """Called by bot.py's idle watcher once IDLE_TIMEOUT_SECS of total
        silence has passed. Speaks a real goodbye rather than letting the
        watcher silently drop the connection — a dead cut-off would read as
        a bug, not an ended call, and would break the "real person"
        illusion this whole demo relies on."""
        farewell = (
            "Looks like you might have stepped away — I'll go ahead and hop off. "
            "Feel free to jump back in anytime!"
        )
        asyncio.create_task(self._report_reply(farewell))
        await self._speak(farewell, FrameDirection.DOWNSTREAM)

    async def cleanup(self):
        if self._hand_raise_poll_task is not None:
            self._hand_raise_poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._hand_raise_poll_task
        if self._auto_continue_watchdog_task is not None:
            self._auto_continue_watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._auto_continue_watchdog_task
        # Same reasoning as the hand-raise poll task above — a walkthrough
        # left mid-tour when the call ends shouldn't leave a dangling task
        # trying to speak into a torn-down pipeline.
        self._cancel_pending_auto_continue()
        await super().cleanup()


def _rms_level(audio_bytes: bytes) -> float:
    """0-1 loudness from raw 16-bit PCM, same normalization the frontend's
    own useAudioLevelRing.ts uses for the visitor's mic (RMS / int16 full
    scale, boosted 4x since normal speech sits well under full scale) —
    kept consistent so both sides of the speaking ring feel comparably
    responsive rather than one looking louder than the other by accident."""
    usable_len = len(audio_bytes) - (len(audio_bytes) % 2)
    if usable_len <= 0:
        return 0.0
    samples = array.array("h")
    samples.frombytes(audio_bytes[:usable_len])
    if not samples:
        return 0.0
    mean_square = sum(s * s for s in samples) / len(samples)
    rms = mean_square**0.5
    return min(1.0, (rms / 32768.0) * 4)


class TTSLevelReporter(FrameProcessor):
    """Sits right after TTS in the pipeline, before transport.output().

    The agent's synthesized speech isn't exposed to the browser as an
    inspectable MediaStreamTrack under the WebSocket transport the way the
    visitor's own mic is (confirmed by reading
    @pipecat-ai/websocket-transport's WavMediaManager.tracks() directly —
    it returns a "local" track but has no "bot" key at all), so there's
    nothing for the frontend to run a Web Audio analyser on for its side.
    This computes the same kind of loudness value server-side, from the
    actual audio bytes about to be sent, and reports it alongside the
    audio as a small RTVI server-message — genuine measured amplitude, not
    a canned animation keyed off start/stop timing.

    Purely a side channel: the original audio frame is always forwarded
    unchanged and immediately, so this can't add latency or alter what's
    actually heard — it only ever adds one small extra message frame.
    """

    _MIN_INTERVAL_SECS = 0.08  # ~12/sec — smooth enough for a CSS transition, cheap on the wire

    def __init__(self):
        super().__init__()
        self._last_sent = 0.0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TTSAudioRawFrame):
            now = time.monotonic()
            if now - self._last_sent >= self._MIN_INTERVAL_SECS:
                self._last_sent = now
                level = _rms_level(frame.audio)
                await self.push_frame(
                    OutputTransportMessageFrame(
                        message={
                            "id": str(uuid.uuid4()),
                            "label": "rtvi-ai",
                            "type": "server-message",
                            "data": {"kind": "agent-audio-level", "level": level},
                        }
                    ),
                    direction,
                )

        await self.push_frame(frame, direction)
