import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

load_dotenv()

from .agent.runtime import run_turn
from .context.store import get_session
from .data.dashboard import dashboard_data
from .data.analytics import analytics_overview
from .data.brand_kit import brand_kit_data

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

brand_kit_state = dict(brand_kit_data)


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


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8787))
    uvicorn.run("src.server:app", host="0.0.0.0", port=port, reload=True)
