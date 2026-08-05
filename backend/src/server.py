import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from .agent.runtime import run_turn
from .context.store import get_session
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


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8787))
    uvicorn.run("src.server:app", host="0.0.0.0", port=port, reload=True)
