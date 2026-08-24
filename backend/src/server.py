import os
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psutil
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

load_dotenv()

from .agent.runtime import generate_call_summary, run_turn
from .context.store import get_session, start_session
from .data import email as email_service
from .data import gate_log
from .data.dashboard import dashboard_data
from .data.analytics import analytics_overview
from .data.brand_kit import brand_kit_data
from .data.approvals import approvals_data

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

brand_kit_state = dict(brand_kit_data)

# Pending UI actions reported by the voice pipeline (a separate process,
# src/voice/bot.py), keyed by visitor_id. The frontend polls this while a
# voice call is active — same {page, component, method} shape the chat's
# /chat response already uses.
_pending_voice_actions: Dict[str, List[dict]] = {}

# Same idea for the reply text itself. Pipecat's own bot-transcription RTVI
# event depends on pushing an LLMTextFrame through the pipeline; the voice
# process pushes a plain TextFrame instead (run_turn already returns the
# complete reply, there's no real streaming LLM to bracket), so that event
# never fires. Reporting the text through this side-channel — identical
# pattern to voice actions — is what actually gets it into the chat transcript.
#
# A queue, not a single slot: a turn with an action reports two texts in
# quick succession (the lead_in, then the reply) — a single dict slot would
# let the second POST silently clobber the first before a poll ever saw it.
# Each entry also carries which surface it answers ("voice" — narration,
# real spoken turns, hand-raise handoffs — or "chat" — a reply to a typed
# Meeting Mode message, see _pending_meeting_chat below) so the frontend's
# docked chat panel can show only the exchanges the visitor actually typed,
# not the whole call's narration, while every other existing consumer
# (ChatWidget's Product Mode Talk view) keeps working unchanged since it
# never looks at this field.
_pending_voice_replies: Dict[str, List[dict]] = {}

# The reverse direction of _pending_voice_replies, for typed input instead
# of spoken: Meeting Mode's chat panel posts here, and the voice process (a
# separate process on :7860) polls it — same reasoning as
# _hand_raise_state below, since the two processes don't share memory. A
# real queue, not a single slot, for the same reason _pending_voice_actions
# already is: someone can type and send a second message before the voice
# process's poll has drained the first.
_pending_meeting_chat: Dict[str, List[str]] = {}

# The reverse direction of the two mailboxes above: the frontend's hand-raise
# button posts here, and the voice process (a separate process on :7860)
# polls it — that's how a click in Meeting Mode becomes something the live
# call actually reacts to, since the two processes don't share memory.
#
# Unlike the mailboxes above, this is real persistent state, not a one-shot
# flag that gets consumed on first read: raising and lowering the hand are
# both explicit visitor actions (see MeetingShell's toggle button), and the
# voice process itself tracks whether it has already acknowledged the
# current raise — see agent_processor.py's _hand_ack_sent. Nothing here
# auto-expires a raise; only a visitor clicking the button again does.
_hand_raise_state: Dict[str, bool] = {}

# Same mailbox shape for the pause button. Distinct from hand-raise on
# purpose: a raised hand means "I have a question, finish your sentence and
# come to me", whereas pause means "stop, right now, and don't do anything
# until I say" — the visitor is taking the floor rather than queuing for it.
_paused_state: Dict[str, bool] = {}

# Admission gate for the voicebot (bot.py): one process running every
# concurrent call's VAD/STT/TTS on one event loop, with no worker pool and
# no autoscaling behind it. Two independent limits, both enforced in
# claim_voice_lock below, mirroring how real voice-agent platforms admit
# work (see the concurrent-calls plan): a hard ceiling on simultaneous
# calls, and an adaptive CPU-load check (LiveKit's own load_fnc/
# load_threshold pattern) that refuses a new call above a safe load even
# if the ceiling hasn't been hit yet — because a flat number picked in the
# abstract has no relationship to what this box can actually sustain.
# Keyed by visitorId (same per-visitor-dict shape as _hand_raise_state/
# _paused_state above) rather than a single slot, so more than one call
# can be admitted at once.
_active_calls: Dict[str, Dict[str, Any]] = {}
# Kept at 1 until Phase 3's synthetic load test + staged real-call
# verification (see the plan) validates a higher number on THIS box —
# raising this is the actual "go live" switch for concurrent calls, not
# the code change itself.
_MAX_CONCURRENT_CALLS = 1
# Matches LiveKit's own default load_threshold — refuse new work once the
# box is already this loaded, tune from real Phase 3 measurements.
_CPU_LOAD_THRESHOLD_PCT = 70.0
# Safety net only, not the normal release path — the normal path is bot.py
# calling /api/voice-lock/release from on_client_disconnected the moment a
# call actually ends. This just self-heals a lock that got stuck because
# that never fired (e.g. the voice process crashed outright), without ever
# interrupting a call that's realistically still going.
_CALL_LOCK_TTL_SECS = 30 * 60

# cpu_percent(interval=None) is non-blocking but returns 0.0 (meaningless)
# on its very first call in a process — it measures the delta since the
# last call. Priming it once here at import time means the first real
# claim_voice_lock() call already gets a real reading instead of a
# spurious 0.0 that would never refuse anything.
psutil.cpu_percent(interval=None)


class ChatRequest(BaseModel):
    visitorId: Optional[str] = None
    message: Optional[str] = None
    currentPage: Optional[str] = None


@app.post("/chat")
def chat(body: ChatRequest):
    if not body.visitorId or not body.message:
        raise HTTPException(status_code=400, detail="visitorId and message are required")
    session = get_session(body.visitorId)
    if body.currentPage:
        session.current_page = body.currentPage
    return run_turn(body.message, session)


class StartSessionRequest(BaseModel):
    visitorId: str
    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None


@app.post("/api/session/start")
def start_session_endpoint(body: StartSessionRequest):
    """Called once by Meeting Mode's pre-join screen, right when the visitor
    fills in their name, company, and work email — before the voice
    connection is made. Seeds a fresh session with a greeting personalized
    to that name, so the voice pipeline's opening line (see
    AgentRuntimeProcessor._greet) addresses them by it from the very first
    word, and with company/email already on hand as the first real MEDDIC
    data point (see runtime.py's _company_note)."""
    name = body.name.strip() if body.name else None
    company = body.company.strip() if body.company else None
    email = body.email.strip() if body.email else None
    start_session(body.visitorId, name, company, email)
    return {"ok": True}


# --- Gate email verification -----------------------------------------------
#
# Sits in FRONT of the existing lookup/known/new steps, which are unchanged:
# a visitor proves the address is theirs, and only then does the gate go on to
# ask whether we already know them. Splitting it that way is deliberate —
# neither endpoint below ever says whether an email is on file, because
# answering that before verification turns the gate into a free "is this
# person a SwishX customer" oracle for anyone with a list of addresses.

_EMAIL_FORMAT_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _otp_error(status: int, code: str, message: str, **extra: Any) -> HTTPException:
    """Every failure below answers in the same shape — {code, message, ...} —
    so the gate form can switch on `code` for behaviour (start the resend
    countdown, clear the input) while showing `message` verbatim. Real status
    codes rather than a 200 carrying an error field: a send that didn't happen
    is not a successful request, and the difference matters to anything
    watching this endpoint from outside the browser."""
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


class OtpSendRequest(BaseModel):
    email: str


@app.post("/api/visitor/otp/send")
def send_otp(body: OtpSendRequest):
    """Issues a 6-digit code and emails it. Two separate limits apply, and
    they're doing different jobs: the 30-second cooldown stops a visitor
    double-tapping "Resend" and racing two codes against each other, while
    the 3-per-15-minutes cap is what stops this endpoint being used to mail
    someone repeatedly."""
    email = body.email.strip().lower()
    if not _EMAIL_FORMAT_RE.match(email):
        raise _otp_error(400, "invalid_email", "Enter a valid email address.")

    # The personal-domain rule (see frontend/src/lib/email.ts) stays where it
    # is — the form blocks those before it ever gets here, and the rate limit
    # below caps what a direct caller could do with one anyway. Duplicating
    # that domain list into a second place it could drift from is worse than
    # what it would buy.
    window = gate_log.recent_otp_sends(email, email_service.OTP_SEND_WINDOW_SECS)
    if window:
        since_last = (datetime.now(timezone.utc) - max(window)).total_seconds()
        if since_last < email_service.OTP_RESEND_COOLDOWN_SECS:
            wait = int(email_service.OTP_RESEND_COOLDOWN_SECS - since_last) + 1
            raise _otp_error(
                429,
                "cooldown",
                f"Hang on {wait} more second{'s' if wait != 1 else ''} before asking for another code.",
                retry_after=wait,
            )
    if len(window) >= email_service.OTP_MAX_SENDS_PER_WINDOW:
        minutes = email_service.OTP_SEND_WINDOW_SECS // 60
        raise _otp_error(
            429,
            "rate_limited",
            f"Too many codes requested. Try again in {minutes} minutes, or contact us directly.",
            retry_after=email_service.OTP_SEND_WINDOW_SECS,
        )

    # secrets, not random: this is the only thing standing between a stranger
    # and someone else's identity on the gate, and random's Mersenne Twister
    # is reconstructable from enough observed output.
    code = f"{secrets.randbelow(1_000_000):06d}"
    gate_log.burn_otp_codes(email)
    # Written before the send, not after, so a send that fails still counts
    # against the limits above — otherwise a caller could hammer Postmark
    # indefinitely as long as every attempt errored.
    gate_log.create_otp_code(email, code)

    try:
        email_service.send_otp_email(email, code)
    except email_service.EmailSendError as exc:
        logger.error(f"OTP send failed for {email}: {exc}")
        # Fails closed. The visitor does not continue, and nothing here hints
        # at whether the address is known — the message is about our send,
        # not about them.
        raise _otp_error(
            502,
            "send_failed",
            "We couldn't send your code just now. Please try again in a moment.",
        )

    return {
        "ok": True,
        "expires_in": email_service.OTP_TTL_SECS,
        "resend_after": email_service.OTP_RESEND_COOLDOWN_SECS,
    }


class OtpVerifyRequest(BaseModel):
    email: str
    code: str


@app.post("/api/visitor/otp/verify")
def verify_otp(body: OtpVerifyRequest):
    """Checks a code and, on success, consumes it. Success returns nothing but
    {"ok": true} — the frontend then continues into the existing lookup step
    exactly as it did before this endpoint existed."""
    email = body.email.strip().lower()
    submitted = body.code.strip()

    record = gate_log.get_active_otp(email)
    if record is None:
        raise _otp_error(400, "no_code", "That code is no longer valid. Request a new one.")

    try:
        issued_at = datetime.fromisoformat(record["created_at"])
    except ValueError:
        issued_at = datetime.now(timezone.utc)
    if (datetime.now(timezone.utc) - issued_at).total_seconds() > email_service.OTP_TTL_SECS:
        gate_log.consume_otp(record["id"])
        raise _otp_error(400, "expired", "That code has expired. Request a new one.")

    if record["attempts"] >= email_service.OTP_MAX_ATTEMPTS:
        gate_log.consume_otp(record["id"])
        raise _otp_error(400, "too_many_attempts", "Too many incorrect attempts. Request a new code.")

    # Counted before the comparison, so a wrong guess costs an attempt even if
    # the response never reaches the caller.
    attempts = gate_log.record_otp_attempt(record["id"])
    # compare_digest, not ==: string equality short-circuits on the first
    # differing character, which leaks how much of the code was right through
    # response timing.
    if not secrets.compare_digest(record["code"], submitted):
        remaining = max(0, email_service.OTP_MAX_ATTEMPTS - attempts)
        if remaining == 0:
            gate_log.consume_otp(record["id"])
            raise _otp_error(400, "too_many_attempts", "Too many incorrect attempts. Request a new code.")
        raise _otp_error(
            400,
            "invalid_code",
            f"That code isn't right. {remaining} attempt{'s' if remaining != 1 else ''} left.",
            attempts_left=remaining,
        )

    gate_log.consume_otp(record["id"])
    return {"ok": True}


class VisitorLookupRequest(BaseModel):
    email: str


@app.post("/api/visitor/lookup")
def lookup_visitor(body: VisitorLookupRequest):
    """Called by the shared gate form (PreJoinScreen and the dashboard gate)
    the moment a valid work email is entered — lets a returning visitor skip
    straight past the name/company fields instead of retyping what's already
    on file from a previous visit (see gate_log.lookup_by_email)."""
    result = gate_log.lookup_by_email(body.email)
    if result is None:
        return {"known": False}
    return {"known": True, **result}


class VisitorGateRequest(BaseModel):
    visitorId: str
    email: str
    name: Optional[str] = None
    company: Optional[str] = None
    path: str
    status: str


@app.post("/api/visitor/gate")
def report_visitor_gate(body: VisitorGateRequest):
    """Called once per gate submission — allowed or blocked — by the shared
    gate form. This is the actual write path for the admin panel's identity
    log; unlike everything else in this file, it's meant to persist across a
    restart (see gate_log.py)."""
    gate_log.record_attempt(body.visitorId, body.email, body.name, body.company, body.path, body.status)
    return {"ok": True}


@app.get("/api/admin/visitors")
def admin_list_visitors():
    return gate_log.list_visitors_summary()


@app.get("/api/admin/attempts")
def admin_list_attempts(limit: int = 200, offset: int = 0):
    return gate_log.list_attempts(limit, offset)


@app.get("/api/admin/stats")
def admin_stats():
    return gate_log.get_stats()


@app.get("/api/admin/visitors/{email}")
def admin_visitor_detail(email: str):
    detail = gate_log.get_visitor_detail(email)
    if detail is None:
        raise HTTPException(status_code=404, detail="No visitor with that email")
    # Each session's qualification profile (5 required KPI questions + 4
    # bonus MEDDIC fields, see agent/runtime.py's _QUAL_LABELS/_MEDDIC_LABELS)
    # keyed by that session's own visitor_id — same one list_transcript()
    # below is keyed on, since a returning visitor gets a fresh visitor_id
    # per session.
    for session in detail["sessions"]:
        session["qualification"] = gate_log.get_qualification_fields(session["visitor_id"])
    return detail


@app.get("/api/admin/transcript/{visitor_id}")
def admin_transcript(visitor_id: str):
    return gate_log.list_transcript(visitor_id)


@app.get("/api/admin/summary/{visitor_id}")
def admin_call_summary(visitor_id: str):
    """Cached AI call summary if one exists (normally already generated by
    bot.py's on_client_disconnected right when the call ended) — generated
    on-demand here as a fallback for the rare case nothing's cached yet
    (call still in progress, or background generation failed)."""
    summary = gate_log.get_call_summary(visitor_id)
    if summary is None:
        summary = generate_call_summary(visitor_id)
        if summary:
            gate_log.save_call_summary(visitor_id, summary)
    return {"summary": summary}


class VoiceLockRequest(BaseModel):
    visitorId: str


@app.post("/api/voice-lock/claim")
def claim_voice_lock(body: VoiceLockRequest):
    """Called right before connecting voice — both Meeting Mode's pre-join
    screen and Product Mode's Talk button go through useVoiceSession.connect(),
    which calls this first. Admission is gated two ways (see the module-level
    comment on _active_calls): a hard ceiling on simultaneous calls, and a
    CPU-load check so a new call isn't admitted onto a box that's already
    struggling, even under the ceiling. A visitor reclaiming a slot they
    already hold (a retry, a reconnect) always succeeds regardless of either
    check — this must behave identically to today's single-slot lock for
    that case, not get caught by a CPU spike."""
    global _active_calls
    now = time.monotonic()
    stale_cutoff = now - _CALL_LOCK_TTL_SECS
    _active_calls = {
        vid: call for vid, call in _active_calls.items() if call["claimed_at"] > stale_cutoff
    }

    if body.visitorId in _active_calls:
        _active_calls[body.visitorId] = {"claimed_at": now}
        return {"ok": True}

    if len(_active_calls) >= _MAX_CONCURRENT_CALLS:
        return {"ok": False}

    if psutil.cpu_percent(interval=None) > _CPU_LOAD_THRESHOLD_PCT:
        return {"ok": False}

    _active_calls[body.visitorId] = {"claimed_at": now}
    return {"ok": True}


@app.post("/api/voice-lock/release")
def release_voice_lock(body: VoiceLockRequest):
    """Called by bot.py's on_client_disconnected the moment a call actually
    ends (the prompt, common-case release), and also by the frontend on an
    explicit hangup for good measure. Only releases if the caller actually
    holds the lock, so a stale/late release from a call that already lost
    the lock (e.g. to the TTL) can't accidentally kick out whoever's on it
    now."""
    _active_calls.pop(body.visitorId, None)
    # Per-call scratch state dies with the call. _hand_raise_state is keyed
    # by visitor_id, and a visitor_id is STABLE across calls — so a hand left
    # raised when a call ended was still raised when the same person dialled
    # back in, firing a hand-raise handoff seconds into the new call with
    # nobody having touched the button. Same for any typed message that was
    # queued but never delivered.
    _hand_raise_state.pop(body.visitorId, None)
    _paused_state.pop(body.visitorId, None)
    _pending_meeting_chat.pop(body.visitorId, None)
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/dashboard")
def get_dashboard():
    return dashboard_data


@app.get("/api/analytics/overview")
def get_analytics_overview():
    return analytics_overview


@app.get("/api/brand-kit")
def get_brand_kit():
    return brand_kit_state


@app.put("/api/brand-kit")
def put_brand_kit(body: dict):
    brand_kit_state.update(body)
    return brand_kit_state


@app.get("/api/approvals")
def get_approvals():
    return approvals_data


class VoiceActionReport(BaseModel):
    visitorId: str
    action: Dict[str, Any]


@app.post("/internal/voice-action")
def report_voice_action(body: VoiceActionReport):
    """Called by the voice process (src/voice/bot.py) to hand off a UI
    action for the frontend to pick up on its next poll. A per-visitor
    queue, not a single overwritable slot — the walkthrough can report a
    new action for a fresh beat well within the frontend's 800ms poll
    window (see useVoiceSession.ts), and a single slot silently lost
    whichever action hadn't been polled yet, which is exactly why the
    walkthrough's on-screen highlighting kept going dark mid-tour. Mirrors
    _pending_voice_replies' already-correct queue below."""
    _pending_voice_actions.setdefault(body.visitorId, []).append(body.action)
    return {"ok": True}


@app.get("/api/voice-action/{visitor_id}")
def get_voice_action(visitor_id: str):
    """Polled by the frontend during an active voice call. Returns and
    clears the oldest pending action, or {} if there isn't one — one per
    poll, same pattern as get_voice_reply below."""
    queue = _pending_voice_actions.get(visitor_id)
    if not queue:
        return {}
    return queue.pop(0)


class VoiceReplyReport(BaseModel):
    visitorId: str
    reply: str
    source: str = "voice"


@app.post("/internal/voice-reply")
def report_voice_reply(body: VoiceReplyReport):
    """Called by the voice process to hand off a piece of spoken text (a
    lead_in, or a reply) so it can show up in the chat transcript as its own
    bubble. `source` distinguishes ordinary narration/spoken turns ("voice")
    from a reply that specifically answers a typed Meeting Mode chat message
    ("chat") — see get_voice_reply."""
    _pending_voice_replies.setdefault(body.visitorId, []).append({"text": body.reply, "source": body.source})
    return {"ok": True}


@app.get("/api/voice-reply/{visitor_id}")
def get_voice_reply(visitor_id: str):
    """Polled by the frontend during an active voice call. Returns and
    clears the oldest pending reply, or an empty one if there isn't one —
    one per poll, so a lead_in and its reply each land as separate bubbles.
    Product Mode's ChatWidget only ever reads `.reply`, so this stays
    backward compatible for it; Meeting Mode's chat panel additionally
    filters on `.source == "chat"` so it only ever shows exchanges the
    visitor actually typed, not the whole call's narration."""
    queue = _pending_voice_replies.get(visitor_id)
    if not queue:
        return {"reply": "", "source": "voice"}
    item = queue.pop(0)
    return {"reply": item["text"], "source": item["source"]}


class MeetingChatRequest(BaseModel):
    message: str


@app.post("/api/meeting-chat/{visitor_id}")
def send_meeting_chat(visitor_id: str, body: MeetingChatRequest):
    """Called by Meeting Mode's chat panel when the visitor sends a typed
    message. Deliberately NOT routed through /chat above — /chat calls
    run_turn against a SessionState that lives in THIS process, but a live
    Meeting Mode call is being driven by the voice process on :7860 against
    its OWN SessionState object for the same visitor_id; the two are not the
    same object and share no history. Queuing here for the voice process's
    own poll (_poll_meeting_chat in agent_processor.py) to pick up is what
    lets a typed message actually reach the conversation the visitor is
    really having, exactly like hand-raise already does for a boolean
    signal — mirrored here for real text content instead."""
    _pending_meeting_chat.setdefault(visitor_id, []).append(body.message)
    return {"ok": True}


@app.get("/internal/meeting-chat/{visitor_id}")
def get_meeting_chat(visitor_id: str):
    """Polled by the voice process. Returns and clears the oldest pending
    typed message, or "" if there isn't one."""
    queue = _pending_meeting_chat.get(visitor_id)
    if not queue:
        return {"message": ""}
    return {"message": queue.pop(0)}


class HandRaiseRequest(BaseModel):
    raised: bool


@app.post("/api/hand-raise/{visitor_id}")
def set_hand_raise(visitor_id: str, body: HandRaiseRequest):
    """Called by the frontend's hand-raise button — a toggle, not a momentary
    press. Raising and lowering are both explicit clicks the visitor makes;
    the button itself decides when to unset this, nothing here times it out."""
    if body.raised:
        _hand_raise_state[visitor_id] = True
    else:
        _hand_raise_state.pop(visitor_id, None)
    return {"ok": True}


class PauseRequest(BaseModel):
    paused: bool


@app.post("/api/pause/{visitor_id}")
def set_paused(visitor_id: str, body: PauseRequest):
    """The play/pause control in the meeting's bottom bar.

    A real demo can't be stopped mid-sentence — that is precisely the
    advantage this format has over a human rep, so it gets a first-class
    control rather than being buried in the hand-raise flow. Hand-raise
    politely queues a question; this stops everything.
    """
    if body.paused:
        _paused_state[visitor_id] = True
    else:
        _paused_state.pop(visitor_id, None)
    return {"ok": True}


@app.get("/internal/paused/{visitor_id}")
def get_paused(visitor_id: str):
    """Polled by the voice process. Non-consuming, same as hand-raise: the
    voice process tracks for itself whether it has already acted on the
    current pause."""
    return {"paused": _paused_state.get(visitor_id, False)}


@app.get("/internal/hand-raise/{visitor_id}")
def get_hand_raise(visitor_id: str):
    """Polled by the voice process every second. Returns the current state
    without consuming it — the voice process tracks for itself whether it's
    already handed off for the current raise (see agent_processor.py's
    _hand_ack_sent), so polling the same "still raised" state repeatedly is
    expected and safe."""
    return {"raised": _hand_raise_state.get(visitor_id, False)}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8787))
    uvicorn.run("src.server:app", host="0.0.0.0", port=port, reload=True)
