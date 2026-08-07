import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from .agent.runtime import run_turn
from .context.store import get_session, start_session
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
_pending_hand_raises: Dict[str, bool] = {}


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


@app.post("/api/session/start")
def start_session_endpoint(body: StartSessionRequest):
    """Called once by Meeting Mode's pre-join screen, right when the visitor
    picks a name — before the voice connection is made. Seeds a fresh
    session with a greeting personalized to that name, so the voice
    pipeline's opening line (see AgentRuntimeProcessor._greet) addresses
    them by it from the very first word."""
    name = body.name.strip() if body.name else None
    start_session(body.visitorId, name)
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


@app.post("/api/hand-raise/{visitor_id}")
def raise_hand(visitor_id: str):
    """Called by the frontend when the prospect clicks the hand-raise button
    in Meeting Mode — the non-interrupting alternative to talking over the
    agent."""
    _pending_hand_raises[visitor_id] = True
    return {"ok": True}


@app.get("/internal/hand-raise/{visitor_id}")
def get_hand_raise(visitor_id: str):
    """Polled by the voice process. Returns and clears the pending flag, so
    it's handled exactly once."""
    return {"raised": _pending_hand_raises.pop(visitor_id, False)}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8787))
    uvicorn.run("src.server:app", host="0.0.0.0", port=port, reload=True)
