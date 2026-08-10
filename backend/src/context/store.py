import time
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
    # Captured from Meeting Mode's pre-join screen (see server.py's
    # /api/session/start) — the company name and work email the visitor gave
    # before the call even started. Real MEDDIC data points from minute one,
    # not something the agent has to go ask for.
    company: Optional[str] = None
    work_email: Optional[str] = None
    # MEDDIC qualification, captured opportunistically over the course of the
    # call (see runtime.py's tool fields of the same names) — each one set
    # once, the first time it genuinely comes up, then left alone so the
    # agent never re-asks something it already knows. Mirrors the
    # prospect_name pattern above, just for six fields instead of one.
    meddic_metrics: Optional[str] = None
    meddic_economic_buyer: Optional[str] = None
    meddic_decision_criteria: Optional[str] = None
    meddic_decision_process: Optional[str] = None
    meddic_pain: Optional[str] = None
    meddic_champion: Optional[str] = None
    # Wall-clock start of this session (monotonic, not calendar time) — lets
    # the prompt tell the agent how long the call has actually been running,
    # so it can pace itself toward the ~10 minute target instead of pacing
    # blind.
    started_at: float = field(default_factory=time.monotonic)
    # The same id this session is keyed by in _sessions below — kept on the
    # object itself (not just as the dict key) so run_turn() can persist each
    # turn to the durable transcript log (see data/gate_log.py) without
    # needing it threaded through as a separate parameter everywhere.
    visitor_id: Optional[str] = None


_sessions: Dict[str, SessionState] = {}


def get_session(visitor_id: str) -> SessionState:
    session = _sessions.get(visitor_id)
    if session is None:
        session = SessionState(history=[HistoryEntry(role="agent", text=OPENING_GREETING)], visitor_id=visitor_id)
        _sessions[visitor_id] = session
    return session


def start_session(
    visitor_id: str,
    prospect_name: Optional[str] = None,
    company: Optional[str] = None,
    work_email: Optional[str] = None,
) -> SessionState:
    """Explicitly (re)starts a session for visitor_id — called once, right
    when the visitor picks a name on Meeting Mode's pre-join screen, before
    the voice connection is made. Unlike get_session, this always creates a
    fresh session (overwriting any existing one) rather than only creating
    on first-ever contact: visitor_id persists in the browser's sessionStorage
    across visits, so without this a repeat visitor (or a dev re-testing the
    same browser tab) would silently resume a stale conversation instead of
    starting the new call they just asked for."""
    session = SessionState(
        history=[HistoryEntry(role="agent", text=build_greeting(prospect_name))],
        prospect_name=prospect_name,
        company=company,
        work_email=work_email,
        visitor_id=visitor_id,
    )
    _sessions[visitor_id] = session
    return session
