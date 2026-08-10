"""Durable log of every visitor-gate submission (see server.py's
/api/visitor/gate) — name, company, and work email captured before someone
reaches /demo/dashboard or /demo/meet, plus every blocked personal-email
attempt. This is the only thing in the app that survives a restart; it's
deliberately separate from SessionState (context/store.py), which stays
exactly what it always was — in-memory, per-call conversation memory for the
live agent, not identity/audit history.

A single append-only table rather than a separate "visitors" table kept in
sync with a "sessions" table: "is this email known" and the admin panel's two
views are just queries over this one log, so there's nothing to keep
consistent across two writes.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, List, Optional, TypedDict

DB_PATH = os.path.join(os.path.dirname(__file__), "app.db")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Called automatically at import time (see bottom of this file) — safe
    to call repeatedly (CREATE TABLE IF NOT EXISTS). Runs in both backend
    processes (server.py and, via agent/runtime.py, bot.py's voice
    pipeline), since either one could be the first to actually write here
    and there's no guaranteed startup order between them."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gate_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_id TEXT NOT NULL,
                email TEXT NOT NULL,
                name TEXT,
                company TEXT,
                path TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gate_attempts_email ON gate_attempts(email)")
        # Every turn of every conversation (chat or voice — both go through
        # the same run_turn(), see agent/runtime.py), keyed by visitor_id so
        # it can be joined back to the gate_attempts row for that session.
        # Written directly from both backend processes (server.py for
        # Product Mode's /chat, bot.py for the voice pipeline) — same file,
        # sqlite's own locking handles the concurrent writers.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS transcript_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_id TEXT NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_transcript_turns_visitor ON transcript_turns(visitor_id)")


class VisitorLookup(TypedDict):
    name: str
    company: str


def record_attempt(
    visitor_id: str,
    email: str,
    name: Optional[str],
    company: Optional[str],
    path: str,
    status: str,
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO gate_attempts (visitor_id, email, name, company, path, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (visitor_id, email.strip().lower(), name, company, path, status, datetime.now(timezone.utc).isoformat()),
        )


def lookup_by_email(email: str) -> Optional[VisitorLookup]:
    """Most recent *allowed* attempt for this email — what lets the gate form
    skip straight to a Continue button for a returning visitor instead of
    asking for their name/company again."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT name, company FROM gate_attempts
            WHERE email = ? AND status = 'allowed'
            ORDER BY created_at DESC LIMIT 1
            """,
            (email.strip().lower(),),
        ).fetchone()
    if not row or not row["name"] or not row["company"]:
        return None
    return {"name": row["name"], "company": row["company"]}


def list_attempts(limit: int = 200, offset: int = 0) -> List[dict]:
    """Raw log, newest first — the admin panel's "Attempts" tab, including
    blocked personal-email rows."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, visitor_id, email, name, company, path, status, created_at
            FROM gate_attempts ORDER BY created_at DESC LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def list_visitors_summary() -> List[dict]:
    """One row per email — the admin panel's "Visitors" tab. Paths tried and
    session count come from every attempt (allowed or blocked) under that
    email; name/company shown are from the most recent *allowed* attempt,
    since a blocked attempt may have no name/company at all (see the
    email-first gate flow — blocked happens before those fields are shown)."""
    with _connect() as conn:
        emails = [r["email"] for r in conn.execute("SELECT DISTINCT email FROM gate_attempts").fetchall()]
        summaries = []
        for email in emails:
            rows = conn.execute(
                "SELECT * FROM gate_attempts WHERE email = ? ORDER BY created_at ASC",
                (email,),
            ).fetchall()
            latest_allowed = next((r for r in reversed(rows) if r["status"] == "allowed"), None)
            summaries.append(
                {
                    "email": email,
                    "name": latest_allowed["name"] if latest_allowed else None,
                    "company": latest_allowed["company"] if latest_allowed else None,
                    "first_seen_at": rows[0]["created_at"],
                    "last_seen_at": rows[-1]["created_at"],
                    "session_count": len(rows),
                    "paths_tried": sorted({r["path"] for r in rows}),
                    "ever_blocked": any(r["status"] != "allowed" for r in rows),
                }
            )
    summaries.sort(key=lambda s: s["last_seen_at"], reverse=True)
    return summaries


def get_visitor_detail(email: str) -> Optional[dict]:
    """Everything the admin panel's visitor detail view needs: the header
    (name/company/first-last seen) plus every individual session (gate
    attempt) under this email — each session's own visitor_id is what
    list_transcript() below is keyed on, since a returning visitor gets a
    fresh visitor_id every session (see frontend/src/lib/session.ts)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM gate_attempts WHERE email = ? ORDER BY created_at DESC",
            (email.strip().lower(),),
        ).fetchall()
    if not rows:
        return None
    latest_allowed = next((r for r in rows if r["status"] == "allowed"), None)
    return {
        "email": email.strip().lower(),
        "name": latest_allowed["name"] if latest_allowed else None,
        "company": latest_allowed["company"] if latest_allowed else None,
        "first_seen_at": rows[-1]["created_at"],
        "last_seen_at": rows[0]["created_at"],
        "sessions": [
            {
                "id": r["id"],
                "visitor_id": r["visitor_id"],
                "path": r["path"],
                "status": r["status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
    }


def append_transcript_turn(visitor_id: str, role: str, text: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO transcript_turns (visitor_id, role, text, created_at) VALUES (?, ?, ?, ?)",
            (visitor_id, role, text, datetime.now(timezone.utc).isoformat()),
        )


def list_transcript(visitor_id: str) -> List[dict]:
    """Oldest first — read top to bottom like an actual conversation, unlike
    the gate/attempts logs above which are newest-first audit trails."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, text, created_at FROM transcript_turns WHERE visitor_id = ? ORDER BY created_at ASC",
            (visitor_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    """The admin dashboard's stat cards — deliberately just a handful of
    numbers that actually answer "how is the demo being used", not a
    kitchen-sink analytics dump."""
    with _connect() as conn:
        total_visitors = conn.execute("SELECT COUNT(DISTINCT email) FROM gate_attempts").fetchone()[0]
        total_sessions = conn.execute("SELECT COUNT(*) FROM gate_attempts WHERE status = 'allowed'").fetchone()[0]
        blocked_attempts = conn.execute("SELECT COUNT(*) FROM gate_attempts WHERE status != 'allowed'").fetchone()[0]
        dashboard_sessions = conn.execute(
            "SELECT COUNT(*) FROM gate_attempts WHERE status = 'allowed' AND path = 'dashboard'"
        ).fetchone()[0]
        meet_sessions = conn.execute(
            "SELECT COUNT(*) FROM gate_attempts WHERE status = 'allowed' AND path = 'meet'"
        ).fetchone()[0]
    recent = list_visitors_summary()[:5]
    return {
        "total_visitors": total_visitors,
        "total_sessions": total_sessions,
        "blocked_attempts": blocked_attempts,
        "dashboard_sessions": dashboard_sessions,
        "meet_sessions": meet_sessions,
        "recent_visitors": recent,
    }


init_db()
