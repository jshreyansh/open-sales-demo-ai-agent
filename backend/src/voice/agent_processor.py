import array
import asyncio
import contextlib
import dataclasses
import random
import re
import time
import uuid
from typing import Callable, Optional

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

from ..agent.runtime import commit_prefetched_turn, run_turn_stream, run_walkthrough_continuation
from ..context.store import OPENING_GREETING, get_session
from ..data import gate_log

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

# How often _poll_hand_raise checks the REST API's mailbox for a raised
# hand. Used to be 1.0s — a raise landing right after a tick meant up to a
# full second before the system even noticed, on top of whatever a
# sentence-boundary wait added on top of that. Tightened so a raise reads
# as prompt, not laggy; still cheap enough (one small HTTP GET) not to be
# worth throttling further.
HAND_RAISE_POLL_INTERVAL_SECS = 0.3

# A typed message deserves at least as prompt a reaction as a hand-raise —
# arguably more, since unlike a raise (a pure signal) it already carries the
# actual thing the visitor wants answered.
MEETING_CHAT_POLL_INTERVAL_SECS = 0.3

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
# Two distinct pools, chosen by what the filler is actually doing (see
# _pick_filler / _is_question) rather than mixed together at random:
# THINKING_FILLERS ("Hmm —") for when the prospect asked a real question and
# the agent needs a beat to actually think before answering; FLOOR_FILLERS
# ("Um —") for when they just made a statement/comment and the agent is
# simply holding the floor for a moment before continuing, not thinking hard.
# Previously both cases drew from an overlapping pool, which read as
# unnatural (e.g. "Hmm —" before a plain acknowledgment).
THINKING_FILLERS = ["Hmm —", "Hmm, let's see —", "Hmm, good question —", "Let me think —"]
FLOOR_FILLERS = ["Um —", "Mm —", "Okay, um —", "Sure, um —"]

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
        # Which surface a stashed interruption's text actually came from —
        # "voice" (a dropped real transcript, the original/only case this
        # existed for) or "chat" (a typed Meeting Mode message that arrived
        # while a beat was mid-turn, see _handle_meeting_chat_message).
        # Read (and reset back to "voice") by _advance_after_turn alongside
        # _pending_interruption_text itself, so the eventual reply gets
        # reported with the right source — see _current_reply_source below.
        self._pending_interruption_source: str = "voice"
        # Which surface the CURRENTLY RUNNING turn's replies should be
        # reported under (see _report_reply) — "voice" for everything
        # (narration, real spoken turns, hand-raise handoffs) except a real
        # turn that specifically started from a typed chat message, which
        # sets this to "chat" for its duration (see _handle_real_turn's
        # `source` param). Every speaking path that ISN'T _handle_real_turn
        # (auto_continue_walkthrough, _speak_hand_raise_handoff, the idle
        # farewell) resets this to "voice" itself at its own start, since
        # otherwise it would just keep whatever a previous chat-sourced turn
        # last left it as.
        self._current_reply_source: str = "voice"
        self._meeting_chat_poll_task: asyncio.Task | None = None
        # Counts consecutive stash-replays chained back-to-back with no
        # normal, non-replayed turn in between (see _advance_after_turn) —
        # capped at one. Without a cap, someone saying two or three
        # different things in a row while the bot was mid-turn each got
        # a full, separate answer chained one after another, which reads
        # as the agent "queuing up" and reciting multiple unrelated replies
        # instead of engaging with what's current. Reset to 0 any time a
        # turn ends with nothing left stashed.
        self._interruption_replay_depth = 0
        # Background task generating the NEXT walkthrough beat's content
        # ahead of time, kicked off the moment the CURRENT beat's own
        # state is settled but its audio may still be playing (see
        # _consume_turn_stream's on_result hook and _start_prefetch) — this
        # is what hides DeepSeek's real ~2-4s generation latency behind
        # speech that's already happening, instead of paying it as dead
        # air between steps (confirmed live as the dominant cost there).
        # _prefetch_for_step records which walkthrough_step this was
        # generated FROM, so a mismatch at consumption time (something else
        # moved the step in between) is caught rather than silently used.
        # MUST be cancelled (see _cancel_prefetch) the instant anything
        # actually interrupts — a real barge-in, a hand-raise, or a fresh
        # real turn — so it can never finish and silently finalize
        # (advancing walkthrough_step) a beat nobody is going to hear.
        self._prefetch_task: Optional[asyncio.Task] = None
        self._prefetch_for_step: Optional[int] = None
        # The disposable session clone _drain_prefetch actually ran
        # against (see _start_prefetch) — held so _take_ready_prefetch can
        # replay its mutations onto the real session via
        # runtime.commit_prefetched_turn ONLY once this prefetch is
        # confirmed to actually be spoken. Never the real session itself:
        # run_walkthrough_continuation's persist=False mode still fully
        # mutates whatever session object it's given, so driving it against
        # the real session would commit a beat nobody may ever hear.
        self._prefetch_session_clone = None

    def _pick_filler(self, heard_text: str) -> str:
        pool = THINKING_FILLERS if _is_question(heard_text) else FLOOR_FILLERS
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
            self._pending_interruption_source = "voice"
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
                self._meeting_chat_poll_task = asyncio.create_task(self._poll_meeting_chat())
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
            # still queued up). A next-beat prefetch is the same kind of
            # "abort whatever's ahead of us" state — cancel it here too, so
            # it can never finish and silently finalize a beat that was
            # never actually delivered.
            self._cancel_pending_auto_continue()
            self._cancel_prefetch()
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

    async def _handle_real_turn(self, text: str, direction: FrameDirection, source: str = "voice") -> None:
        """Processes one real turn — the prospect's actual words — through
        run_turn_stream and out to speech. Shared by the TranscriptionFrame
        handler above (a transcript arriving live), _advance_after_turn
        below (a transcript that had to be stashed because it arrived mid-
        beat — see queue_frame's docstring — replayed here the moment it's
        safe to), and _handle_meeting_chat_message (a typed message, treated
        as a real turn's content exactly the same way). Exactly the same
        handling either way: the model should never be able to tell the
        difference from its own side.

        `source` ("voice" or "chat") only affects _report_reply's tagging
        (see _current_reply_source) — it changes nothing about how the turn
        itself runs, so a typed message gets identical interruption/
        walkthrough/qualification handling to a spoken one, just reported
        under the surface it actually came from."""
        logger.info(f"[{self._visitor_id}] heard: {text!r}")
        self._current_reply_source = source
        session = get_session(self._visitor_id)
        # Defensive second cancellation point — VAD-start and an STT
        # segment finalizing aren't the same frame/timing, so this isn't
        # redundant with the VADUserStartedSpeakingFrame branch; a real turn
        # starting for any reason must never race against a scheduled
        # auto-continue or a stale prefetch for a beat this turn might make
        # irrelevant (a detour, a skip-ahead, anything other than a plain
        # "continue").
        self._cancel_pending_auto_continue()
        self._cancel_prefetch()
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
        skipped over in favor of the tour continuing on schedule.

        Only ever chains ONE such replay in a row (_interruption_replay_depth).
        _pending_interruption_text already always holds just the latest
        overwrite, never a backlog — but a person can genuinely say two or
        three different things in the seconds it takes to work through each
        one, and chaining a full reply for every single one back-to-back is
        what read as the agent "queuing up" and answering several unrelated
        things in a row instead of engaging with what's current. Capping at
        one still guarantees the most recent thing said is never silently
        dropped; anything stacked on top of that gets a short, honest
        "still catching up" instead of another full unrelated answer."""
        pending = self._pending_interruption_text
        if pending is not None:
            self._pending_interruption_text = None
            pending_source = self._pending_interruption_source
            self._pending_interruption_source = "voice"
            if self._interruption_replay_depth >= 1:
                self._interruption_replay_depth = 0
                catching_up = "Sorry, I'm still catching up — could you say that again?"
                # Both sides of this exchange used to be invisible outside
                # the raw pipeline log — neither the superseded transcript
                # nor this recovery reply ever went through _handle_real_turn/
                # _finalize_turn (the only place transcript_turns rows and
                # history entries normally get written), since this path
                # bypasses the model entirely. Confirmed live: reviewing a
                # call afterward, this exchange was real (present in the raw
                # log) but read as a mysterious gap in the transcript DB and
                # the frontend chat UI, which both only ever show what's
                # persisted here. Persist and report the same way every
                # other real turn does.
                if session.visitor_id:
                    gate_log.append_transcript_turn(session.visitor_id, "user", pending)
                    gate_log.append_transcript_turn(session.visitor_id, "agent", catching_up)
                self._current_reply_source = pending_source
                asyncio.create_task(self._report_reply(catching_up))
                await self._speak(catching_up, direction)
                # This message is spoken directly here, never through the
                # model's own tool call — so it's the one place that has to
                # set the sticky pause itself instead of relying on the
                # model to set "walkthrough_awaiting_answer" (see runtime.py's
                # _finalize_turn). Without this, _maybe_schedule_auto_continue
                # right below would go ahead and fire the next scripted beat
                # anyway, the exact "asked me to repeat, then kept going
                # without listening" bug confirmed live.
                if session.walkthrough_step is not None:
                    session.walkthrough_awaiting_answer = True
                self._maybe_schedule_auto_continue(session, direction)
                return
            self._interruption_replay_depth += 1
            await self._handle_real_turn(pending, direction, source=pending_source)
            return
        self._interruption_replay_depth = 0
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

    async def _consume_turn_stream(
        self,
        stream,
        direction: FrameDirection,
        on_result: Optional[Callable[[], None]] = None,
        allow_abandon_before_speech: bool = False,
    ) -> tuple[Optional[dict], bool]:
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

        allow_abandon_before_speech (only ever True for auto-continue beats
        — see auto_continue_walkthrough's call site): if a fresher stash
        (see queue_frame's docstring) is ALREADY waiting the moment this
        beat is about to speak its very first word, and nothing has been
        said for this beat yet, abandon it outright — return (None, False)
        — instead of speaking stale content right before that stash gets
        replayed a moment later. Confirmed live: a beat that sat waiting on
        its LLM call for 8+ seconds (self-healed by the watchdog) finally
        resolved and spoke its content within ~10ms of a genuinely-asked
        question being replayed, reading as "it's not even listening."
        Unlike the interrupted-mid-speech case below, this is safe to
        abandon rather than drain: nothing was ever said, so there's
        nothing in session.history to keep consistent, and — critically —
        this must NEVER be enabled for a real turn's own run_turn_stream(),
        since _begin_turn() there already logged the prospect's message
        before this call even started; abandoning that reply early would
        recreate the exact "heard message with no matching reply in
        history" bug already found and fixed once. run_walkthrough_continuation()
        has no such pairing (it deliberately never calls _begin_turn() —
        there's no real prospect message behind an auto-continue beat), so
        it alone is safe to opt into this.
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
        # Whether ANYTHING has actually been spoken yet for THIS beat —
        # distinct from any_speech_started above, which flips true the
        # instant text/a lead_in is merely seen, before _speak() is
        # actually reached. Only meaningful when allow_abandon_before_speech
        # is set; unused otherwise.
        spoken_anything_yet = False
        abandoned_before_speech = False

        def _superseded_by_fresher_stash() -> bool:
            return (
                allow_abandon_before_speech
                and not spoken_anything_yet
                and self._pending_interruption_text is not None
            )

        async def _flush_ready_sentences(final: bool) -> bool:
            """Speaks whatever's newly complete in pending_text (all but a
            possibly-still-growing last fragment, unless final=True, in
            which case everything left over is spoken as the last piece).
            Returns True if a hand-raise, a real barge-in, or (auto-continue
            only) a fresher stash already waiting interrupted mid-flush
            (mirrors _speak_reply's own early-return behavior) — the caller
            stops treating this turn as still-speaking either way, it just
            doesn't speak a handoff line for a barge-in."""
            nonlocal pending_text, spoken_anything_yet, abandoned_before_speech
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
                if _superseded_by_fresher_stash():
                    abandoned_before_speech = True
                    return True
                self._speech_finished.clear()
                await self._speak(sentence, direction)
                spoken_anything_yet = True
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
                if _superseded_by_fresher_stash():
                    abandoned_before_speech = True
                    stopped_speaking_early = True
                    continue
                any_speech_started = True
                spoken_anything_yet = True
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
                # This fires here specifically because runtime.py's
                # _finalize_turn() has ALREADY run by the time this event
                # reaches us (see run_walkthrough_continuation/
                # _stream_with_claude) — session state (walkthrough_step
                # etc.) is fully settled for THIS beat, even though its
                # remaining sentences are about to be spoken over the next
                # few seconds below. That's exactly the window a caller can
                # use to prefetch the NEXT beat's own LLM call concurrently,
                # hiding its latency behind this beat's still-playing audio
                # instead of paying it as dead air afterward.
                if on_result is not None:
                    on_result()
                if kind == "done_streamed":
                    asyncio.create_task(self._report_reply(result["reply"]))
                    if await _flush_ready_sentences(final=True):
                        stopped_speaking_early = True
                    else:
                        reply_fully_spoken_live = True

        if abandoned_before_speech:
            # Nothing was ever actually spoken for this beat before a
            # fresher, real thing the prospect said landed — abandon the
            # generator outright (it's already past the loop, nothing left
            # to drain) instead of the normal finalize path, so nothing
            # gets silently committed (walkthrough_step advance, a history
            # entry) for content the prospect never actually heard. The
            # caller treats a None result exactly like any other skipped
            # auto-continue beat.
            await stream.aclose()
            return None, False

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

    def _cancel_prefetch(self) -> None:
        """Discards an in-flight next-beat prefetch outright (see
        _start_prefetch) — called from every real-interruption path (VAD
        barge-in, hand-raise, a fresh real turn starting), same reason
        _cancel_pending_auto_continue exists: a prefetch racing ahead of
        something that actually changes the conversation must never be
        allowed to finish and silently finalize (advancing
        walkthrough_step) a beat nobody is going to hear. Cancelling here
        interrupts the prefetch's own generation call before it reaches
        that point in the overwhelmingly common case (the ~2-4s DeepSeek
        wait is most of the task's lifetime); _take_ready_prefetch's own
        step-match check is the backstop for the rare remaining race.
        Safe to call when nothing is prefetching."""
        if self._prefetch_task is not None:
            self._prefetch_task.cancel()
            self._prefetch_task = None
        self._prefetch_for_step = None
        self._prefetch_session_clone = None

    def _start_prefetch(self, session) -> None:
        """Kicks off the NEXT walkthrough beat's LLM generation in the
        background right when the CURRENT beat's own state is already
        settled (see _consume_turn_stream's on_result hook, and
        auto_continue_walkthrough's use of it) but its audio may still be
        playing for a few more seconds — this is what actually hides
        DeepSeek's real generation latency behind speech that's already
        happening, instead of it being paid as dead air between steps
        afterward (measured live: ~3-4s of silence per step, almost
        entirely LLM generation time, not TTS or the 0.1s scheduling
        pause). Only ever one prefetch in flight; a stale leftover is
        replaced, not stacked. No-op outside an active, unpaused
        walkthrough — nothing to get ahead of."""
        if session.walkthrough_step is None or session.walkthrough_awaiting_answer:
            return
        if self._prefetch_task is not None:
            return
        self._prefetch_for_step = session.walkthrough_step
        # A DISPOSABLE clone, never the real session — run_walkthrough_
        # continuation(persist=False) still fully mutates whatever session
        # object it's given (walkthrough_step, history, etc.), just without
        # the two gate_log writes. Driving that against the real session
        # would commit a beat nobody may ever hear the instant generation
        # completes, seconds before (or in the discarded case, instead of)
        # it's ever actually spoken — confirmed live as a real bug: 2 of 18
        # finalize calls on one real call were never spoken yet had already
        # permanently written themselves into session.history and the
        # transcript DB, one of them a hallucinated step reversion that
        # then poisoned every later turn's context. `history=list(...)`
        # gives the clone its own list object so appends to it never touch
        # the real session's history.
        session_clone = dataclasses.replace(session, history=list(session.history))
        self._prefetch_session_clone = session_clone
        self._prefetch_task = asyncio.create_task(self._drain_prefetch(session_clone))

    async def _drain_prefetch(self, session_clone) -> Optional[dict]:
        """Runs run_walkthrough_continuation() to completion for a
        prefetch, silently — no speaking, no reporting, just capturing the
        final result. Iterating the generator to its terminal event is
        what triggers its own _finalize_turn(persist=False) (see
        runtime.py) — against `session_clone`, a disposable copy (see
        _start_prefetch), not the real session, and with the durable
        gate_log writes skipped. Nothing is committed anywhere for real
        until _take_ready_prefetch confirms this prefetch is actually going
        to be spoken and calls runtime.commit_prefetched_turn. Cancelling
        the wrapping task (see _cancel_prefetch) mid-await stops this
        before that point in the normal case, same as any other cancelled
        asyncio task — and even when it isn't cancelled in time, completing
        against the clone means there's nothing to undo either way."""
        result = None
        async for event in run_walkthrough_continuation(session_clone, persist=False):
            if event[0] in ("done_streamed", "done_fallback"):
                result = event[1]
        return result

    async def _take_ready_prefetch(self, session) -> Optional[dict]:
        """Returns an in-flight prefetch's result if one exists and still
        matches where we actually are, clearing it either way so it's
        never reused or double-consumed. Falls back to None (the caller
        drives a fresh run_walkthrough_continuation() call itself, exactly
        like before prefetching existed) on any step mismatch, failure, or
        cancellation — always safe, it just loses the speed win for this
        one beat rather than risking stale content. On success, replays the
        clone's mutations (and the gate_log writes it skipped) onto the
        REAL session via runtime.commit_prefetched_turn — this is the one
        and only place a prefetch's side effects ever become real, and it
        only happens here because this beat is actually about to be spoken."""
        task = self._prefetch_task
        for_step = self._prefetch_for_step
        clone = self._prefetch_session_clone
        self._prefetch_task = None
        self._prefetch_for_step = None
        self._prefetch_session_clone = None
        if task is None:
            return None
        if for_step != session.walkthrough_step:
            # Something else moved walkthrough_step since this was kicked
            # off (a real turn, a skip-ahead, a restart) — this prefetch is
            # for a step we're not actually continuing from anymore. Cancel
            # it outright rather than let it finish and silently finalize a
            # beat nobody asked for.
            task.cancel()
            return None
        try:
            result = await task
        except (asyncio.CancelledError, Exception):
            logger.exception(f"[{self._visitor_id}] prefetched walkthrough beat failed, generating fresh")
            return None
        if result is None:
            # Both the streaming and non-streaming paths inside the
            # prefetch's own run_walkthrough_continuation() failed (already
            # logged there) — nothing to commit.
            return None
        commit_prefetched_turn(session, clone, result)
        return result

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
        #
        # _user_speaking matters here specifically: VAD only fires on the
        # EDGE of speech (VADUserStartedSpeakingFrame), so if the user was
        # already mid-utterance when this timer was scheduled and is STILL
        # talking now, there's no new VAD-start event left to trigger
        # _cancel_pending_auto_continue or broadcast_interruption — without
        # this check this beat would start speaking straight over them with
        # nothing to stop it. _watch_auto_continue_stall already reschedules
        # once things go idle, so bailing here is safe, not a dead end.
        if self._turn_in_progress or self._bot_speaking or self._user_speaking:
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
        new interruption logic needed for this case.

        Prefers an already-in-flight prefetch (see _take_ready_prefetch)
        over driving run_walkthrough_continuation() itself — same content
        either way, just without paying its ~2-4s LLM latency as dead air
        first. Either way, the FOLLOWING beat's own prefetch gets kicked
        off as early as possible relative to THIS beat's speaking, via
        _consume_turn_stream's on_result hook when generating fresh, or
        directly here when a ready prefetch was used instead (that path
        never drives _consume_turn_stream at all, so the hook never
        fires)."""
        self._turn_in_progress = True
        self._interrupted_this_turn = False
        # Auto-continue beats are always narration, never a reply to
        # anything typed — reset in case a previous real turn left this set
        # to "chat" (see _current_reply_source).
        self._current_reply_source = "voice"
        try:
            prefetched = await self._take_ready_prefetch(session)
            try:
                if prefetched is not None:
                    result, already_spoken = prefetched, False
                    self._start_prefetch(session)
                else:
                    result, already_spoken = await self._consume_turn_stream(
                        run_walkthrough_continuation(session),
                        direction,
                        on_result=lambda: self._start_prefetch(session),
                        allow_abandon_before_speech=True,
                    )
            except Exception:
                logger.exception(f"[{self._visitor_id}] walkthrough auto-continue failed, skipping this beat")
                return

            if result is None:
                if self._pending_interruption_text is not None:
                    # _consume_turn_stream abandoned this beat before
                    # speaking anything because a fresher stash was already
                    # waiting (see allow_abandon_before_speech) — replay it
                    # right now via _advance_after_turn's own stash-replay
                    # logic instead of just returning, which would leave it
                    # sitting untouched until the watchdog eventually
                    # reschedules this same beat (itself just abandoning
                    # again in an unnecessary loop, seconds later, instead
                    # of answering what was actually asked).
                    await self._advance_after_turn(session, direction)
                    return
                # Both the streaming and non-streaming paths inside
                # run_walkthrough_continuation() failed (already logged
                # there). Silently skip rather than speak anything wrong or
                # retry in a tight loop.
                return

            logger.info(f"[{self._visitor_id}] auto-continuing: {result!r}")

            if not already_spoken and self._pending_interruption_text is not None:
                # Neither the prefetched-result branch above nor a
                # done_fallback result (already_spoken is only ever True for
                # a streamed result _consume_turn_stream itself spoke) ever
                # passes through _consume_turn_stream's own
                # allow_abandon_before_speech check — this is the same
                # "don't speak stale content right before a fresher stash
                # replays" guard for those two paths. Leave the stash itself
                # untouched; _advance_after_turn below replays it exactly
                # like any other skipped beat.
                logger.info(
                    f"[{self._visitor_id}] a fresher stash is already waiting — skipping this "
                    "auto-continue beat instead of speaking it"
                )
            elif not already_spoken:
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
                    json={"visitorId": self._visitor_id, "reply": reply, "source": self._current_reply_source},
                    timeout=aiohttp.ClientTimeout(total=3),
                )
        except Exception:
            logger.exception(f"Failed to report voice reply for visitor {self._visitor_id}")

    async def _speak_hand_raise_handoff(self, direction: FrameDirection) -> None:
        # A hand-raise carries no typed content of its own, regardless of
        # whether it interrupted a chat-sourced turn — always report as
        # "voice" (see _current_reply_source).
        self._current_reply_source = "voice"
        # Set before speaking, not after — this is the single gate that
        # stops a raise from getting handed off twice (once mid-reply via
        # _speak_reply, once more at end-of-turn, or twice across repeated
        # polls while it's still held up).
        self._hand_ack_sent = True
        # A hand-raise IS a real interruption — treated exactly like a real
        # VAD barge-in (see VADUserStartedSpeakingFrame above), not a
        # special case of its own: mark the session interrupted the same
        # way, cancel anything already queued up ahead of it (a scheduled
        # auto-continue tick, a next-beat prefetch), and — since this
        # message is spoken directly here and never goes through the
        # model's own tool call — set the sticky walkthrough pause
        # ourselves the same way the "still catching up" recovery path
        # does. Without this, the very next auto-continue tick had nothing
        # telling it to hold off and would resume the tour right through
        # this handoff — confirmed live at ~6ms after the handoff finished,
        # giving no real window to actually unmute and ask anything.
        # Cleared the normal way once the model sets "resume_walkthrough"
        # after the prospect's real question gets answered and they give an
        # actual go-ahead to continue.
        session = get_session(self._visitor_id)
        session.was_interrupted = True
        self._cancel_pending_auto_continue()
        self._cancel_prefetch()
        if session.walkthrough_step is not None:
            session.walkthrough_awaiting_answer = True
        handoff = "Yes, go ahead — what's your question?"
        # Persisted directly, same reason and same pattern as the "still
        # catching up" recovery line (see _advance_after_turn) — this is
        # spoken by code, never through a real turn/_finalize_turn, so
        # without this it's genuinely spoken but invisible in both the
        # transcript DB and the frontend chat UI. Confirmed live: had to
        # read the raw pipeline log to see hand-raise activity a transcript
        # pull didn't show at all.
        if session.visitor_id:
            gate_log.append_transcript_turn(session.visitor_id, "agent", handoff)
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
                    await asyncio.sleep(HAND_RAISE_POLL_INTERVAL_SECS)
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

                    fresh_raise = raised and not self._hand_raised
                    if raised != self._hand_raised:
                        # Either edge (fresh raise, or the visitor lowering
                        # it) resets the ack gate — a fresh raise deserves
                        # its own handoff, and lowering it is what makes the
                        # *next* raise fresh again. Only a real transition
                        # does this; polling the same still-raised state
                        # tick after tick must not re-open the gate.
                        self._hand_ack_sent = False
                    if fresh_raise:
                        # Counts as activity even though it's not speech — a
                        # hand-raise is a genuine engagement signal, and
                        # someone who just raised their hand shouldn't get
                        # idled out from under them before they even speak.
                        self._last_activity = time.monotonic()
                    self._hand_raised = raised

                    if fresh_raise and self._bot_speaking:
                        # A raised hand means "stop right now," not "finish
                        # your sentence first" — cut audio the exact same way
                        # a real VAD barge-in does (see
                        # VADUserStartedSpeakingFrame above) instead of
                        # relying on _speak_reply's own sentence-boundary
                        # check, which could otherwise let a long sentence
                        # (or a whole multi-sentence reply, mid-stream) run
                        # all the way out before reacting.
                        self._interrupted_this_turn = True
                        await self.broadcast_interruption()

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

    async def _poll_meeting_chat(self) -> None:
        """Same cross-process reasoning as _poll_hand_raise, opposite
        direction: Meeting Mode's chat panel posts typed text to the REST
        process (:8787), and this process (:7860, the one actually running
        the live call) polls it, since the two share no memory. Unlike
        hand-raise's boolean mailbox, this one already carries a complete,
        final piece of content — no "wait for the actual question" step, it
        gets handled the instant it's seen."""
        try:
            async with aiohttp.ClientSession() as http:
                while True:
                    await asyncio.sleep(MEETING_CHAT_POLL_INTERVAL_SECS)
                    try:
                        async with http.get(
                            f"{REST_API_URL}/internal/meeting-chat/{self._visitor_id}",
                            timeout=aiohttp.ClientTimeout(total=3),
                        ) as resp:
                            data = await resp.json()
                            message = data.get("message") or ""
                    except Exception:
                        logger.exception(f"Failed to poll meeting chat for visitor {self._visitor_id}")
                        continue
                    if message:
                        await self._handle_meeting_chat_message(message, FrameDirection.DOWNSTREAM)
        except asyncio.CancelledError:
            pass

    async def _handle_meeting_chat_message(self, text: str, direction: FrameDirection) -> None:
        """Routes a typed Meeting Mode message into the exact same handling
        a spoken interruption already gets — deliberately not a separate
        mechanism, since every piece of "was I speaking, do I need to cut
        audio, do I need to cancel the next scripted beat" logic a typed
        message needs already exists for voice. The one difference from a
        real VAD barge-in: there's no waiting for STT to catch up, since the
        full text is already in hand the moment this runs.

        Counts as activity (see _last_activity) even though it's not
        speech — someone actively typing instead of talking shouldn't get
        idled out from under them."""
        self._last_activity = time.monotonic()
        if self._turn_in_progress:
            # A beat is currently being generated and/or spoken. If it's
            # actively speaking, cut the audio right now — same as a real
            # mic barge-in (see VADUserStartedSpeakingFrame above) or a
            # hand-raise landing mid-speech (see _poll_hand_raise) — rather
            # than waiting for the current sentence to finish. Either way,
            # stash the text itself rather than calling _handle_real_turn
            # again here: a second concurrent call while _turn_in_progress
            # is already true would corrupt session.history ordering. The
            # in-flight turn's own _advance_after_turn (its `finally` always
            # runs, interrupted or not) picks this up and replays it the
            # instant it's actually safe to, via the same stash-and-replay
            # path a dropped real transcript already uses.
            if self._bot_speaking:
                get_session(self._visitor_id).was_interrupted = True
                self._interrupted_this_turn = True
                await self.broadcast_interruption()
            self._cancel_pending_auto_continue()
            self._cancel_prefetch()
            self._pending_interruption_text = text
            self._pending_interruption_source = "chat"
            return
        # Genuinely idle — nothing else is going to pick this up, so handle
        # it directly, exactly like a transcript arriving while idle would.
        self._cancel_pending_auto_continue()
        self._cancel_prefetch()
        await self._handle_real_turn(text, direction, source="chat")

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
        self._current_reply_source = "voice"
        asyncio.create_task(self._report_reply(farewell))
        await self._speak(farewell, FrameDirection.DOWNSTREAM)

    async def cleanup(self):
        if self._hand_raise_poll_task is not None:
            self._hand_raise_poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._hand_raise_poll_task
        if self._meeting_chat_poll_task is not None:
            self._meeting_chat_poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._meeting_chat_poll_task
        if self._auto_continue_watchdog_task is not None:
            self._auto_continue_watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._auto_continue_watchdog_task
        # Same reasoning as the hand-raise poll task above — a walkthrough
        # left mid-tour when the call ends shouldn't leave a dangling task
        # trying to speak into a torn-down pipeline.
        self._cancel_pending_auto_continue()
        self._cancel_prefetch()
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
