import os
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from .agent.runtime import run_turn
from .context.store import get_session, start_session
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
_pending_voice_actions: Dict[str, dict] = {}

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
_pending_voice_replies: Dict[str, List[str]] = {}

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

# Whole-app single-call gate: the voicebot (bot.py) is one process running
# every concurrent call's VAD/STT/TTS on one event loop, with no worker pool
# and no autoscaling behind it — a second simultaneous caller doesn't get a
# clean "no capacity" error, they just silently degrade the first caller's
# call too. This makes that real limit explicit instead of letting it
# happen invisibly. None means the line is free.
_active_call: Optional[Dict[str, Any]] = None
# Safety net only, not the normal release path — the normal path is bot.py
# calling /api/voice-lock/release from on_client_disconnected the moment a
# call actually ends. This just self-heals a lock that got stuck because
# that never fired (e.g. the voice process crashed outright), without ever
# interrupting a call that's realistically still going.
_CALL_LOCK_TTL_SECS = 30 * 60


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
    return detail


@app.get("/api/admin/transcript/{visitor_id}")
def admin_transcript(visitor_id: str):
    return gate_log.list_transcript(visitor_id)


class VoiceLockRequest(BaseModel):
    visitorId: str


@app.post("/api/voice-lock/claim")
def claim_voice_lock(body: VoiceLockRequest):
    """Called right before connecting voice — both Meeting Mode's pre-join
    screen and Product Mode's Talk button go through useVoiceSession.connect(),
    which calls this first. Only one real call is supported at a time on
    this box today (see the module-level comment on _active_call); this is
    what actually enforces that instead of just hoping it doesn't happen."""
    global _active_call
    now = time.monotonic()
    if _active_call is not None:
        stale = (now - _active_call["claimed_at"]) > _CALL_LOCK_TTL_SECS
        same_visitor = _active_call["visitorId"] == body.visitorId
        if not stale and not same_visitor:
            return {"ok": False}
    _active_call = {"visitorId": body.visitorId, "claimed_at": now}
    return {"ok": True}


@app.post("/api/voice-lock/release")
def release_voice_lock(body: VoiceLockRequest):
    """Called by bot.py's on_client_disconnected the moment a call actually
    ends (the prompt, common-case release), and also by the frontend on an
    explicit hangup for good measure. Only releases if the caller actually
    holds the lock, so a stale/late release from a call that already lost
    the lock (e.g. to the TTL) can't accidentally kick out whoever's on it
    now."""
    global _active_call
    if _active_call is not None and _active_call["visitorId"] == body.visitorId:
        _active_call = None
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
    action for the frontend to pick up on its next poll."""
    _pending_voice_actions[body.visitorId] = body.action
    return {"ok": True}


@app.get("/api/voice-action/{visitor_id}")
def get_voice_action(visitor_id: str):
    """Polled by the frontend during an active voice call. Returns and
    clears the pending action, or {} if there isn't one."""
    return _pending_voice_actions.pop(visitor_id, {})


class VoiceReplyReport(BaseModel):
    visitorId: str
    reply: str


@app.post("/internal/voice-reply")
def report_voice_reply(body: VoiceReplyReport):
    """Called by the voice process to hand off a piece of spoken text (a
    lead_in, or a reply) so it can show up in the chat transcript as its own
    bubble."""
    _pending_voice_replies.setdefault(body.visitorId, []).append(body.reply)
    return {"ok": True}


@app.get("/api/voice-reply/{visitor_id}")
def get_voice_reply(visitor_id: str):
    """Polled by the frontend during an active voice call. Returns and
    clears the oldest pending reply text, or "" if there isn't one — one
    per poll, so a lead_in and its reply each land as separate bubbles."""
    queue = _pending_voice_replies.get(visitor_id)
    if not queue:
        return {"reply": ""}
    return {"reply": queue.pop(0)}


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
