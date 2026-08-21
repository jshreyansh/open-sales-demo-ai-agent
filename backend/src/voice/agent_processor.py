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

from pipecat.audio.turn.base_turn_analyzer import EndOfTurnState
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InputAudioRawFrame,
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

from ..agent.runtime import (
    CUTOFF_MARKER,
    NOTHING_SPOKEN_MARKER,
    amend_last_agent_turn,
    commit_prefetched_turn,
    run_turn_stream,
    run_walkthrough_continuation,
)
from ..context.store import OPENING_GREETING, HistoryEntry, get_session
from ..data import gate_log
from .call_recorder import CallRecorder, recording_enabled
from .turn_telemetry import TurnTelemetry

# Short "breathing room" between one walkthrough beat finishing and the next
# starting on its own — long enough that an interruption landing right after
# the bot stops speaking still lands cleanly (see AgentRuntimeProcessor's
# VADUserStartedSpeakingFrame handling, which cancels a pending auto-continue
# the instant real speech starts), short enough that it still reads as one
# continuous presenter talking, not "waiting for a response" silence.
AUTO_CONTINUE_PAUSE_SECS = 0.1

# How many walkthrough beats may play back-to-back before the floor goes back
# to the prospect. Session 7d0018d3 ran EIGHT consecutive beats (02:08:39 ->
# 02:10:05) immediately after the prospect said, in as many words, that a good
# salesperson stays quiet and asks which direction you want to go. He then went
# silent and the idle timeout hung up on him. A tour that never checks in isn't
# a demo, it's a broadcast.
MAX_CONSECUTIVE_AUTO_BEATS = 2

# ...but the budget GROWS each time the prospect answers "keep going".
#
# Session 5e1732cb: she asked six times in five minutes, he answered "continue"
# five of them, and she asked again anyway. His words: "Why are you stopping
# with every step? Should I keep reminding you that yeah, go ahead?" A fixed
# cap of 2 is right for an agent narrating unprompted; it is wrong for a tour
# the prospect explicitly asked to run, and asking someone the same question
# six times is its own kind of not listening.
#
# So each bare confirmation doubles the run: 2 beats, then 4, 8, 16. Someone
# who wants it to flow gets it to flow; someone who wants to steer still gets
# asked early. Reset on anything substantive, since that is evidence they do
# want the floor after all.
AUTO_BEAT_BUDGET_CAP = 16

_CONTINUATION_WORDS = re.compile(
    r"\b(continue|carry\s*on|keep\s*going|go\s*on|go\s*ahead|proceed|"
    r"move\s*on|listening)\b",
    re.I,
)
# Any of these means they want something OTHER than the next beat, however
# politely phrased. Checked BEFORE the continuation words, because "actually
# no, continue somewhere else" contains both.
_REDIRECT_MARKERS = re.compile(
    r"\b(instead|actually|but|wait|stop|hold\s*on|drop|skip|back|why|what|"
    r"how|when|where|who|show|open|explain|tell\s*me|go\s*to|jump|change|"
    r"rather|first|before)\b",
    re.I,
)
# Above this it isn't a nod, it's a thought — and a thought deserves an answer
# rather than being counted as permission to keep talking.
_CONTINUATION_MAX_WORDS = 12


def _is_bare_continuation(text: str) -> bool:
    """True when the prospect said "keep going" and essentially nothing else.

    Conservative in the direction that matters: a false negative just means we
    ask again sooner, while a false positive means treating a real question as
    permission to talk over it. Keys off the continuation verb appearing in a
    SHORT utterance with no question and no redirect, rather than trying to
    enumerate the words that may precede it — an earlier prefix-whitelist
    version missed "you can continue" outright.
    """
    t = (text or "").strip()
    if not t or "?" in t:
        return False
    if len(t.split()) > _CONTINUATION_MAX_WORDS:
        return False
    if _REDIRECT_MARKERS.search(t):
        return False
    return bool(_CONTINUATION_WORDS.search(t))

# Upper bound on how long _auto_continue_after_pause will wait for the
# CURRENT beat's own speech to genuinely finish (via _speech_finished)
# before it even starts the AUTO_CONTINUE_PAUSE_SECS countdown — see that
# method's docstring for why this wait exists. Generous on purpose: a real
# walkthrough sentence can legitimately run long, and the only cost of
# waiting a little too long here is falling back to the exact bail-and-let-
# the-watchdog-catch-it behavior this file already had before, not a new
# failure mode.
AUTO_CONTINUE_SPEECH_WAIT_TIMEOUT_SECS = 15.0

# Safety-net poll interval for _watch_auto_continue_stall (see that method's
# docstring) — cheap (a few attribute reads), so this doesn't need to be
# tight; it only affects how quickly a dead auto-continue chain gets
# noticed and revived, not anything on the live speaking path. Tightened
# from 2.0 (confirmed live: a chain that fell through to this watchdog paid
# up to AUTO_CONTINUE_WATCHDOG_INTERVAL_SECS + AUTO_CONTINUE_STALL_GRACE_SECS
# of pure dead air, repeatedly, across a multi-beat step — reading as the
# agent going silent mid-thought, not a rare fallback).
AUTO_CONTINUE_WATCHDOG_INTERVAL_SECS = 0.75
# How long things must have been quiet (no VAD/turn activity) before the
# watchdog will self-heal a stalled chain — long enough that a real
# in-progress utterance (VAD fired, transcript still pending) isn't mistaken
# for a dead chain. The _user_speaking check right above this one in
# _watch_auto_continue_stall is what actually guards that case (it waits
# indefinitely, not just this long) — this grace period is a secondary
# buffer on top of that, so it's safe to keep tight too.
AUTO_CONTINUE_STALL_GRACE_SECS = 0.75

# How often _poll_hand_raise checks the REST API's mailbox for a raised
# hand. Used to be 1.0s — a raise landing right after a tick meant up to a
# full second before the system even noticed, on top of whatever a
# sentence-boundary wait added on top of that. Tightened so a raise reads
# as prompt, not laggy; still cheap enough (one small HTTP GET) not to be
# worth throttling further.
HAND_RAISE_POLL_INTERVAL_SECS = 0.3

# Pause is polled harder than hand-raise. A raised hand is a request that can
# wait a beat; pause is someone wanting the room to go quiet NOW, and 300ms of
# continued talking after the click is enough to make the button feel broken.
PAUSE_POLL_INTERVAL_SECS = 0.12

# How long after the visitor presses play to wait before saying anything.
#
# Pressing play usually means they are about to speak — they paused to think
# or to talk to someone in the room, and now they're back. Talking over them
# in that first moment is the exact rudeness the pause button exists to fix.
# So she waits, and if they take the floor first she simply doesn't say the
# re-entry line at all.
RESUME_GRACE_SECS = 1.2

# A typed message deserves at least as prompt a reaction as a hand-raise —
# arguably more, since unlike a raise (a pure signal) it already carries the
# actual thing the visitor wants answered.
MEETING_CHAT_POLL_INTERVAL_SECS = 0.3

# Safety-net poll interval for _watch_pending_fragment_stall (see that
# method's docstring) — a held-back fragment isn't spoken over the top of
# anything if it sits a beat longer than it needs to, so this can be a
# little tighter than the auto-continue watchdog without any downside.
# Tightened 1.0 -> 0.25 when the consolidation window landed. This loop is
# now the thing that decides WHEN a reply happens, not just a stall safety
# net, so its period is dead time added to every single answer: at 1.0s a
# settled turn waited an extra 0-1s at random, which reads as her being
# slow and inconsistent. The body is a handful of attribute reads.
PENDING_FRAGMENT_WATCHDOG_INTERVAL_SECS = 0.25
# How long a pending fragment sits genuinely untouched (bot not speaking, no
# turn running, VAD not mid-utterance) before the watchdog gives up waiting
# for Smart Turn to ever call it COMPLETE and just answers what's been said
# so far. Comfortably above Silero VAD's own stop_secs (1.0) and Smart
# Turn's own internal silence safety net (3s, see SmartTurnParams.stop_secs)
# so it only ever kicks in as a true last resort, not a competing timer.
PENDING_FRAGMENT_STALL_GRACE_SECS = 4.0

# How long a fragment may sit held in silence before the agent audibly
# acknowledges it's still listening. Measured on a real demo: 8 of 20 turns
# were held, 3 of them for the full stall grace above — up to 5.2 seconds
# during which NOTHING was spoken (the filler lives inside _handle_real_turn,
# which doesn't run until the fragment is released). Five seconds of dead air
# after a person finishes a sentence reads as "it isn't listening," and in
# that session it made the prospect repeat himself, which then tripped the
# "still catching up" recovery. Deliberately shorter than the stall grace so
# it lands DURING the hold rather than replacing it.
# Raised 1.5 -> 2.6 as part of cutting the filler rate. At 1.5s this fired on
# ordinary mid-thought pauses, on top of the per-turn filler, which is how a
# real call ended up 32% filler.
#
# Superseded by BACKCHANNEL_MIN_FLOOR_HOLD_SECS below: raising the threshold
# was still the wrong axis, because the timer it was measured against reset on
# every fragment. The threshold was never the problem; what it was measured
# FROM was.
#
# Measured against how long the prospect has held the floor for THIS TURN, not
# how long since their last fragment landed. That distinction is the whole bug:
# _last_fragment_activity resets on every fragment, so a 20-second thought
# delivered in seven fragments never accumulated 20 seconds of hold — it
# accumulated seven separate 2.8-second holds, and each one earned its own nod.
# Session 7d0018d3 got "Right." / "Mm." / "Mm-hm." / "Sure." in 21 seconds
# inside a single thought that way.
#
# One nod per turn is the cap; this is what makes the nod EARNED rather than
# merely periodic.
BACKCHANNEL_MIN_FLOOR_HOLD_SECS = 3.5

# Don't nod immediately before answering. A nod that lands ~100ms ahead of the
# real reply isn't listening behaviour, it's a stammer — and it is what makes
# the agent sound like it's buffering rather than thinking. If the settle
# window is closer than this, stay quiet and let the answer be the answer.
BACKCHANNEL_MIN_LEAD_SECS = 1.2

# Spoken once per held fragment while waiting — the conversational equivalent
# of a nod. Short on purpose: this must not read as the agent taking the
# floor, only as evidence it's still there. Kept separate from THINKING_FILLERS
# / FLOOR_FILLERS because those bridge to an answer that's already coming,
# whereas these bridge to "keep going, I'm with you."
BACKCHANNELS = ["Mm-hm.", "Right.", "Mm.", "Sure."]

# Spoken when the walkthrough hits MAX_CONSECUTIVE_AUTO_BEATS. Each is a real
# question handing back a real choice — "carry on, or go somewhere else" —
# rather than the empty "does that make sense?" that only invites "yes".
FLOOR_RETURN_PROMPTS = [
    "Want me to keep going, or is there something you'd rather jump to?",
    "I can carry on from here — or is there somewhere more useful to go?",
    "Should I keep moving through this, or would you rather steer for a bit?",
]

# How long to wait, after a barge-in cut the agent off, for the transcript
# that would prove the barge-in was real. If nothing arrives in this window
# and the room is quiet, it wasn't speech that interrupted — it was a cough,
# a door, a keyboard, mic bleed from the shared screen's own audio — and the
# agent should pick up where it was cut off instead of silently abandoning
# the rest of its answer.
#
# This is LiveKit's `resume_false_interruption`, which ships enabled by
# default for exactly this reason: VAD fires, no transcript materializes,
# the framework waits out a timeout and resumes. Without it a 120ms noise
# spike (our Silero start_secs) permanently destroys the remainder of
# whatever was being explained, and the tour appears to skip ahead.
#
# 1.6s: comfortably longer than Groq Whisper's observed finalization lag on
# a short segment (~0.4-0.9s), so a REAL barge-in's transcript essentially
# always beats it and this never fires on genuine speech.
# Measured from the moment VAD says the visitor STOPPED, not from when the
# interruption began. Timing it from the start (as this first shipped) is
# unfixable by tuning: a transcript cannot exist until the sentence is
# finished, and only then does VAD wait out stop_secs=1.0 and Whisper
# transcribe. For anything longer than one word that total always exceeded
# the window, so the timer beat the transcript on genuine speech and the
# agent resumed on top of a real question. Confirmed live (visitor
# 5b7b77ff, turns 2-8): three replies to one question.
#
# Now also the wait for a LONG (>= MIN_REAL_INTERRUPTION_SECS) VAD event with
# no transcript, not just short ones -- see the real-barge-in branch below.
# The honest tradeoff: a genuinely noisy, wordless interruption that used to
# be abandoned instantly (and permanently) now takes up to this many seconds
# to recover instead. That is a real, deliberate cost, accepted because the
# alternative -- what shipped before this -- was worse: 35 of 40 measured
# no-transcript VAD events in one call were long enough to hit the old
# "certain, instant, permanent" path, with no way back at all. A few seconds
# of delayed recovery beats a response that's gone for good.
FALSE_INTERRUPTION_GRACE_AFTER_SILENCE_SECS = 2.5

# How much continuous VAD-active speech counts as a real barge-in rather
# than a noise blip. Below this, nothing a person could have meant fits, so
# the reply is worth resuming; at or above it, assume they said something
# real and NEVER resume — even if the transcript is late or never lands.
# This is LiveKit's `min_interruption_duration`, and it is the signal that
# actually separates the two cases. A cough or a door is ~0.2-0.4s; the
# shortest real word people barge in with ("wait", "stop") still clears 0.6.
MIN_REAL_INTERRUPTION_SECS = 0.6


# A passive acknowledgement: they are listening and not asking for anything.
# Crucially this is NEITHER permission to continue NOR a bid for the floor, so
# it must leave the beat budget exactly where it is.
#
# Session 5e1732cb-with-fix showed why: the budget grew 2 -> 4 twice, and both
# times the very next "Okay." knocked it straight back to 2, so the cap fired
# at 2/2 six times anyway. Treating a nod as "the prospect took control" is
# what made the growth useless.
_ACKNOWLEDGEMENTS = re.compile(
    r"^(?:\W*(?:okay|ok|yeah|yep|yup|yes|sure|right|got\s*it|mm+\W*hm+|"
    r"uh\W*huh|fine|cool|nice|great|good|thanks|thank\s*you|no|nope|nah|"
    r"alright|understood|makes\s*sense)\W*)+$",
    re.I,
)


def _is_acknowledgement(text: str) -> bool:
    """True for "Okay.", "Got it.", "Yeah sure." and nothing more.

    Deliberately anchored end-to-end: the whole utterance must be nothing but
    acknowledgement tokens. "Okay, but show me MLR" is a redirect and has to
    fall through to the reset branch."""
    t = (text or "").strip()
    if not t or "?" in t:
        return False
    return bool(_ACKNOWLEDGEMENTS.match(t))


# A signal that the prospect is not done with the CURRENT step and the tour
# must not advance past their position — "wait," "go back," "show me that
# again." Deliberately narrow and word-based, not a broad NLU pass: this is
# a state-transition gate (should auto-advance fire, yes/no), not a
# conversational understanding problem, and the two need different rigor.
# The model itself stays fully free to understand and respond to whatever
# the prospect actually says; this only ever decides one boolean.
#
# Session be5a8774: the tour advanced from MagicReel into MagicAvatar while
# the prospect was still asking about MagicReel's own final render screen,
# and needed three corrective turns before the agent caught up. The RESET
# path already narrows the beat budget on a substantive reply (see
# _is_permission_to_continue's caller), but that alone doesn't stop the
# very next scheduled beat from firing — this does, directly.
_HOLD_SIGNAL = re.compile(
    r"\b(?:wait|hold\s*on|hold\s*up|go\s*back|show\s*(?:me|us)?\s*(?:that|this|it)"
    r"\s*again|one\s*sec(?:ond)?|slow\s*down|not\s*yet|still\s*(?:looking|reading|"
    r"thinking|processing)|i\s*(?:want|need)\s*to\s*(?:understand|see|look\s*at)\s*"
    r"this|didn'?t\s*(?:show|see)\s*(?:me|us)?)\b",
    re.I,
)


def _is_hold_signal(text: str) -> bool:
    """True when the prospect is asking to stay on the current step rather
    than move forward. Checked before scheduling the NEXT auto-continue
    beat — see _maybe_schedule_auto_continue. A question mark doesn't
    disqualify this one (unlike the continue/ack classifiers): "wait, can
    you show me that again?" is still a hold, not a redirect worth
    resetting the whole budget over."""
    return bool(_HOLD_SIGNAL.search((text or "").strip()))


# A bare affirmative. On its own this means nothing in particular — but
# directly after "want me to keep going?" it is unambiguous permission.
_BARE_AFFIRMATIVE = re.compile(
    r"^\W*(yes|yeah|yep|yup|ya|sure|ok|okay|alright|please|go|absolutely|"
    r"definitely|of\s*course|sounds\s*good|fine)\W*$",
    re.I,
)


def _is_permission_to_continue(text: str, agent_just_asked: bool) -> bool:
    """Did the prospect just grant permission to carry on?

    Context-dependent by design. Session 0aa0aaeb is the whole argument: the
    agent asked "want me to keep going?" TEN times and the answer was "yes"
    every single time, but a bare "yes" isn't in the continuation vocabulary,
    so it counted as a mere nod and the budget never grew past 2.

    Globally treating "yes" as continue would be worse — "yes" answering
    "is your team producing a lot of content?" is data, not a green light.
    So the same word means different things depending on what was just asked,
    which is how it works between people too.
    """
    if _is_bare_continuation(text):
        return True
    return agent_just_asked and bool(_BARE_AFFIRMATIVE.match((text or "").strip()))


# How long the room must stay genuinely quiet before anything the prospect
# said gets answered.
#
# This is what turns N replies into ONE. Silero's stop_secs is 1.0, so VAD
# calls someone "not speaking" a single second after they stop making noise —
# far shorter than a normal mid-thought pause. The replay path fired on
# exactly that boolean, which produced the machine-gun pattern reported live:
# say something, pause, she answers, you carry on, she stashes it, answers
# again — five fragments, five separate answers, none of them aware of the
# others.
#
# A person listening to a colleague doesn't do that. They let the whole
# thought land, holding each piece, and reply once to all of it. This window
# is that behaviour: every fragment keeps accumulating (see queue_frame)
# and nothing is answered until the prospect has actually stopped for real.
#
# 1.8s is deliberately longer than a breath and shorter than a turn handover
# feels broken. It sits on TOP of stop_secs, so the true silence before a
# reply is ~2.8s from the last sound — close to what Gemini Live feels like,
# and the reason it can hold a long rambling input without cutting in.
# The consolidation window ADAPTS to how the person is talking, because one
# fixed number can't serve both cases. Short and it chops up a rambler; long
# and every quick "what does it cost?" sits in dead air.
#
# So: start impatient, grow patient as evidence arrives. Someone who has
# already paused-and-continued twice is telling you they're mid-thought, and
# the window stretches to match. Someone who says one sentence and stops gets
# answered promptly.
#
#   1 fragment  -> 1.5s   (a one-liner; answer briskly)
#   2 fragments -> 1.95s
#   3 fragments -> 2.4s
#   4+          -> 2.6s   (a genuine ramble; wait them out)
#
# Measured against the reported failure: six fragments with 0.8-1.6s breaths
# came back as six answers before this, one answer after.
CONSOLIDATION_SETTLE_BASE_SECS = 1.5
CONSOLIDATION_SETTLE_STEP_SECS = 0.45
CONSOLIDATION_SETTLE_MAX_SECS = 2.6


# ---------------------------------------------------------------------------
# PHASE 2: adaptive commit window. Built, wired, and OFF.
# ---------------------------------------------------------------------------
#
# Turn commit is the single biggest latency we own: measured p50 1,680ms and
# p95 8,632ms across three production calls, against an industry target of
# 150-300ms. Smart Turn v3 answers "is this a finished thought?" in ~65ms and
# we then start a 1.5-2.6s stopwatch anyway, which is the whole problem.
#
# But session 5e1732cb showed why a flat 600ms would be WORSE, not better, for
# some speakers. One thought arrived as four transcripts:
#
#   05:35:26  heard   "Actually, we are just starting to take some agency"
#   05:35:29  BARGE   2.26s   <- she had started answering; he kept talking
#   05:35:32  heard   "market."
#   05:35:33  BARGE   1.06s   <- again
#   05:35:40  heard   "And that's been exploding a lot. So we have to"
#
# Committing sooner would have cut him off sooner. To him it sounded like a bad
# connection; Cartesia was steady at 80ms p50 the whole time.
#
# So the window is per-session and moves BOTH ways:
#
#   600ms means "I am confident this turn is finished"
#   NOT     "any silence past 600ms means they stopped"
#
# Clean speaker -> stay fast. Speaker who has demonstrated mid-thought pauses
# -> widen, back toward the old conservative behaviour and past it if needed.
# Smart Turn stays authoritative: this only accelerates a COMPLETE verdict, it
# never substitutes a timer for one.
FAST_COMMIT_SECS = 0.6

# Master switch. OFF until the A/B runs. With this False, _commit_window()
# returns exactly _settle_window() and behaviour is bit-for-bit unchanged --
# which is what makes it safe to deploy the machinery before the decision.
FAST_COMMIT_ENABLED = False

# Each observed fragmentation event adds this much protection, so a speaker who
# keeps continuing through the agent gets progressively more room.
FRAGMENTATION_PROTECTION_STEP_SECS = 0.5

# Ceiling on that protection. Above the old CONSOLIDATION_SETTLE_MAX_SECS on
# purpose: for a genuinely fragmented speaker the old 2.6s was itself too
# short, which is what produced the 8.6s p95 via the stall backstop.
FRAGMENTATION_PROTECTION_MAX_SECS = 2.4

# How long after the agent starts speaking a user utterance still counts as
# "they had not finished" rather than a fresh interruption. Above this it is an
# ordinary barge-in and says nothing about our commit timing.
EARLY_FOLLOWUP_WINDOW_SECS = 2.0

# Fragmentation decays. Someone who rambled early then settled down should get
# the fast path back rather than being punished for the rest of the call.
FRAGMENTATION_DECAY_TURNS = 6

# How long a gap must be before a new fragment counts as a genuine PAUSE
# rather than a breath inside one sentence.
#
# The adaptive window grows because someone who paused-and-continued is
# telling you they're mid-thought. That inference is only valid if a
# "fragment" means a considered pause. It stopped being valid the moment
# VAD stop_secs dropped from 1.0 to 0.3: an ordinary sentence started
# producing four fragments, the window grew 1.5 -> 2.6s inside a single
# utterance, and the clock restarted on every breath. Measured median went
# 4.0s -> 7.6s — worse than before any of this.
#
# So the growth now keys off the actual gap between fragments, not off how
# often VAD happens to segment. That makes the window a function of human
# behaviour rather than of a tuning constant one layer down, which is what
# it always should have been — a fragment arriving 200ms after the last one
# is the same breath, however VAD chose to cut it.
FRAGMENT_PAUSE_MIN_GAP_SECS = 0.8

# Hard ceiling on how long the deferred-interruption buffer may hold the
# floor before it gets answered no matter what.
#
# That buffer's drain requires FIVE conditions at once — VAD silent, settle
# window elapsed, Smart Turn calling the utterance complete, no half
# transcript in hand, no turn or speech running. Each is individually right,
# but together they form an AND with no timeout, so any single one sticking
# holds the prospect's words indefinitely. Worse, _maybe_schedule_auto_continue
# refuses to queue a walkthrough beat while ANY buffer is non-empty, so a
# stuck buffer doesn't just delay one answer — it silences the tour.
#
# Prod session 92a7ddaf logged nineteen consecutive
#   "auto-continue chain stalled ... could NOT be rescheduled
#    (blocked by: pending fragment)"
# while the prospect sat asking why nothing was happening.
#
# So the buffer gets a deadline. Past it, whatever is held gets answered
# even if the quiet-checks still object: replying to a slightly-early
# utterance is a small cost, going mute for the rest of the call is not.
PENDING_INTERRUPTION_MAX_HOLD_SECS = 6.0


# Hard ceiling on how long a walkthrough pause may last before the tour
# resumes on its own.
#
# walkthrough_awaiting_answer is a latch: easy to set (any garbled transcript
# trips it) and, by design, exitable ONLY by the model volunteering
# resume_walkthrough — which its own schema tells it to be conservative
# about. Worse, the self-healing watchdog switches itself OFF while the latch
# is set, so the one mechanism built to recover a dead tour is disabled in
# precisely the state that kills it.
#
# Confirmed live (visitor a335c780): the tour froze repeatedly and the
# prospect had to say "continue", "why are you waiting for me", "do it" five
# separate times. The moment the flag cleared, nine steps ran perfectly with
# no input at all — it was never unwillingness, it was a deadlock.
#
# 45s: far longer than any genuine "let me answer their question" pause, so a
# real tangent is never cut short, but bounded so a stuck latch can no longer
# end the demo. Resuming a tour one beat early is a small cost; silently
# ending it is not.
WALKTHROUGH_LATCH_MAX_SECS = 45.0

# Spoken before resuming, so picking the thread back up doesn't sound like a
# glitch or like the agent ignored something. Deliberately not an apology —
# nothing went wrong from the prospect's side.
FALSE_INTERRUPTION_RESUME_PREFIXES = ["Sorry, where was I —", "Anyway —", "So, as I was saying —"]

# Short affirmations that Smart Turn sometimes judges INCOMPLETE even though
# they are unmistakably a whole turn — confirmed live: a bare "Yeah." sat
# held for 4.85 seconds. Matched after stripping punctuation/case, and only
# when the fragment is this word ALONE (a single word can't be the front of a
# longer sentence in any way that matters here). Anything longer still goes
# through Smart Turn normally: the fast-track exists to fix an obvious
# false-negative, not to second-guess the turn detector generally.
FAST_TRACK_AFFIRMATIONS = {
    "yeah", "yes", "yep", "yup", "ok", "okay", "sure", "right", "correct",
    "no", "nope", "nah", "exactly", "perfect", "great", "cool", "thanks",
}

REST_API_URL = "http://localhost:8787"

# Fired when the prospect explicitly pushes for real, live generation
# instead of just walking a flow — see runtime.py's instruction 13 and
# registry.py's "meeting"/"example-gallery" entry. Matched exactly against
# the action dict _report_action receives, to trigger the booking-link chat
# message below alongside it.
EXAMPLE_GALLERY_ACTION = {"page": "meeting", "component": "example-gallery", "method": "open"}
# The real booking link. No code change needed elsewhere if this ever
# changes again — this is the only place it's referenced.
BOOKING_LINK_URL = "https://www.swishx.com/calendar"

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

# One nudge partway through a silence, not a whole escalating sequence — a
# real rep breaks a long silence once, they don't keep asking "still there?"
# every 15 seconds. bot.py's _watch_idle fires this once per idle streak,
# the first time total idle time crosses this threshold (still well short
# of IDLE_TIMEOUT_SECS, so there's always room to respond before the real
# farewell). A small random jitter is added at each new idle streak (see
# _watch_idle) so it doesn't land on the exact same second on every call.
#
# Raised 15 -> 30 after a real demo where the nudge repeatedly landed while
# the prospect was simply watching a rendered video play (nothing for them to
# say for a minute at a time) or thinking through a real answer. 15s is a
# normal length for a considered pause in a sales conversation; 30s is not.
# Note this only became a genuine 30 seconds alongside the BotStoppedSpeakingFrame
# clock fix above — before it, a long agent answer consumed most of the
# budget before the room ever went quiet.
IDLE_CHECKIN_THRESHOLD_SECS = 30

# Picked at random so back-to-back demo calls don't all hear the identical
# line. Named/unnamed variants — prospect_name may not be captured yet this
# early in some calls (see SessionState.prospect_name).
IDLE_CHECKIN_MESSAGES = {
    "named": ["Hey {name}, just checking you're still with me.", "Still there, {name}? Take your time."],
    "unnamed": ["Hey, just checking you're still with me.", "Still there? Take your time."],
}

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
# ("Hmm, right —") for when they just made a statement/comment and the agent
# is simply holding the floor for a moment before continuing, not thinking
# hard. Previously both cases drew from an overlapping pool, which read as
# unnatural (e.g. "Hmm —" before a plain acknowledgment).
#
# FLOOR_FILLERS used to be "Um —"/"Mm —"/"Okay, um —"/"Sure, um —" —
# confirmed live (real call transcript) as consistently the wrong register:
# reads as a person stalling, not a curious listener. Every filler in this
# file is now Hmm-based, in a curious/thinking tone, never "um"/"uh"/"oh".
# Two pools, split by whether the prospect actually asked something.
#
# The split is the whole point. "Great question" is genuinely good when they
# asked a question — and grating when they said "go to the brief tab" and got
# told their instruction was a great question. Anything that COMMENTS on what
# they said can only live in the question pool.
#
# Which leaves the statement pool needing fillers that claim nothing at all,
# and that is what the elongated hesitations are for: "Hmmm", "Ummm", "Mmm"
# assert no interpretation of what was just said, so they cannot be wrong
# about it. They also buy more time than a clipped "Right —", which matters
# when the thing they are covering is 2-3 seconds of model latency — a short
# filler leaves exposed silence behind it, and exposed silence is what makes
# people think it has crashed.
#
# Elongation is kept to three letters. Cartesia renders "Hmmm" as a sound;
# six or more risks being spelled out letter by letter, which would be worse
# than no filler at all. NOT yet confirmed by ear — worth one listen.
THINKING_FILLERS = [
    "Great question —",
    "Hmmm —",
    "Good question —",
    "Ummm, let me think —",
    "Hmmm, let's see —",
]
FLOOR_FILLERS = [
    "Hmmm —",
    "Ummm —",
    "Mmm —",
    "Right —",
    "Okay —",
    "Got it —",
]

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _is_fast_track_affirmation(text: str) -> bool:
    """True for a bare one-word affirmation ("Yeah", "Okay.", "Sure!").

    Smart Turn occasionally rules these INCOMPLETE — reasonable in the
    abstract (someone may well be about to continue) but wrong often enough
    to hurt: a lone "Yeah." was held 4.85s on a real call. A single word
    can't have a meaningful continuation withheld by answering it, and these
    particular words are the ones a prospect uses to hand the floor BACK,
    which is exactly when a delay is most damaging.
    """
    stripped = text.strip().strip(".,!?;:").lower()
    return bool(stripped) and " " not in stripped and stripped in FAST_TRACK_AFFIRMATIONS


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

    # When _pending_interruption_text last went empty -> non-empty, bounding
    # how long it may hold the floor (see PENDING_INTERRUPTION_MAX_HOLD_SECS).
    #
    # Declared at class level, not only in __init__, so it exists on any
    # instance however it was constructed. Anything reading it before
    # __init__ has run would otherwise raise AttributeError deep inside the
    # drain path — a crash in the one code path whose entire job is to stop
    # the pipeline getting stuck.
    _pending_interruption_since: Optional[float] = None
    # When the prospect started holding the floor for the CURRENT turn. Set on
    # the first fragment of a turn, cleared when the turn is released — so it
    # measures the whole thought, not the gap since the last fragment.
    _turn_floor_started_at: Optional[float] = None
    _consecutive_auto_beats: int = 0
    # How many beats this tour may run before asking again. Doubles on each
    # bare "keep going" — see AUTO_BEAT_BUDGET_CAP.
    _auto_beat_budget: int = MAX_CONSECUTIVE_AUTO_BEATS
    # True only between speaking a FLOOR_RETURN_PROMPT and the prospect's next
    # turn. Gives "yes" its meaning; see _is_permission_to_continue.
    _awaiting_continue_answer: bool = False
    # Session fragmentation profile — the evidence the commit window reads.
    # Counts events where this speaker demonstrably had NOT finished when we
    # decided they had. Session-scoped only: nothing is learned across calls.
    _fragmentation_events: int = 0
    _turns_since_fragmentation: int = 0
    # VAD noise accounting. Every VAD start is the agent deciding someone is
    # talking; the ones that never produce a transcript were something else —
    # a fan, a keyboard, a door, mic bleed. That matters beyond cosmetics: while
    # _user_speaking is True the release gates at _watch_pending_fragment_stall
    # refuse to answer, so ambient noise can hold the agent silent. Reported
    # per call so "it thinks I'm talking when I'm not" becomes a number.
    _vad_starts: int = 0
    _vad_starts_without_speech: int = 0
    _vad_start_at: Optional[float] = None
    _saw_speech_this_vad: bool = False
    # The turn currently being measured. See turn_telemetry.py — this exists
    # because "how long before she made a sound" was unanswerable from logs.
    _telemetry: Optional[TurnTelemetry] = None
    # None unless RECORD_CALLS=true. Class-level default so the audio path can
    # never AttributeError on a test object built via __new__.
    _recorder: Optional[CallRecorder] = None
    # True while the text going through _speak() is the answer rather than a
    # bridge word, backchannel or handoff line. Read only by telemetry.
    _speaking_reply: bool = False
    _turn_counter: int = 0
    # Declared at class level for the same reason: the pause gates are read
    # from the scheduler and the stall watchdog, both of which run on paths
    # that must never raise. A missing attribute there would take down the
    # loop whose entire job is keeping the call alive.
    _paused: bool = False
    _paused_remainder: Optional[str] = None

    def __init__(self, visitor_id: str):
        super().__init__()
        self._visitor_id = visitor_id
        # Judges whether a VAD-stop-driven STT segment is an actually
        # complete thought or just a mid-utterance pause — see
        # _analyze_smart_turn/_maybe_handle_transcript. Silero VAD's
        # stop_secs=1.0 alone is a flat silence timer with no idea whether a
        # sentence was finished; this is pipecat's own bundled local ONNX
        # classifier (no network dependency, already-installed onnxruntime),
        # layered on top rather than replacing VAD — VAD still owns
        # start/stop timing (barge-in stays exactly as responsive as
        # before), this only gates whether a stop is treated as "they're
        # actually done" before a reply gets generated for it. Confirmed
        # live as a real bug otherwise: a real call got two separate replies
        # to "Hmm..." and "I'm just" before the prospect ever finished their
        # actual question.
        self._smart_turn = LocalSmartTurnAnalyzerV3()
        # Deliberately loud. A recording that starts silently is the failure
        # mode that matters here — anyone reading the log for any reason should
        # be able to see that this call is being captured.
        if recording_enabled():
            self._recorder = CallRecorder(visitor_id)
            logger.warning(
                f"[{visitor_id}] RECORD_CALLS=true — capturing this call's audio "
                f"for turn-detection research. Participants must already know."
            )
        # Set from analyze_end_of_turn()'s verdict at the most recent VAD
        # stop — read by _maybe_handle_transcript when the matching
        # transcript for that same segment arrives a moment later. Defaults
        # to False (i.e. "complete") so a segment this was never computed
        # for (should not normally happen, but fails open rather than fails
        # silent) behaves exactly like today, not like a stuck hold.
        self._last_turn_incomplete = False
        # Text held back because the last segment judged INCOMPLETE — see
        # _maybe_handle_transcript. Concatenated onto the next segment's
        # text once one finally judges COMPLETE (or the watchdog below
        # gives up waiting).
        self._pending_fragment_text = ""
        self._pending_interruption_since = None
        # The play/pause control (server.py's /api/pause mailbox). Paused
        # means: stop speaking now, run no new turns, schedule no walkthrough
        # beats. It is the visitor taking the floor outright, as opposed to
        # hand-raise, which queues a question politely behind the current
        # sentence.
        self._paused = False
        self._pause_poll_task: asyncio.Task | None = None
        # What she was part-way through saying when the pause landed, so play
        # can resume from the START of that sentence rather than its middle.
        # Streaming services all behave this way for the same reason: coming
        # back mid-clause is disorienting, and a couple of repeated words cost
        # nothing.
        self._paused_remainder: Optional[str] = None
        self._last_fragment_activity = time.monotonic()
        self._pending_fragment_watch_task: Optional[asyncio.Task] = None
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
        # Sentences from THIS turn's reply that were actually played to the
        # end, in order — the ground truth for what the prospect really
        # heard. Only ever appended to after `_speech_finished` confirms real
        # playback finished, never at the point text was merely queued for
        # TTS. Read by _amend_interrupted_turn when a barge-in cuts a reply
        # short, so the history entry can be corrected down from the full
        # intended reply to the spoken prefix (see runtime.amend_last_agent_turn).
        # Set once a backchannel has been spoken for the fragment currently
        # being held, so a long hold gets one acknowledgement, not one per
        # watchdog tick. Cleared whenever the held fragment changes or is
        # released (see _maybe_handle_transcript).
        self._fragment_backchannel_sent = False
        self._last_backchannel = ""
        self._spoken_parts: list[str] = []
        # The sentence that was mid-playback when an interruption landed —
        # genuinely heard in part, so it's recorded with a cut-off marker
        # rather than either dropped outright (which would under-report) or
        # kept whole (which would over-report).
        self._cut_off_part: Optional[str] = None
        # Bumped on any real speech from either side (see BotStartedSpeakingFrame/
        # VADUserStartedSpeakingFrame below) — read both by
        # _watch_auto_continue_stall (walkthrough staleness) AND by bot.py's
        # idle watcher (seconds_since_activity(), abandonment detection +
        # the 15s check-in). One clock for both, deliberately: a visitor
        # silently listening to an active, still-progressing walkthrough is
        # not "idle" by any reasonable definition — the pre-check-in version
        # of the 120s farewell got this right for free, since it only ever
        # read this single, all-speech clock. Confirmed live: a call where
        # you said one thing ("give me a walkthrough") and then just
        # listened for two straight minutes of continuous real narration —
        # nothing else — still got disconnected as abandoned once
        # seconds_since_activity() was pointed at a visitor-only clock
        # instead. _suppress_activity_bump below is the ONE deliberate
        # exception: the check-in/farewell's own filler speech must not
        # bump this, or it resets its own countdown (see that flag's
        # docstring for the exact bug that caused, and how the fix here
        # differs from the version that didn't work).
        self._last_activity = time.monotonic()
        # Guards BotStartedSpeakingFrame below so a check-in/farewell's own
        # speech can't bump _last_activity — without this, "still there?"
        # would reset the very clock it exists to observe, which is exactly
        # what happened previously: this flag existed before, cleared right
        # after the (non-blocking) _speak() call returned rather than after
        # the utterance actually finished playing — but the real
        # BotStartedSpeakingFrame this triggers doesn't arrive until
        # Cartesia actually starts that audio, well after _speak() itself
        # returns, so the flag was already back to False by the time it
        # needed to matter and every check-in reset its own countdown
        # anyway. Fixed this time by having _speak_without_activity_bump
        # (below) hold this flag until the utterance's real
        # BotStoppedSpeakingFrame arrives, not until _speak() returns.
        self._suppress_activity_bump = False
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
        # Set to time.monotonic() the moment a barge-in cuts speech off, and
        # cleared the moment any real transcript lands (which proves the
        # barge-in was genuine). If it survives FALSE_INTERRUPTION_TIMEOUT_SECS
        # it was a false positive — see _watch_pending_fragment_stall.
        self._interrupted_at: Optional[float] = None
        # When the interrupting speech began, and when VAD said it ended.
        # The gap between them is what decides real-vs-noise; the second is
        # what the recovery grace is measured from.
        self._interruption_speech_started_at: Optional[float] = None
        self._interruption_quiet_since: Optional[float] = None
        # When VAD last said the prospect stopped making sound. The
        # consolidation window (see the adaptive settle window) is measured
        # from here, so every new fragment pushes the reply back rather than
        # triggering one of its own.
        self._last_user_speech_ended_at: float = 0.0
        # When the walkthrough latch was last observed set, so
        # WALKTHROUGH_LATCH_MAX_SECS can bound it. None whenever the tour
        # isn't paused.
        self._latch_since: Optional[float] = None
        # How many separate utterances have piled up since the last answer.
        # Drives the adaptive settle window (see the constants above) and
        # resets to 0 every time something is actually answered.
        self._burst_fragments = 0
        # Consecutive turns that opened with a spoken filler.
        #
        # Fillers cover LLM latency, but nothing counted how often they
        # fired. A real call came back with 39 of 121 spoken chunks being
        # "Hmm" / "Mm-hm" / "Let me think" — 32% of everything she said,
        # and the prospect noticed unprompted. Any one is defensible; one
        # in three is a verbal tic. Worse, TWO systems emit them
        # independently (this, and the backchannel in
        # _watch_pending_fragment_stall), so the total was larger than
        # either author intended and neither could see it.
        # The last two bridges spoken, so _pick_filler can avoid both.
        self._recent_fillers: list[str] = []
        # The tail of the reply the prospect never heard, captured when a
        # turn ends interrupted. Spoken on false-interruption recovery.
        self._unspoken_remainder: Optional[str] = None
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

    def _pick_backchannel(self) -> str:
        """Short 'still listening' token for a held fragment. Avoids
        repeating the previous one back-to-back, same reason _pick_filler
        does: hearing the identical sound twice is what makes it read as a
        recording rather than a person."""
        pool = [b for b in BACKCHANNELS if b != self._last_backchannel] or BACKCHANNELS
        choice = random.choice(pool)
        self._last_backchannel = choice
        return choice

    def _pick_filler(self, heard_text: str) -> str:
        """Picks a bridge, avoiding the last two rather than just the last.

        With six per pool there is room to look back further, and two turns is
        the distance at which a repeat stops registering as one. Falls back
        through progressively weaker constraints so this can never fail to
        return something.
        """
        pool = THINKING_FILLERS if _is_question(heard_text) else FLOOR_FILLERS
        choices = (
            [f for f in pool if f not in self._recent_fillers]
            or [f for f in pool if f != self._last_filler]
            or pool
        )
        filler = random.choice(choices)
        self._last_filler = filler
        self._recent_fillers = ([filler] + self._recent_fillers)[:2]
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
            #
            # ACCUMULATE, never overwrite. This was `= frame.text` — a plain
            # assignment — which meant that if the prospect said two things
            # while one beat was in flight, the FIRST was silently destroyed
            # by the second. Confirmed against a real call (visitor
            # a335c780, turns 68-76): STT inverted "they are NOT tech savvy"
            # into "they are very tech savvy", the prospect immediately
            # corrected it mid-beat, and the correction was thrown away by
            # this line. He had to repeat it six turns later.
            #
            # This is also what every serious voice stack does. OpenAI's
            # Realtime API appends into a continuous server-side
            # input_audio_buffer and only commits at a detected endpoint, so
            # there is no such thing as speech arriving "at a bad time" to be
            # dropped. Joining here gives the same property: whatever the
            # prospect said during the beat is answered as ONE turn, in the
            # order they said it, rather than one utterance winning a race.
            #
            # Whitespace-joined rather than newline/punctuation-joined for
            # the same reason _maybe_handle_transcript does it: these are
            # segments of one continuous stretch of speech, not separate
            # messages, and the model reads them best as one sentence-ish run.
            if self._pending_interruption_text:
                combined = f"{self._pending_interruption_text} {frame.text}".strip()
            else:
                combined = frame.text
            logger.info(
                f"[{self._visitor_id}] stashing transcript mid-turn "
                f"(now {combined!r})"
            )
            self._pending_interruption_text = combined
            if self._pending_interruption_since is None:
                self._pending_interruption_since = time.monotonic()
            self._pending_interruption_source = "voice"
            self._note_fragment_gap()
            # Real words arrived — the barge-in was genuine, so cancel the
            # false-positive recovery and drop the unheard tail. Resuming an
            # explanation the prospect deliberately cut off is worse than
            # losing it: they interrupted precisely because they didn't want
            # to hear the rest.
            self._interrupted_at = None
            self._interruption_quiet_since = None
            self._unspoken_remainder = None
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
            self._smart_turn.set_sample_rate(frame.audio_in_sample_rate)
            await self.push_frame(frame, direction)
            if not self._greeted:
                self._greeted = True
                self._hand_raise_poll_task = asyncio.create_task(self._poll_hand_raise())
                self._pause_poll_task = asyncio.create_task(self._poll_paused())
                self._meeting_chat_poll_task = asyncio.create_task(self._poll_meeting_chat())
                self._auto_continue_watchdog_task = asyncio.create_task(self._watch_auto_continue_stall())
                self._pending_fragment_watch_task = asyncio.create_task(self._watch_pending_fragment_stall())
                await self._greet(direction)
            return

        if isinstance(frame, BotStartedSpeakingFrame):
            self._bot_speaking = True
            self._speech_finished.clear()
            if not self._suppress_activity_bump:
                self._last_activity = time.monotonic()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, BotStoppedSpeakingFrame):
            self._bot_speaking = False
            self._speech_finished.set()
            # Bump the idle clock on speech ENDING, not just on it starting.
            # Confirmed live (2026-08-20 05:20:45): a 13-second sentence
            # started at :30.3 and ended at :43.4, but the clock had been set
            # at :30.3 — so the 15s check-in fired at :45.5, giving the
            # prospect 2.1 seconds of actual silence before being asked
            # "Still there?". The longer and more useful the agent's answer,
            # the sooner it accused the prospect of leaving. Idle has to mean
            # "quiet since the room went quiet", not "since someone last
            # started talking".
            if not self._suppress_activity_bump:
                self._last_activity = time.monotonic()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, VADUserStartedSpeakingFrame):
            # Telemetry clock for the turn that's forming. Opened here rather
            # than at commit so user_speech_ms covers the whole utterance, and
            # so t_user_speech_end (the reference point for every latency we
            # care about) has somewhere to land.
            self._telemetry_open()
            # Deliberately does NOT bump _last_activity any more.
            #
            # VAD fires on any sound above threshold — a cough, a keyboard, a
            # door, mic bleed from the shared screen's own audio. Treating
            # that as "the prospect is engaged" meant an empty room with a
            # fan in it re-armed the idle clock forever, so a call nobody was
            # on never hung up: a real session ran 63 minutes, announced
            # twice that it was leaving, and stayed. That mattered less while
            # a check-in nagged every 30s; now that the check-in is gone, the
            # hangup is the ONLY thing ending an abandoned call, so it has to
            # actually work.
            #
            # Activity now means a real finalized transcript (see
            # _maybe_handle_transcript), a typed message, or a hand-raise —
            # things a person definitely did. _user_speaking is still set
            # here, because barge-in detection genuinely does want the
            # earliest possible signal.
            self._user_speaking = True
            self._vad_starts += 1
            self._vad_start_at = time.monotonic()
            self._saw_speech_this_vad = False
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
                # Arm false-positive recovery and note when the speech
                # began. Whether it turns out to be a real barge-in or a
                # noise blip is decided on VAD-stop, by how long it lasted.
                self._interrupted_at = time.monotonic()
                self._interruption_speech_started_at = time.monotonic()
                self._interruption_quiet_since = None
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
            # The VAD window just closed. If no transcript ever landed inside it,
            # whatever triggered it wasn't speech — and it still blocked the
            # release gates for as long as it lasted.
            if not self._saw_speech_this_vad and self._vad_start_at is not None:
                self._vad_starts_without_speech += 1
                held = time.monotonic() - self._vad_start_at
                logger.debug(
                    f"[{self._visitor_id}] VAD fired with no speech ({held:.2f}s) — "
                    f"{self._vad_starts_without_speech}/{self._vad_starts} this call"
                )
            # Same reasoning as VADUserStartedSpeakingFrame above: a VAD stop
            # only means a sound ended, not that a person spoke.
            # Every time they stop, the consolidation window restarts. A new
            # fragment therefore pushes the reply further out instead of
            # racing one of its own — which is exactly what turns five
            # fragments into one answer instead of five.
            self._last_user_speech_ended_at = time.monotonic()
            # NOT stamped into the record here. This assignment used to be
            # direct (not mark()), so every subsequent VAD stop overwrote it —
            # and because the consolidation window spans several VAD cycles per
            # turn, the final value routinely landed AFTER the commit. That is
            # what produced turn_commit_latency_ms of -732ms in the first
            # baseline.
            #
            # The honest reference point is "the last time they stopped talking
            # before we accepted the turn", which is only knowable at commit.
            # _last_user_speech_ended_at above already tracks it; the record
            # copies it in _handle_real_turn.
            if self._bot_speaking:
                # They started again while a reply was already under way. May
                # be a genuine interruption rather than us cutting them off —
                # named for the observation, not the conclusion.
                if self._telemetry is not None:
                    self._telemetry.early_commit_followup = True
                # ...but for the commit window the intent doesn't matter. What
                # matters is that this speaker continues through the agent, and
                # that they need more room before we decide they're done.
                self._note_fragmentation_event("spoke over the reply")
            # Decide, right here, whether what just ended was a real
            # barge-in or a noise blip — this is the only moment both the
            # start and end of the segment are known -- and it happens well
            # before the transcript could arrive, which is exactly the bug
            # this used to have: duration alone decided "this was definitely
            # real" and _unspoken_remainder was wiped right here, permanently,
            # with no later check for whether any words actually showed up.
            #
            # Session 8439c3af measured the cost precisely: 40 VAD events in
            # one 19-minute call produced no transcript at all, 35 of them
            # long enough (>= MIN_REAL_INTERRUPTION_SECS) to have hit the old
            # "certain, don't resume" branch -- meaning 35 times the agent
            # would have abandoned whatever she was saying over noise that
            # was never actually speech, with no way back.
            #
            # spoke_for still matters as a signal, just not as a VERDICT: it
            # only changes what gets logged, not whether recovery is
            # possible. Both branches now do the same thing the short-blip
            # case always did -- start the grace clock and let a transcript,
            # if one shows up, settle it. Genuine long barge-ins lose nothing
            # here: real speech produces a transcript in well under a
            # second, long before FALSE_INTERRUPTION_GRACE_AFTER_SILENCE_SECS
            # elapses, and the instant it lands, _maybe_handle_transcript's
            # own "real words arrived" clear (see its comment) cancels this
            # exactly as before -- confirmed real, remainder dropped,
            # nothing resumes. This block only ever changes the outcome for
            # the case that used to have no recovery at all: long silence,
            # confirmed genuinely empty.
            if self._interrupted_at is not None:
                started = self._interruption_speech_started_at
                spoke_for = (time.monotonic() - started) if started is not None else 0.0
                self._interruption_quiet_since = time.monotonic()
                if spoke_for >= MIN_REAL_INTERRUPTION_SECS:
                    logger.info(
                        f"[{self._visitor_id}] long VAD event ({spoke_for:.2f}s) — "
                        f"waiting for a transcript before deciding; resuming if none lands"
                    )
                else:
                    logger.info(
                        f"[{self._visitor_id}] possible false interruption "
                        f"({spoke_for:.2f}s) — will resume if no transcript lands"
                    )
            # Judge the segment that's ending right now, before its
            # transcript even arrives — see _analyze_smart_turn's docstring.
            # TranscriptionFrame reads the verdict this sets a moment later,
            # once STT actually finishes transcribing.
            await self._analyze_smart_turn()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, InputAudioRawFrame):
            # Fed continuously so the analyzer has the actual audio to judge
            # once analyze_end_of_turn() is triggered above — see
            # LocalSmartTurnAnalyzerV3/BaseSmartTurn. append_audio also
            # carries its own internal silence safety net (COMPLETE once
            # ~3s of raw silence passes even without an explicit VAD-stop
            # trigger); checked here for that rare case too, mirroring
            # pipecat's own reference turn-strategy.
            # Research capture, off unless RECORD_CALLS=true (see
            # call_recorder.py). Taps the SAME bytes Smart Turn is judging, so
            # a replay is exactly what the model heard — the whole point, since
            # the harness's synthetic verdicts are what misled us. Append only;
            # anything costlier here would perturb the timings being measured.
            if self._recorder is not None:
                self._recorder.append(frame.audio)
            state = self._smart_turn.append_audio(frame.audio, self._user_speaking)
            if state == EndOfTurnState.COMPLETE:
                await self._analyze_smart_turn()
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            # Proof that the VAD window we're in carried actual words.
            self._saw_speech_this_vad = True
            await self._maybe_handle_transcript(frame.text, direction)
            return

        await self.push_frame(frame, direction)

    async def _analyze_smart_turn(self) -> None:
        """Runs Smart Turn's ML judgment on the audio buffered since the
        last call, storing the verdict for _maybe_handle_transcript to read
        once the matching transcript arrives. Cheap to call speculatively
        (a single ONNX inference on a short audio clip, off the event loop
        via BaseSmartTurn's own thread executor) — called from both the
        explicit VAD-stop trigger and append_audio's own internal silence
        safety net above."""
        state, _ = await self._smart_turn.analyze_end_of_turn()
        self._last_turn_incomplete = state == EndOfTurnState.INCOMPLETE
        if self._telemetry is not None:
            self._telemetry.mark("t_smart_turn_verdict")
            # Recorded per turn so Phase 2 can measure how often COMPLETE is
            # right — the number that decides whether the fast path is safe.
            self._telemetry.smart_turn_verdict = (
                "INCOMPLETE" if self._last_turn_incomplete else "COMPLETE"
            )

    async def _maybe_handle_transcript(self, text: str, direction: FrameDirection) -> None:
        """Gates a finalized transcript segment on whether Smart Turn judged
        the audio it came from a genuinely complete thought (see
        _analyze_smart_turn) instead of treating every VAD-stop-driven STT
        segment as its own complete turn — Silero VAD's stop_secs=1.0 alone
        can't tell "actually done talking" from "paused mid-sentence,"
        confirmed live as a real bug: a real call got two separate replies
        to "Hmm..." and "I'm just" before the prospect ever finished their
        actual question.

        An INCOMPLETE verdict holds this segment's text rather than
        answering it — appended to whatever's already pending from an
        earlier INCOMPLETE segment in the same still-forming utterance.
        Nothing is spoken while held (no filler, no reply): silence while
        the prospect finishes their thought is the whole point, not a
        flicker of "still thinking" between fragments.

        A COMPLETE verdict releases everything held so far, combined with
        this segment's own text, as one real turn. _watch_pending_fragment_stall
        is the safety net for a verdict that never arrives.
        """
        # Same proof-of-genuineness as the mid-turn stash path above.
        self._interrupted_at = None
        self._interruption_quiet_since = None
        self._unspoken_remainder = None
        combined = f"{self._pending_fragment_text} {text}".strip() if self._pending_fragment_text else text
        if self._last_turn_incomplete and not _is_fast_track_affirmation(combined):
            self._note_fragment_gap()
            self._pending_fragment_text = combined
            self._last_fragment_activity = time.monotonic()
            # NOT re-arming the backchannel here. Appending a fragment is the
            # same person still talking — it is not a new turn, and treating it
            # as one is what produced the nod clusters. The nod re-arms only
            # when a turn is actually RELEASED (see the release sites below).
            self._start_floor_hold()
            logger.info(f"[{self._visitor_id}] holding incomplete fragment: {combined!r}")
            return
        if self._last_turn_incomplete:
            # Fast-tracked past an INCOMPLETE verdict — see
            # FAST_TRACK_AFFIRMATIONS for why this specific carve-out. These
            # hand the floor BACK ("yeah", "okay"), so they answer at once
            # rather than sitting out the consolidation window below.
            if self._telemetry is not None:
                self._telemetry.released_by = "fast_track"
            logger.info(f"[{self._visitor_id}] fast-tracking short affirmation past INCOMPLETE: {combined!r}")
            self._pending_fragment_text = ""
            self._end_floor_hold()
            await self._handle_real_turn(combined, direction)
            return
        # COMPLETE — but "complete sentence" is not "finished talking".
        # Answering here is what produced one reply per fragment: six
        # sentences with ordinary breaths between them came back as six
        # separate answers, because each one was individually a valid whole
        # sentence. Smart Turn is judging grammar; the prospect is mid-
        # THOUGHT.
        #
        # So hold it and let the consolidation window decide, exactly like
        # the mid-turn stash path. Anything else they say keeps appending,
        # and _watch_pending_fragment_stall answers all of it once the room
        # has actually been quiet for the adaptive settle window. Found by
        # the stress harness, which drove six fragments through the real
        # idle path and got six answers back.
        self._note_fragment_gap()
        self._pending_fragment_text = combined
        self._last_fragment_activity = time.monotonic()
        # Same reasoning as the INCOMPLETE append above: still the same turn.
        self._start_floor_hold()
        logger.info(
            f"[{self._visitor_id}] holding fragment {self._burst_fragments} "
            f"(window now {self._settle_window():.1f}s): {combined!r}"
        )

    async def _watch_pending_fragment_stall(self) -> None:
        """Safety net for a fragment Smart Turn keeps calling INCOMPLETE —
        a model misfire, or someone who trails off and never actually comes
        back. Without this, a wrong verdict would hold the prospect's words
        forever with no reply at all, which is worse than the premature-
        interruption bug this whole mechanism exists to fix. Same
        lightweight polling pattern as _watch_auto_continue_stall, but
        independent of walkthrough state — this applies to every turn, not
        just an active tour."""
        try:
            while True:
                # Each pass is individually guarded. This loop is the only thing
                # that ever drains _pending_fragment_text and
                # _pending_interruption_text, so if one tick raises — a TTS
                # hiccup in the backchannel, a closed transport mid-flush — the
                # task dies and the prospect's words sit in a buffer with
                # nothing left to answer them, silently, for the rest of the
                # call. That is the exact failure this watchdog exists to
                # prevent, so it must not be able to fail that way itself.
                # Found by test_smart_turn_gate: the backchannel raised with no
                # pipeline attached and the stall flush behind it never ran.
                try:
                    await asyncio.sleep(PENDING_FRAGMENT_WATCHDOG_INTERVAL_SECS)
                    # A stashed mid-beat interruption that _advance_after_turn
                    # deliberately left behind because the prospect was still
                    # talking when the beat ended (see its docstring). Now that
                    # the room is quiet, answer it — this is the only thing that
                    # will, since _advance_after_turn has already returned and
                    # nothing else drains this buffer.
                    if (
                        self._pending_interruption_text
                        and not self._turn_in_progress
                        and not self._bot_speaking
                        and not self._user_speaking
                        # Every signal this pipeline has, all pointing at "they
                        # are genuinely finished", before a single word is said
                        # back. Free VAD alone can't tell a breath from a turn
                        # handover, so it is deliberately the weakest of the four:
                        #
                        #  1. VAD says silent            (_user_speaking False)
                        #  2. silent for long enough     (settle window below)
                        #  3. Smart Turn v3 calls the last segment a COMPLETE
                        #     thought — semantic, not acoustic, so "so the thing
                        #     is..." trailing off still counts as unfinished
                        #  4. nothing half-transcribed still in hand
                        #
                        # Any one of them saying "not yet" keeps accumulating.
                        and (
                            (
                                time.monotonic() - self._last_user_speech_ended_at
                                >= self._commit_window()
                                and not self._last_turn_incomplete
                                and not self._pending_fragment_text
                            )
                            # ...or the deadline passed. See
                            # PENDING_INTERRUPTION_MAX_HOLD_SECS: the AND above
                            # has no timeout of its own, so one sticky signal
                            # can hold these words — and the whole walkthrough —
                            # for the rest of the call.
                            or (
                                self._pending_interruption_since is not None
                                and time.monotonic() - self._pending_interruption_since
                                >= PENDING_INTERRUPTION_MAX_HOLD_SECS
                            )
                        )
                    ):
                        pending = self._pending_interruption_text
                        self._pending_interruption_text = None
                        self._pending_interruption_since = None
                        pending_source = self._pending_interruption_source
                        self._pending_interruption_source = "voice"
                        logger.info(
                            f"[{self._visitor_id}] draining deferred interruption: {pending!r}"
                        )
                        await self._handle_real_turn(
                            pending, FrameDirection.DOWNSTREAM, source=pending_source
                        )
                        continue
                    # False-interruption recovery. Something cut the agent off,
                    # the timeout has passed, and no transcript ever arrived to
                    # justify it — so it was noise, and the rest of the answer is
                    # still owed. All four quiet-checks must hold: resuming into
                    # someone who IS talking would be the very cut-in this fixes.
                    if (
                        self._interrupted_at is not None
                        and self._unspoken_remainder
                        and not self._turn_in_progress
                        and not self._bot_speaking
                        and not self._user_speaking
                        and not self._pending_interruption_text
                        and not self._pending_fragment_text
                        # Never before VAD has confirmed the room went quiet AND
                        # the segment was classified as too short to be speech.
                        # This is None while they're still talking and gets
                        # cleared outright on a real barge-in, so neither case
                        # can reach the resume below.
                        and self._interruption_quiet_since is not None
                        and time.monotonic() - self._interruption_quiet_since
                        >= FALSE_INTERRUPTION_GRACE_AFTER_SILENCE_SECS
                    ):
                        remainder = self._unspoken_remainder
                        self._interrupted_at = None
                        self._interruption_quiet_since = None
                        self._interruption_speech_started_at = None
                        self._unspoken_remainder = None
                        prefix = random.choice(FALSE_INTERRUPTION_RESUME_PREFIXES)
                        logger.info(
                            f"[{self._visitor_id}] false interruption — resuming: {remainder[:80]!r}"
                        )
                        # Bypasses the model entirely (this is text it already
                        # produced), so it persists and reports itself the way
                        # every other spoken line does — otherwise it would be a
                        # silent gap in the transcript DB and the chat UI.
                        resumed = f"{prefix} {remainder}"
                        session = get_session(self._visitor_id)
                        if session.visitor_id:
                            gate_log.append_transcript_turn(session.visitor_id, "agent", resumed)
                        self._current_reply_source = "voice"
                        asyncio.create_task(self._report_reply(resumed))
                        await self._speak(resumed, FrameDirection.DOWNSTREAM)
                        continue
                    if not self._pending_fragment_text:
                        continue
                    if self._turn_in_progress or self._bot_speaking or self._user_speaking:
                        continue
                    # Settled: Smart Turn called it a complete thought AND the
                    # room has been quiet long enough that nothing more is
                    # coming. Answer everything held, as one turn. This is the
                    # normal path now; the stall grace below is only the safety
                    # net for a verdict that stays INCOMPLETE forever.
                    if (
                        not self._last_turn_incomplete
                        and not self._pending_interruption_text
                        and time.monotonic() - self._last_user_speech_ended_at
                        >= self._commit_window()
                    ):
                        pending = self._pending_fragment_text
                        self._pending_fragment_text = ""
                        self._end_floor_hold()
                        if self._telemetry is not None:
                            self._telemetry.released_by = "settle"
                        logger.info(f"[{self._visitor_id}] settled — answering once: {pending!r}")
                        await self._handle_real_turn(pending, FrameDirection.DOWNSTREAM)
                        continue
                    held_for = time.monotonic() - self._last_fragment_activity
                    # Audible "I'm still here" partway through the hold, well
                    # before the flush below. Once per held fragment — a nod, not
                    # a nag. Deliberately does NOT touch _pending_fragment_text
                    # or _last_fragment_activity: this is the agent making a
                    # sound, not the prospect speaking, so it must not extend the
                    # hold or reset the stall countdown it sits inside.
                    floor_held = self._floor_held_for()
                    # How much longer the settle window has to run. A nod is
                    # only worth making if the answer isn't about to arrive
                    # anyway — see BACKCHANNEL_MIN_LEAD_SECS. This is the
                    # cancellation requirement in its practical form: rather
                    # than starting a nod and racing to abort it, don't start
                    # one we can already see will collide.
                    quiet_for = time.monotonic() - self._last_user_speech_ended_at
                    lead = self._settle_window() - quiet_for
                    if (
                        not self._fragment_backchannel_sent
                        and floor_held >= BACKCHANNEL_MIN_FLOOR_HOLD_SECS
                        and lead >= BACKCHANNEL_MIN_LEAD_SECS
                    ):
                        self._fragment_backchannel_sent = True
                        if self._telemetry is not None:
                            self._telemetry.backchannel_count += 1
                        backchannel = self._pick_backchannel()
                        logger.info(
                            f"[{self._visitor_id}] floor held {floor_held:.1f}s (lead {lead:.1f}s) "
                            f"— backchanneling {backchannel!r}"
                        )
                        await self._speak_without_activity_bump(backchannel)
                        continue
                    if held_for < PENDING_FRAGMENT_STALL_GRACE_SECS:
                        continue
                    pending = self._pending_fragment_text
                    self._pending_fragment_text = ""
                    # This release path never reset the nod at all, so after a
                    # stall flush the next turn inherited a spent flag and went
                    # un-acknowledged however long it ran.
                    self._end_floor_hold()
                    if self._telemetry is not None:
                        self._telemetry.released_by = "stall_backstop"
                    logger.warning(f"[{self._visitor_id}] pending fragment stalled, flushing: {pending!r}")
                    await self._handle_real_turn(pending, FrameDirection.DOWNSTREAM)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        f"[{self._visitor_id}] fragment watchdog pass failed — continuing"
                    )
        except asyncio.CancelledError:
            pass

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
        # THE definition of activity: a real finalized transcript. VAD no
        # longer bumps this clock (see VADUserStartedSpeakingFrame), so this
        # is what keeps a live call alive and what an abandoned one lacks.
        self._last_activity = time.monotonic()
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
        # Answered — the burst is over, so the next one starts impatient
        # again rather than inheriting a stretched window.
        self._burst_fragments = 0
        # The prospect spoke, so the tour is a two-way conversation again
        # and the beat budget resets. This is what lets "keep going" buy
        # another full run of beats rather than one at a time.
        self._consecutive_auto_beats = 0
        if self._burst_fragments > 1:
            # This turn arrived in pieces, which is the definition of a
            # mid-thought pause — recorded before _burst_fragments resets.
            self._note_fragmentation_event(f"{self._burst_fragments} fragments")
        else:
            self._turns_since_fragmentation += 1
        # A bare "keep going" earns a longer run before we ask again; anything
        # substantive resets to the cautious default, because that is evidence
        # they want the floor. Session 5e1732cb asked six times in five minutes
        # and got "continue" five times — the budget has to learn.
        asked = self._awaiting_continue_answer
        self._awaiting_continue_answer = False
        if _is_permission_to_continue(text, asked):
            grown = min(self._auto_beat_budget * 2, AUTO_BEAT_BUDGET_CAP)
            if grown != self._auto_beat_budget:
                logger.info(
                    f"[{self._visitor_id}] 'keep going' confirmed — beat budget "
                    f"{self._auto_beat_budget} -> {grown}"
                )
            self._auto_beat_budget = grown
        elif _is_acknowledgement(text):
            # HOLD. A nod is neither permission nor a bid for the floor, and
            # resetting on it is what made the growth above useless: the budget
            # reached 4 twice in one call and a bare "Okay." put it back to 2
            # both times, so the cap still fired at 2/2 six times.
            pass
        else:
            self._auto_beat_budget = MAX_CONSECUTIVE_AUTO_BEATS
        # Committed: this is the moment we accepted their words as a turn.
        # turn_detection_ms — the 1.5-2.6s window — is measured to right here.
        if source == "voice":
            self._telemetry_open()
        if source != "voice":
            # A typed message has no VAD window, so there is no honest zero
            # point for any of the voice latencies. Back-filling one from
            # _last_user_speech_ended_at is what produced
            # turn_commit_latency_ms = 49050 on a chat turn: a timestamp from
            # 49 seconds and one whole conversation earlier. Three of the four
            # telemetry records in session 0aa0aaeb were chat, all with
            # fabricated latencies, which would have poisoned any A/B built on
            # them. Chat turns are dropped from latency telemetry entirely
            # rather than reported with an invented reference.
            if self._telemetry is not None:
                logger.debug(
                    f"[{self._visitor_id}] {source} turn — no VAD window, "
                    f"latency telemetry dropped"
                )
                self._telemetry = None
        elif self._telemetry is not None:
            # Copied, not marked: this is when they last stopped talking before
            # this turn was accepted, which is the only defensible zero point
            # for every latency below. Taken here because only now is "before
            # the commit" a settled fact.
            if self._telemetry.t_user_speech_end is None:
                self._telemetry.t_user_speech_end = self._last_user_speech_ended_at
            self._telemetry.mark("t_turn_committed")
            self._telemetry.source = source
        self._begin_spoken_tracking()

        try:
            # Rationed: at most one filler, then a turn without. Two or
            # three in a row is what turns "thinking" into a stammer. The
            # backchannel path emits sounds too, so unrationed they stack.
            if self._paused:
                # Paused means the visitor holds the floor. Anything picked up
                # here is them talking to someone else in the room, or thinking
                # out loud — answering it would be exactly the interruption
                # they pressed the button to stop.
                logger.info(f"[{self._visitor_id}] dropping turn while paused: {text[:60]!r}")
                return
            # Always bridge. An earlier version rationed these — one turn on,
            # one turn off — to stop her sounding repetitive, and measurement
            # showed exactly what that bought: on session 4c23f875 the turns
            # WITH a filler reached audio in 1.2-1.5s and the turns without it
            # sat in 3.5-4.3s of complete silence, which reads as the thing
            # having crashed. Repetition was the wrong problem to solve by
            # subtraction; it is solved above, by pools that actually differ
            # from each other.
            filler = self._pick_filler(text)
            await self._speak(filler, direction)

            try:
                if self._telemetry is not None:
                    self._telemetry.mark("t_llm_request")
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

            # Correct the history entry BEFORE _advance_after_turn below: a
            # stashed interruption replays as a whole new turn from there and
            # appends its own entries, at which point the entry this needs to
            # fix is no longer the last one and the guard would (correctly)
            # refuse to touch it.
            self._amend_interrupted_turn(session, result)

            if self._hand_raised and not self._hand_ack_sent:
                # Either a raise landed right as the last sentence
                # finished (too late for _speak_reply's own per-sentence
                # check to catch), or the whole reply was one sentence to
                # begin with. Either way, this is the natural end-of-turn
                # point to hand off — _speak_reply already handles the
                # mid-reply case by breaking early and handing off itself,
                # which sets _hand_ack_sent so this doesn't double-fire.
                await self._speak_hand_raise_handoff(direction)

            await self._advance_after_turn(session, direction, last_user_text=text)
        finally:
            self._turn_in_progress = False
            # In the finally so a turn that ends by raising, or by being
            # interrupted, still reports. A latency record that only existed
            # for turns that went well would flatter every average we take.
            self._telemetry_close()

    async def _advance_after_turn(
        self, session, direction: FrameDirection, last_user_text: str = ""
    ) -> None:
        """Called at the end of every turn — real or auto-continued — instead
        of calling _maybe_schedule_auto_continue directly. Checks for a
        stashed dropped-interruption transcript first (see queue_frame's
        docstring): if one landed while this turn was in flight, replay it
        as the next real turn right now instead of scheduling the next
        scripted beat, so a genuine barge-in never just gets silently
        skipped over in favor of the tour continuing on schedule.

        _pending_interruption_text now ACCUMULATES everything said during the
        beat (see queue_frame), so this replays one turn carrying all of it
        rather than one turn per utterance. That removes the reason the old
        depth cap existed: the cap was there because replaying N separate
        stashes produced N unrelated answers back-to-back ("queuing up"), and
        its overflow branch spoke a canned "still catching up — could you say
        that again?" INSTEAD of the prospect's words. That branch is gone.
        Confirmed against a real call (visitor a335c780, turns 57 and 71):
        both of those canned lines were this cap firing, not speech-to-text
        failing, and turn 71 discarded a correction the prospect had to
        repeat six turns later. Joining the utterances answers all of them
        once, which is what the cap was trying to approximate by dropping.

        Chaining is naturally bounded now — a replay only follows a replay if
        the prospect spoke again DURING the replay, which is just a
        conversation, not a runaway.

        Defers while _user_speaking: replaying the instant a beat ends, while
        the prospect is still mid-sentence, is exactly the premature cut-in
        this whole redesign is about. _watch_pending_fragment_stall drains it
        once the room is actually quiet."""
        # Held voice input from the IDLE path lives in a DIFFERENT buffer
        # (_pending_fragment_text) than mid-turn barge-ins
        # (_pending_interruption_text). This used to check only the latter,
        # so during a walkthrough anything said in the gap between beats was
        # invisible here: the next scripted beat fired, _bot_speaking went
        # true, and the settle-window drain in _watch_pending_fragment_stall
        # could never run — the quiet moment it waits for never arrived
        # because the tour kept talking. The prospect's words sat in the
        # buffer for the rest of the tour.
        #
        # This is exactly the "it answers on chat but not on voice" report:
        # typed messages call _handle_real_turn directly and skip the window
        # entirely, so chat looked fine while voice went unheard.
        if self._pending_fragment_text:
            logger.info(
                f"[{self._visitor_id}] holding tour — voice input pending: "
                f"{self._pending_fragment_text!r}"
            )
            return
        pending = self._pending_interruption_text
        if pending is not None:
            # Still mid-sentence — leave it stashed and let it keep
            # accumulating. _watch_pending_fragment_stall replays it the
            # moment they actually stop. Deliberately does NOT schedule an
            # auto-continue on the way out: there is unanswered speech
            # pending, so firing the next scripted beat here is precisely
            # the "talked over me" behaviour being fixed.
            # ALWAYS deferred to _watch_pending_fragment_stall, never
            # answered inline. Answering here fired the moment VAD flipped
            # _user_speaking false — one second after the last sound — which
            # is shorter than an ordinary mid-thought pause. Each fragment
            # then got its own reply, and a single rambling answer came back
            # as five disconnected ones. The watchdog holds everything until
            # the adaptive settle window of real quiet, then replies once to
            # the joined text.
            logger.info(
                f"[{self._visitor_id}] holding stashed interruption for settle window: {pending!r}"
            )
            return
        self._maybe_schedule_auto_continue(session, direction, last_user_text=last_user_text)

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
        # Single choke point for "paused means silent". There are several
        # callers — the sentence loop, fillers, backchannels, walkthrough
        # beats, the false-interruption resume — and gating each of them
        # separately is how one gets missed. _leave_pause deliberately clears
        # the flag before it speaks its own re-entry line.
        if self._paused:
            return
        # First text handed to TTS this turn. This is time_to_first_tts_enqueue
        # and it is NOT acoustic TTFA — sound leaves the speaker an unmeasured
        # amount later. Conflating the two would bake an unknown constant into
        # every number we then tuned against, so they stay separate fields.
        if self._telemetry is not None:
            # Any sound at all — usually the bridge word, which is spoken before
            # the LLM call even starts.
            self._telemetry.mark("t_first_filler_enqueue")
            if self._speaking_reply:
                # ...and separately, the first text of the actual answer. These
                # were one mark until the first baseline showed
                # llm_to_tts_enqueue_ms = -1391ms on every record, because the
                # filler legitimately precedes the first token.
                self._telemetry.mark("t_first_reply_enqueue")
        # TTSService only flushes its sentence-aggregation buffer on an
        # LLMFullResponseEndFrame (or EndFrame) — a bare TextFrame gets
        # buffered and never actually synthesized. Bracketing this way is
        # what a real streaming LLM service's output would normally do; we
        # just do it in one shot per utterance since run_turn() already
        # returns complete text.
        await self.push_frame(LLMFullResponseStartFrame(), direction)
        await self.push_frame(TextFrame(text), direction)
        await self.push_frame(LLMFullResponseEndFrame(), direction)

    def _note_fragment_gap(self) -> None:
        """Grow the settle window only when a REAL pause preceded this
        fragment.

        A fragment landing a fraction of a second after the previous one is
        the same breath, whatever VAD decided; treating it as evidence of
        "they're mid-thought, wait longer" is what made an ordinary sentence
        stretch the window to its 2.6s ceiling and pushed median latency
        from 4.0s to 7.6s. See FRAGMENT_PAUSE_MIN_GAP_SECS.
        """
        gap = time.monotonic() - self._last_fragment_activity
        if self._burst_fragments == 0 or gap >= FRAGMENT_PAUSE_MIN_GAP_SECS:
            self._burst_fragments += 1
        else:
            logger.debug(
                f"[{self._visitor_id}] fragment {gap:.2f}s after the last — same breath, "
                f"window held at {self._settle_window():.1f}s"
            )

    def _telemetry_open(self) -> None:
        """Starts a telemetry record if one isn't already running. Idempotent:
        VAD can fire several times inside one forming turn (a breath, a false
        trigger) and only the first should start the clock."""
        if self._telemetry is None:
            self._turn_counter += 1
            self._telemetry = TurnTelemetry(
                visitor_id=self._visitor_id, turn_id=self._turn_counter
            )
            self._telemetry.mark("t_user_speech_start")

    def _telemetry_close(self, released_by: Optional[str] = None) -> None:
        """Emits the record and clears it. Safe to call when nothing is open —
        turns can end down several paths (normal, interrupted, disconnect) and
        none of them should have to know whether measuring was in progress."""
        tel = self._telemetry
        if tel is None:
            return
        if released_by and tel.released_by is None:
            tel.released_by = released_by
        tel.interrupted = self._interrupted_this_turn
        tel.fragments = self._burst_fragments
        tel.consecutive_auto_beats = self._consecutive_auto_beats
        tel.vad_starts = self._vad_starts
        tel.vad_starts_without_speech = self._vad_starts_without_speech
        tel.fragmentation_events = self._fragmentation_events
        tel.commit_window_ms = round(self._commit_window() * 1000)
        tel.mark("t_reply_complete")
        tel.emit()
        self._telemetry = None

    def _start_floor_hold(self) -> None:
        """Marks the beginning of the prospect holding the floor, if it isn't
        already running. Idempotent on purpose: every fragment of one thought
        calls this, and only the first should set the clock."""
        if self._turn_floor_started_at is None:
            self._turn_floor_started_at = time.monotonic()

    def _end_floor_hold(self) -> None:
        """A turn was actually released. This — and only this — is what re-arms
        the backchannel, which is the fix for the nod clusters."""
        self._turn_floor_started_at = None
        self._fragment_backchannel_sent = False

    def _floor_held_for(self) -> float:
        """Total seconds the prospect has held the floor this turn."""
        if self._turn_floor_started_at is None:
            return 0.0
        return time.monotonic() - self._turn_floor_started_at

    def _note_fragmentation_event(self, why: str) -> None:
        """Records that this speaker was still mid-thought when we committed.

        Deliberately not called "false cutoff": the prospect may simply have
        chosen to interrupt, and we have no ground truth to tell the two apart.
        What matters for the window is only that continuing-through-the-agent
        happened, whatever the intent."""
        self._fragmentation_events += 1
        self._turns_since_fragmentation = 0
        logger.info(
            f"[{self._visitor_id}] fragmentation signal ({why}) — "
            f"{self._fragmentation_events} this session, "
            f"protection now {self._fragmentation_protection():.1f}s"
        )

    def _fragmentation_protection(self) -> float:
        """Extra quiet this speaker has earned, in seconds.

        Decays: someone who rambled early and then settled gets the fast path
        back rather than being punished for the whole call."""
        decayed = self._turns_since_fragmentation // FRAGMENTATION_DECAY_TURNS
        active = max(0, self._fragmentation_events - decayed)
        return min(
            active * FRAGMENTATION_PROTECTION_STEP_SECS,
            FRAGMENTATION_PROTECTION_MAX_SECS,
        )

    def _commit_window(self) -> float:
        """How long the room must be quiet before a COMPLETE turn is answered.

        This is the one place Phase 2 changes behaviour, and while
        FAST_COMMIT_ENABLED is False it returns _settle_window() exactly — so
        the machinery ships and measures itself before the decision is taken.

        When enabled:
          clean speaker, unfragmented turn  -> FAST_COMMIT_SECS (~600ms)
          fragmented turn or fragmented speaker -> the conservative window,
              plus earned protection, which can exceed the old 2.6s ceiling
              because for a genuinely fragmented speaker 2.6s was itself too
              short (that is what produced the 8.6s p95 via the stall backstop)

        Smart Turn stays authoritative upstream: this only ever accelerates a
        verdict that already said COMPLETE.
        """
        conservative = self._settle_window()
        if not FAST_COMMIT_ENABLED:
            return conservative
        protection = self._fragmentation_protection()
        # Any fragmentation in THIS turn disqualifies the fast path outright,
        # regardless of session history — the evidence is right in front of us.
        if self._burst_fragments > 1 or protection > 0:
            return max(conservative, FAST_COMMIT_SECS + protection)
        return FAST_COMMIT_SECS

    def _settle_window(self) -> float:
        """How long the room must stay quiet before answering, given how
        many fragments are already waiting. See the CONSOLIDATION_* block."""
        return min(
            CONSOLIDATION_SETTLE_BASE_SECS
            + CONSOLIDATION_SETTLE_STEP_SECS * max(0, self._burst_fragments - 1),
            CONSOLIDATION_SETTLE_MAX_SECS,
        )

    def _begin_spoken_tracking(self) -> None:
        """Resets the spoken-prefix accumulator at the start of every turn —
        real, replayed, or auto-continued."""
        self._spoken_parts = []
        self._cut_off_part = None

    def _spoken_so_far(self) -> str:
        """What the prospect actually heard of this turn's reply, as text.

        Sentence-granular, which is as fine as this pipeline can resolve:
        `_speech_finished` fires per utterance pushed to TTS, so a sentence
        is the smallest unit we can confirm was fully played. (pipecat's own
        aggregator gets word granularity from PTS-stamped word frames, and
        the Realtime API gets milliseconds from audio_end_ms — both need
        word timestamps threaded through, which Cartesia supports and we
        could adopt later. Sentence level already captures the failure that
        actually hurt: a whole explanation recorded as delivered when the
        prospect never heard it.)"""
        parts = list(self._spoken_parts)
        if self._cut_off_part:
            parts.append(self._cut_off_part.rstrip() + CUTOFF_MARKER)
        return " ".join(p.strip() for p in parts if p.strip())

    def _amend_interrupted_turn(self, session, result: Optional[dict]) -> None:
        """Corrects this turn's history entry down to the spoken prefix when
        a barge-in cut the reply short. No-op unless the turn was actually
        interrupted AND something is genuinely missing.

        Zero-sentence case: if the interruption landed before even the first
        sentence finished playing, the honest record is that none of the
        reply was delivered — say exactly that rather than inventing a
        partial. The prospect did hear the filler and possibly a lead_in, but
        neither of those is part of `reply`, so neither belongs here."""
        if not self._interrupted_this_turn or not result:
            return
        full = result.get("reply")
        if not full:
            return
        spoken = self._spoken_so_far() or NOTHING_SPOKEN_MARKER
        # Everything the prospect did NOT hear, kept for false-interruption
        # recovery (see _watch_pending_fragment_stall). Computed from the
        # sentence list rather than string-slicing `full`, because the
        # spoken record carries CUTOFF_MARKER and other annotations that
        # aren't in the original text and would break a naive prefix match.
        heard = set()
        for part in self._spoken_parts:
            heard.add(part.strip())
        if self._cut_off_part:
            # Partially heard — repeat it whole rather than guessing where
            # inside the sentence the cut landed.
            heard.discard(self._cut_off_part.strip())
        remainder = " ".join(
            sent.strip() for sent in _split_sentences(full)
            if sent.strip() and sent.strip() not in heard
        ).strip()
        self._unspoken_remainder = remainder or None
        if amend_last_agent_turn(session, spoken, full):
            logger.info(
                f"[{self._visitor_id}] interrupted mid-reply — history corrected to what was heard "
                f"({len(spoken)}/{len(full)} chars): {spoken[:90]!r}"
            )

    async def _speak_reply(self, text: str, direction: FrameDirection) -> None:
        """Like _speak, but one sentence at a time — waiting for each
        sentence's real playback to finish (via _speech_finished, set/cleared
        off BotStartedSpeakingFrame/BotStoppedSpeakingFrame) before starting
        the next. This is what lets a hand-raise mid-reply interrupt at the
        sentence boundary it happened in, instead of only ever being noticed
        after the entire explanation has already been spoken."""
        # Marks everything spoken from here as the ANSWER, so telemetry can
        # tell time-to-first-sound (the bridge word) from time-to-reply. The
        # two were one number until the first baseline came back negative.
        self._speaking_reply = True
        try:
            for sentence in _split_sentences(text):
                if self._interrupted_this_turn:
                    return
                self._speech_finished.clear()
                await self._speak(sentence, direction)
                await self._speech_finished.wait()
                if self._interrupted_this_turn:
                    # Playback of THIS sentence was cut mid-way (the interruption
                    # is what ended the wait above) — partially heard, so it's
                    # recorded as truncated rather than as fully delivered.
                    self._cut_off_part = sentence
                    return
                self._spoken_parts.append(sentence)
                if self._hand_raised and not self._hand_ack_sent:
                    await self._speak_hand_raise_handoff(direction)
                    return

        finally:
            self._speaking_reply = False
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
                if self._paused:
                    # THE reason pause needed pressing two or three times.
                    #
                    # A reply is spoken sentence by sentence through this
                    # loop. Pausing cut the audio that was playing, but
                    # nothing here asked whether we were paused, so the loop
                    # calmly started the NEXT sentence — audio stopped, then
                    # restarted about a second later, which reads exactly
                    # like the button not having worked. Pressing again cut
                    # the new sentence, and the loop moved on again.
                    #
                    # Whatever is left of the reply is kept so play can pick
                    # it up rather than losing it.
                    self._paused_remainder = " ".join(
                        [sentence] + [c for c in chunks[chunks.index(sentence) + 1:] if c.strip()]
                    ).strip() or None
                    return True
                if self._interrupted_this_turn:
                    return True
                if _superseded_by_fresher_stash():
                    abandoned_before_speech = True
                    return True
                self._speech_finished.clear()
                # This — not _speak_reply — is the path a real streaming turn
                # takes, so the flag has to be set here too. It wasn't, which
                # is why time_to_reply_enqueue_ms came back as "never measured"
                # across an entire call: the only two callers that set it are
                # the non-streaming fallbacks, which almost never run.
                self._speaking_reply = True
                try:
                    await self._speak(sentence, direction)
                finally:
                    self._speaking_reply = False
                spoken_anything_yet = True
                await self._speech_finished.wait()
                if self._interrupted_this_turn:
                    # Cut mid-sentence — see the same branch in _speak_reply.
                    self._cut_off_part = sentence
                    return True
                self._spoken_parts.append(sentence)
                if self._hand_raised and not self._hand_ack_sent:
                    await self._speak_hand_raise_handoff(direction)
                    return True
            return False

        async for event in stream:
            # First event out of the stream. Not literally the first token —
            # run_turn_stream yields on parsed JSON boundaries — but it is the
            # first moment the model produced anything usable, which is what
            # llm_first_token_ms is actually asking about.
            if self._telemetry is not None:
                self._telemetry.mark("t_llm_first_token")
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

    def _maybe_schedule_auto_continue(
        self, session, direction: FrameDirection, last_user_text: str = ""
    ) -> None:
        """Called at the end of every real AND auto-continued turn.
        Schedules the next walkthrough beat to speak on its own after a
        short pause, unless the tour just ended or the model is waiting on
        a real answer to a genuine interruption (see
        SessionState.walkthrough_awaiting_answer and _walkthrough_note's
        interruption rule in runtime.py) — this is what makes "give me a
        walkthrough" keep going without the prospect needing to prompt
        every single beat, while still actually pausing for a real question
        instead of talking over it."""
        if self._paused:
            # Same shape as walkthrough_user_stopped below: while the visitor
            # holds the floor, nothing schedules itself behind them.
            return
        if session.walkthrough_step is None or session.walkthrough_awaiting_answer:
            return
        # Hard stop: nothing schedules a beat while the prospect has asked
        # for quiet.
        if session.walkthrough_user_stopped:
            return
        # Don't advance past where the prospect actually is. Only checked
        # against a REAL turn's own words (last_user_text is empty for an
        # auto-continue beat's own self-scheduling, which has no fresh
        # words to check) — see _is_hold_signal. Session be5a8774: the tour
        # moved from MagicReel into MagicAvatar while the prospect was still
        # asking about MagicReel's render screen, and needed three
        # corrective turns before the agent caught up. This stops the very
        # next beat outright rather than only narrowing the budget the way
        # a merely substantive (non-hold) reply already does.
        if last_user_text and _is_hold_signal(last_user_text):
            logger.info(
                f"[{self._visitor_id}] hold signal ({last_user_text[:60]!r}) — "
                f"not scheduling the next beat, staying on step {session.walkthrough_step}"
            )
            return
        # Never schedule a beat while the prospect has unanswered words
        # waiting. Firing here restarts the bot speaking, which blocks the
        # settle-window drain and strands their input (see
        # _advance_after_turn). Belt to that braces: this covers the
        # watchdog's own reschedule path too, not just end-of-turn.
        if self._pending_fragment_text or self._pending_interruption_text:
            return
        # The floor goes back to the prospect after a couple of beats. Without
        # this, session 7d0018d3 ran eight beats end to end and the prospect
        # simply stopped participating.
        #
        # Deliberately NOT a silent stop: going quiet mid-tour is its own
        # failure ("did it crash?"). The agent finishes this beat, asks whether
        # to continue, and parks on walkthrough_awaiting_answer — existing
        # machinery that already halts the chain and waits. A real turn resets
        # the counter, so answering "keep going" buys another full budget.
        if self._consecutive_auto_beats >= self._auto_beat_budget:
            logger.info(
                f"[{self._visitor_id}] auto-continue cap reached "
                f"({self._consecutive_auto_beats}/{self._auto_beat_budget} beats) "
                f"— returning the floor"
            )
            session.walkthrough_awaiting_answer = True
            self._consecutive_auto_beats = 0
            self._pending_auto_continue = asyncio.create_task(
                self._return_floor_after_beats(direction)
            )
            return
        # Only one continuation is ever in flight/pending at a time — a
        # fresh schedule call (from the auto-continue turn that's about to
        # finish and chain into the next one) replacing an old reference is
        # fine, since the old task, by definition, already fired by the
        # time this runs again.
        self._pending_auto_continue = asyncio.create_task(self._auto_continue_after_pause(session, direction))

    async def _return_floor_after_beats(self, direction: FrameDirection) -> None:
        """Hands the floor back with an actual question once the beat budget is
        spent. Waits for the beat in flight to finish first, the same way
        _auto_continue_after_pause does, so this doesn't talk over it."""
        try:
            try:
                await asyncio.wait_for(
                    self._speech_finished.wait(), timeout=AUTO_CONTINUE_SPEECH_WAIT_TIMEOUT_SECS
                )
            except asyncio.TimeoutError:
                pass
            await asyncio.sleep(AUTO_CONTINUE_PAUSE_SECS)
        except asyncio.CancelledError:
            return
        # If they started talking while we waited, they took the floor back
        # themselves and this question would be talking over them.
        if self._user_speaking or self._pending_fragment_text or self._turn_in_progress:
            return
        prompt = random.choice(FLOOR_RETURN_PROMPTS)
        # Persisted, not merely spoken. _speak() alone puts audio on the wire
        # and leaves no trace, so the agent had no record of having asked —
        # which is why it asked six times in five minutes in session 5e1732cb.
        # The prospect heard every one; the agent knew about none of them. Same
        # shape as the false-interruption resume path, and the same rule:
        # anything the prospect actually HEARS belongs in the history the next
        # turn reasons over, or the agent is answering a call that didn't happen.
        session = get_session(self._visitor_id)
        if session.visitor_id:
            gate_log.append_transcript_turn(session.visitor_id, "agent", prompt)
        session.history.append(HistoryEntry(role="agent", text=prompt))
        self._current_reply_source = "voice"
        asyncio.create_task(self._report_reply(prompt))
        # Arm the context. From here until their next turn, a bare "yes" means
        # "keep going" rather than merely "I'm listening".
        self._awaiting_continue_answer = True
        await self._speak(prompt, direction)

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
                if session.walkthrough_step is None:
                    self._latch_since = None
                    continue
                # The latch no longer switches this watchdog off permanently.
                # It still suppresses it — a paused tour SHOULD stay paused
                # while a real tangent plays out — but only up to
                # WALKTHROUGH_LATCH_MAX_SECS. Past that the pause is treated
                # as stuck rather than intentional and cleared here, which is
                # the escape hatch the latch never had.
                # An explicit human stop is absolute. No ceiling, no
                # watchdog, no timer — the prospect said stop, so the tour
                # stays down until THEY say otherwise. This check sits above
                # the latch ceiling deliberately: the ceiling exists for a
                # model that froze on a garbled transcript, and applying it
                # here is exactly what resumed the tour 45s after a real
                # person asked for quiet (see SessionState.walkthrough_user_stopped).
                if self._paused:
                    self._latch_since = None
                    continue
                if session.walkthrough_user_stopped:
                    self._latch_since = None
                    continue
                if session.walkthrough_awaiting_answer:
                    if self._latch_since is None:
                        self._latch_since = time.monotonic()
                    elif time.monotonic() - self._latch_since >= WALKTHROUGH_LATCH_MAX_SECS:
                        logger.warning(
                            f"[{self._visitor_id}] walkthrough latch stuck for "
                            f"{WALKTHROUGH_LATCH_MAX_SECS:.0f}s at step "
                            f"{session.walkthrough_step} — releasing so the tour can resume"
                        )
                        session.walkthrough_awaiting_answer = False
                        self._latch_since = None
                    continue
                self._latch_since = None
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
                # _maybe_schedule_auto_continue has its own guards and can
                # decline — most often because a fragment is still parked in
                # one of the pending buffers. When it declines there is
                # nothing scheduled and nothing healed, so say which it was.
                # The old unconditional "self-healing" line claimed success
                # either way, and reading six of them in five seconds during
                # a real dead-air incident told me the heal was retrying
                # when in fact it was refusing every time. A watchdog that
                # misreports is worse than no watchdog.
                self._maybe_schedule_auto_continue(session, FrameDirection.DOWNSTREAM)
                if self._pending_auto_continue is not None:
                    logger.warning(
                        f"[{self._visitor_id}] auto-continue chain stalled at step "
                        f"{session.walkthrough_step} — rescheduled"
                    )
                else:
                    blocker = (
                        "pending fragment" if self._pending_fragment_text
                        else "pending interruption" if self._pending_interruption_text
                        else "awaiting answer" if session.walkthrough_awaiting_answer
                        else "user stopped" if session.walkthrough_user_stopped
                        else "unknown"
                    )
                    logger.warning(
                        f"[{self._visitor_id}] auto-continue chain stalled at step "
                        f"{session.walkthrough_step} and could NOT be rescheduled "
                        f"(blocked by: {blocker}) — the tour is silent until this clears"
                    )
        except asyncio.CancelledError:
            pass

    async def _auto_continue_after_pause(self, session, direction: FrameDirection) -> None:
        # Counted here, not at schedule time: a beat cancelled by a barge-in
        # never reaches the prospect's ears, and charging it against the budget
        # would cut the tour short for something that never happened.
        self._consecutive_auto_beats += 1
        try:
            # Wait for the beat that was playing when this got scheduled to
            # genuinely finish before even starting the pause countdown.
            # _maybe_schedule_auto_continue fires right as that beat's own
            # turn wraps up, but its audio can still legitimately be playing
            # for several more seconds (a long last sentence) — a flat
            # AUTO_CONTINUE_PAUSE_SECS sleep alone would then land while
            # _bot_speaking was still true, bail immediately below, and
            # leave nothing scheduled until _watch_auto_continue_stall
            # rescued it seconds later. Confirmed live: this was happening
            # on every beat of a multi-part step, not as a rare fallback.
            # Bounded the same way _speak_without_activity_bump/
            # _speak_hand_raise_handoff already wait on this same event —
            # if it's somehow never set, the bail check right below still
            # catches it exactly as before this change.
            try:
                await asyncio.wait_for(self._speech_finished.wait(), timeout=AUTO_CONTINUE_SPEECH_WAIT_TIMEOUT_SECS)
            except asyncio.TimeoutError:
                pass
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
        # Re-checked at the last possible moment, not only at schedule time:
        # a stop can land during the pause countdown, after this beat was
        # already queued.
        if get_session(self._visitor_id).walkthrough_user_stopped:
            logger.info(f"[{self._visitor_id}] beat cancelled — prospect asked to stop")
            return
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
        # Answered — the burst is over, so the next one starts impatient
        # again rather than inheriting a stretched window.
        self._burst_fragments = 0
        self._begin_spoken_tracking()
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

            self._amend_interrupted_turn(session, result)

            if self._hand_raised and not self._hand_ack_sent:
                await self._speak_hand_raise_handoff(direction)

            await self._advance_after_turn(session, direction)
        finally:
            self._turn_in_progress = False
            # In the finally so a turn that ends by raising, or by being
            # interrupted, still reports. A latency record that only existed
            # for turns that went well would flatter every average we take.
            self._telemetry_close()

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
        if action == EXAMPLE_GALLERY_ACTION:
            # The spoken reply already explains the sandbox/gallery framing
            # (see instruction 13) — this is the one place the actual link
            # lands, since a spoken URL isn't something anyone can click or
            # copy. Fired alongside the action, not gated on the reply, so
            # it lands even if this turn's reply itself needed the
            # _maybe_backfill_reply path above.
            asyncio.create_task(
                self._report_chat_message(f"Here's the link to book a live platform showcase with a human rep: {BOOKING_LINK_URL}")
            )

    async def _report_chat_message(self, text: str) -> None:
        """Pushes a message straight into Meeting Mode's chat panel,
        unconditionally tagged source="chat" regardless of
        _current_reply_source — for agent-initiated content (like the
        example-gallery's booking link) that isn't a reply to anything
        typed, but still needs to land in the panel rather than only being
        spoken (see get_voice_reply in server.py — the chat panel filters
        strictly on source=="chat")."""
        try:
            async with aiohttp.ClientSession() as http:
                await http.post(
                    f"{REST_API_URL}/internal/voice-reply",
                    json={"visitorId": self._visitor_id, "reply": text, "source": "chat"},
                    timeout=aiohttp.ClientTimeout(total=3),
                )
        except Exception:
            logger.exception(f"Failed to report chat message for visitor {self._visitor_id}")

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
        # Deliberately does NOT set walkthrough_awaiting_answer any more.
        # It used to, which welded two unrelated things together: a
        # hand-raise that fired without the visitor meaning it (stale server
        # state, a double poll) spoke this line AND froze the tour
        # permanently, because the latch's only exit is the model
        # volunteering resume_walkthrough. Confirmed live: three of these in
        # one call with no user input, each one killing the tour until the
        # prospect gave up and shouted.
        #
        # If they really did raise their hand, their actual question arrives
        # as a normal transcript within seconds and pauses the tour through
        # the ordinary path. If they didn't, nothing is stuck.
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

    async def _poll_paused(self) -> None:
        """Watches the pause mailbox and turns a button press into silence.

        Separate loop from _poll_hand_raise because the two mean opposite
        things about who holds the floor. A raised hand is a request that
        waits for a sentence boundary; pause is the visitor taking the floor
        immediately, which is the whole reason it exists — you cannot stop a
        human rep mid-sentence, and being able to stop this one is the
        advantage of the format.
        """
        try:
            async with aiohttp.ClientSession() as http:
                while True:
                    await asyncio.sleep(PAUSE_POLL_INTERVAL_SECS)
                    try:
                        async with http.get(
                            f"{REST_API_URL}/internal/paused/{self._visitor_id}",
                            timeout=aiohttp.ClientTimeout(total=3),
                        ) as resp:
                            paused = bool((await resp.json()).get("paused"))
                    except Exception:
                        logger.exception(f"Failed to poll pause for visitor {self._visitor_id}")
                        continue

                    if paused == self._paused:
                        continue

                    if paused:
                        await self._enter_pause()
                    else:
                        await self._leave_pause()
        except asyncio.CancelledError:
            pass

    async def _enter_pause(self) -> None:
        """Stop talking now; keep the place."""
        self._paused = True
        # Whatever hasn't been said yet is what play will resume from. Read
        # before the interruption, since that clears the speaking state.
        self._paused_remainder = self._unspoken_remainder
        # Cuts audio in ~5ms — same path a real barge-in uses.
        await self.broadcast_interruption()
        # Nothing may queue a walkthrough beat behind a pause.
        self._cancel_pending_auto_continue()
        logger.info(
            f"[{self._visitor_id}] PAUSED by the visitor"
            + (f" (holding {len(self._paused_remainder or '')} chars to resume)"
               if self._paused_remainder else "")
        )

    async def _leave_pause(self) -> None:
        """Play. Give them the first move, then pick the thread back up."""
        self._paused = False
        logger.info(f"[{self._visitor_id}] RESUMED by the visitor")

        # They almost certainly pressed play because they are about to talk.
        # Wait, and if they do, say nothing at all — the re-entry line would
        # be talking over the very person who just took the floor back.
        await asyncio.sleep(RESUME_GRACE_SECS)
        if self._paused or self._user_speaking or self._turn_in_progress:
            self._paused_remainder = None
            return
        if self._pending_fragment_text or self._pending_interruption_text:
            self._paused_remainder = None
            return

        remainder = self._paused_remainder
        self._paused_remainder = None
        # A short marker that the floor is coming back — the spoken
        # equivalent of looking up. Without it, audio simply reappearing
        # mid-thought is jarring.
        await self._speak("Okay — picking up where we left off.", FrameDirection.DOWNSTREAM)
        if remainder:
            await self._speak(remainder, FrameDirection.DOWNSTREAM)

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
            # Accumulates for the same reason the voice path does (see
            # queue_frame): two messages typed while one beat is in flight
            # are two things the prospect said, not a race for one slot.
            if self._pending_interruption_text:
                self._pending_interruption_text = f"{self._pending_interruption_text} {text}".strip()
                if self._pending_interruption_since is None:
                    self._pending_interruption_since = time.monotonic()
            else:
                self._pending_interruption_text = text
                if self._pending_interruption_since is None:
                    self._pending_interruption_since = time.monotonic()
            self._pending_interruption_source = "chat"
            # Typed text is proof-positive of intent — even more so than a
            # transcript, since there's no chance it was noise. Same
            # cancellation as the voice path.
            self._interrupted_at = None
            self._interruption_quiet_since = None
            self._unspoken_remainder = None
            return
        # Genuinely idle — nothing else is going to pick this up, so handle
        # it directly, exactly like a transcript arriving while idle would.
        self._cancel_pending_auto_continue()
        self._cancel_prefetch()
        await self._handle_real_turn(text, direction, source="chat")

    def seconds_since_activity(self) -> float:
        """Read by bot.py's idle watcher (see run_bot) to drive both the
        15s check-in and the final farewell. Reads _last_activity —
        deliberately the SAME clock _watch_auto_continue_stall uses, so a
        visitor silently listening to an active, still-progressing
        walkthrough is never mistaken for an abandoned call (see
        _last_activity's docstring in __init__)."""
        return time.monotonic() - self._last_activity

    def last_activity_timestamp(self) -> float:
        """The raw monotonic timestamp behind seconds_since_activity(),
        read by bot.py's idle watcher specifically to detect a genuine
        reset even if one happens while the watcher itself is blocked
        inside its own await agent.speak_idle_checkin() call. Comparing
        the DERIVED seconds-since-activity value across polls (as an
        earlier version did) is unreliable for this: an automated stress
        test caught a visitor speaking while a check-in was still being
        spoken failing to re-arm the next streak at all, because by the
        time the watcher's loop resumed and took its next poll, enough
        wall-clock time had also passed that the elapsed-seconds value
        never looked like it had dropped, even though a real reset had
        happened moments earlier. Comparing this raw timestamp for
        (in)equality instead is immune to that — any genuine reset changes
        the value itself, regardless of how long the watcher was blocked."""
        return self._last_activity

    def is_bot_speaking(self) -> bool:
        """Also read by bot.py's idle watcher, to know when a farewell it
        asked for has actually finished playing before it tears down the
        call — see speak_idle_farewell."""
        return self._bot_speaking

    async def _speak_without_activity_bump(self, text: str) -> None:
        """Like _speak, but holds _suppress_activity_bump across this
        utterance's ENTIRE real playback, not just the _speak() call
        itself — _speak() only pushes frames and returns almost instantly;
        the real BotStartedSpeakingFrame this causes doesn't land until
        Cartesia actually starts playing the audio, well after that. An
        earlier version cleared the guard right after _speak() returned
        and was already off by the time that frame showed up, so every
        check-in silently bumped _last_activity anyway and reset its own
        countdown (confirmed live: the 15s nudge re-firing every ~15-30s,
        the call never reaching the real farewell).

        Waits on _speech_finished (the same asyncio.Event
        BotStartedSpeakingFrame/BotStoppedSpeakingFrame already
        clear/set — see __init__) rather than polling _bot_speaking on a
        timer — a polling version of this was tried first (checking every
        0.1s) and has its own race: an automated stress test caught it
        clearing the utterance's own start+stop cycle inside a single
        0.1s gap between polls, so the "did it start yet" loop never
        observed True at all and burned its full ~5s timeout for nothing
        on every single check-in. Waiting on the event instead has no
        polling interval to be faster than, so it can't miss a transition
        regardless of how quick the utterance is. Cleared right before
        speaking so this is definitely OUR utterance's own completion,
        not a stale set() left over from whatever spoke immediately
        before it. Used only by speak_idle_checkin/speak_idle_farewell,
        the two utterances that must never reset the clock they're read
        against."""
        self._suppress_activity_bump = True
        try:
            self._speech_finished.clear()
            await self._speak(text, FrameDirection.DOWNSTREAM)
            try:
                await asyncio.wait_for(self._speech_finished.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                pass  # TTS genuinely never started/stopped — don't hang the idle watcher forever
        finally:
            self._suppress_activity_bump = False

    async def speak_idle_checkin(self) -> None:
        """Called by bot.py's idle watcher the first time total idle time
        crosses IDLE_CHECKIN_THRESHOLD_SECS — one nudge partway through a
        silence, the way a real rep would naturally break it instead of
        saying nothing until the full IDLE_TIMEOUT_SECS farewell. Picks a
        named/unnamed variant based on whether SessionState.prospect_name
        is known yet, and randomly between phrasings so repeated calls
        don't all sound identical."""
        name = get_session(self._visitor_id).prospect_name
        variants = IDLE_CHECKIN_MESSAGES["named"] if name else IDLE_CHECKIN_MESSAGES["unnamed"]
        message = random.choice(variants).format(name=name)
        self._current_reply_source = "voice"
        # Persisted like any other agent turn. These are spoken by code, never
        # through _finalize_turn, so without this they were genuinely audible
        # to the prospect yet completely absent from the transcript DB and the
        # chat panel — a real session review showed four of these firing in
        # the raw pipeline log while the 46-turn transcript contained none of
        # them, which made the whole "is it nudging too early?" question
        # impossible to answer from the transcript alone.
        session = get_session(self._visitor_id)
        if session.visitor_id:
            gate_log.append_transcript_turn(session.visitor_id, "agent", message)
        asyncio.create_task(self._report_reply(message))
        await self._speak_without_activity_bump(message)

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
        # Same reasoning as speak_idle_checkin above — a call that ended with
        # this goodbye should show it in the transcript, not just stop.
        session = get_session(self._visitor_id)
        if session.visitor_id:
            gate_log.append_transcript_turn(session.visitor_id, "agent", farewell)
        asyncio.create_task(self._report_reply(farewell))
        await self._speak_without_activity_bump(farewell)

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
        if self._pending_fragment_watch_task is not None:
            self._pending_fragment_watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pending_fragment_watch_task
        # This one was missing, which is why a call that ended at 02:12 was
        # still polling :8787 an hour later and threw ConnectionRefused all
        # over the log the moment the REST server restarted under it. At
        # PAUSE_POLL_INTERVAL_SECS = 0.12 that is ~8 requests a second, per
        # finished call, until the process dies. Added with the pause feature
        # and not added here — the same omission the pause bug itself was.
        if self._pause_poll_task is not None:
            self._pause_poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pause_poll_task
        if self._recorder is not None:
            # save() swallows its own failures — a research capture must never
            # be able to break the hang-up path.
            self._recorder.save()
            self._recorder = None
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

    def __init__(self, agent: Optional["AgentRuntimeProcessor"] = None):
        super().__init__()
        self._last_sent = 0.0
        # Optional back-reference so the first audio frame of a turn can be
        # timestamped. This processor sits after TTS and handles the real
        # audio bytes, so it is the only place in the pipeline that knows when
        # sound genuinely starts — which is what makes acoustic_ttfa_ms a
        # measurement rather than an estimate.
        self._agent = agent

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, TTSAudioRawFrame):
            now = time.monotonic()
            if self._agent is not None:
                tel = self._agent._telemetry
                if tel is not None:
                    tel.mark("t_first_output_audio")
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
