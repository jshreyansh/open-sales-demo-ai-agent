from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..persona import AGENT_NAME

# Spoken/shown the instant a visitor joins — before the LLM is ever called —
# so the very first thing they hear is one short self-intro, not silence or
# a feature dump. Deliberately just an intro + open question, not a
# discovery interview — if the prospect volunteers their name, role, or
# company at any point, the model picks up on it opportunistically (see
# runtime.py's "prospect_name" tool field) rather than this being scripted
# to ask for it. The voice pipeline speaks this deterministically (see
# AgentRuntimeProcessor._greet, triggered off the pipeline's own StartFrame)
# and the frontend shows the identical text as the first chat bubble;
# seeding it into history here means run_turn's very next call already sees
# it as the opening turn.
OPENING_GREETING = (
    f"Hi, I'm {AGENT_NAME}, sales rep at SwishX — here to walk you through the demo. "
    "Feel free to raise your hand anytime if something comes to mind — what can I help you with?"
)


def build_greeting(prospect_name: Optional[str] = None) -> str:
    """Personalized variant of OPENING_GREETING when a name is already known
    up front (Meeting Mode's pre-join screen — see start_session below) —
    falls back to the generic version otherwise (e.g. Product Mode's chat,
    which has no equivalent pre-join step)."""
    if not prospect_name:
        return OPENING_GREETING
    return (
        f"Hi {prospect_name}, I'm {AGENT_NAME}, sales rep at SwishX — here to walk you through the demo. "
        "Feel free to raise your hand anytime if something comes to mind — what can I help you with?"
    )


@dataclass
class HistoryEntry:
    role: str
    text: str


@dataclass
class SessionState:
    history: List[HistoryEntry] = field(default_factory=list)
    current_page: str = "dashboard"
    # Set by the voice pipeline when the visitor started talking while the
    # agent was actually still speaking (tracked via pipecat's own
    # BotStartedSpeakingFrame/BotStoppedSpeakingFrame) — read once by the
    # next run_turn call so the agent knows its last explanation may have
    # landed only partially, then cleared.
    was_interrupted: bool = False
    # Captured once the prospect introduces themselves in response to
    # OPENING_GREETING (see runtime.py's "prospect_name" tool field) — kept
    # for the rest of the session so the agent can use it naturally later
    # (e.g. a tag-question close like "Sound good, {name}?"), not just in
    # the opening acknowledgment.
    prospect_name: Optional[str] = None


_sessions: Dict[str, SessionState] = {}


def get_session(visitor_id: str) -> SessionState:
    session = _sessions.get(visitor_id)
    if session is None:
        session = SessionState(history=[HistoryEntry(role="agent", text=OPENING_GREETING)])
        _sessions[visitor_id] = session
    return session


def start_session(visitor_id: str, prospect_name: Optional[str] = None) -> SessionState:
    """Explicitly (re)starts a session for visitor_id — called once, right
    when the visitor picks a name on Meeting Mode's pre-join screen, before
    the voice connection is made. Unlike get_session, this always creates a
    fresh session (overwriting any existing one) rather than only creating
    on first-ever contact: visitor_id persists in the browser's localStorage
    across visits, so without this a repeat visitor (or a dev re-testing the
    same browser tab) would silently resume a stale conversation instead of
    starting the new call they just asked for."""
    session = SessionState(
        history=[HistoryEntry(role="agent", text=build_greeting(prospect_name))],
        prospect_name=prospect_name,
    )
    _sessions[visitor_id] = session
    return session
