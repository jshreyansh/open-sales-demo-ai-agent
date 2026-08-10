import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getAdminTranscript, getAdminVisitorDetail, type AdminVisitorDetail as Detail, type TranscriptTurn } from "../../lib/api";

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

// One session's transcript, fetched only once its row is expanded — most
// sessions won't be looked at, so there's no reason to pull every
// transcript up front just to render a list of dates.
function SessionTranscript({ visitorId }: { visitorId: string }) {
  const [turns, setTurns] = useState<TranscriptTurn[] | null>(null);

  useEffect(() => {
    getAdminTranscript(visitorId).then(setTurns);
  }, [visitorId]);

  if (!turns) return <div className="admin__loading">Loading transcript…</div>;
  if (turns.length === 0) return <div className="admin__empty">No conversation recorded for this session.</div>;

  return (
    <div className="admin-transcript">
      {turns.map((t, i) => (
        <div key={i} className={`admin-transcript__turn admin-transcript__turn--${t.role}`}>
          <span className="admin-transcript__role">{t.role === "user" ? "Visitor" : "Fiona"}</span>
          <span className="admin-transcript__text">{t.text}</span>
        </div>
      ))}
    </div>
  );
}

export default function AdminVisitorDetail() {
  const { email = "" } = useParams();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedSessionId, setExpandedSessionId] = useState<number | null>(null);

  useEffect(() => {
    getAdminVisitorDetail(email)
      .then(setDetail)
      .catch(() => setError("Couldn't find that visitor."));
  }, [email]);

  if (error) return <div className="admin__error">{error}</div>;
  if (!detail) return <div className="admin__loading">Loading…</div>;

  return (
    <div>
      <Link className="admin__back-link" to="/admin/visitors">
        ← All visitors
      </Link>

      <div className="admin-visitor-header">
        <h1 className="admin__page-title">{detail.name || detail.email}</h1>
        <div className="admin-visitor-header__meta">
          <span>{detail.company || "—"}</span>
          <span>{detail.email}</span>
          <span>First seen {formatTimestamp(detail.first_seen_at)}</span>
          <span>Last seen {formatTimestamp(detail.last_seen_at)}</span>
          <span>{detail.sessions.length} session{detail.sessions.length === 1 ? "" : "s"}</span>
        </div>
      </div>

      <h2 className="admin__section-title">Sessions</h2>
      <div className="admin-sessions">
        {detail.sessions.map((s) => {
          const expanded = expandedSessionId === s.id;
          return (
            <div key={s.id} className="admin-session">
              <button
                type="button"
                className="admin-session__row"
                onClick={() => setExpandedSessionId(expanded ? null : s.id)}
              >
                <span className="admin-session__path">{s.path}</span>
                <span>
                  {s.status === "allowed" ? (
                    <span className="admin__pill admin__pill--allowed">Allowed</span>
                  ) : (
                    <span className="admin__pill admin__pill--blocked">Blocked</span>
                  )}
                </span>
                <span className="admin-session__time">{formatTimestamp(s.created_at)}</span>
                <span className="admin-session__toggle">{expanded ? "▲" : "▼"}</span>
              </button>
              {expanded && (
                <div className="admin-session__body">
                  {s.status === "allowed" ? (
                    <SessionTranscript visitorId={s.visitor_id} />
                  ) : (
                    <div className="admin__empty">Blocked at the gate — no conversation happened.</div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
