from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class HistoryEntry:
    role: str
    text: str


@dataclass
class SessionState:
    history: List[HistoryEntry] = field(default_factory=list)
    current_page: str = "dashboard"
    # Set by the voice pipeline when the visitor started talking while Emma
    # was still (estimated to be) mid-reply — read once by the next run_turn
    # call so the agent knows its last explanation may have landed only
    # partially, then cleared.
    was_interrupted: bool = False


_sessions: Dict[str, SessionState] = {}


def get_session(visitor_id: str) -> SessionState:
    session = _sessions.get(visitor_id)
    if session is None:
        session = SessionState()
        _sessions[visitor_id] = session
    return session
