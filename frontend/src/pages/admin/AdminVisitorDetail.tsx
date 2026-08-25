import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getAdminCallSummary,
  getAdminTranscript,
  getAdminVisitorDetail,
  type AdminCallRating,
  type AdminVisitorDetail as Detail,
  type TranscriptTurn,
} from "../../lib/api";

const SENTIMENT_LABELS: Record<string, string> = {
  great: "Great",
  okay: "Okay",
  needs_work: "Needs work",
};

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

// Mirrors backend agent/runtime.py's _QUAL_LABELS/_MEDDIC_LABELS keys exactly
// — the backend owns capture logic and raw field names, this owns display
// copy, same split of responsibility as the rest of this app's UI code.
const REQUIRED_QUAL_FIELDS: [key: string, label: string][] = [
  ["meddic_pain", "1. What problem brought them here"],
  ["qual_current_solution", "2. How they solve it today"],
  ["qual_daily_users", "3. Who'd use it day to day"],
  ["qual_past_attempts", "4. What they've already tried"],
  ["qual_next_step_response", "5. Connect with a rep for next steps"],
];

const BONUS_MEDDIC_FIELDS: [key: string, label: string][] = [
  ["meddic_metrics", "Metrics"],
  ["meddic_economic_buyer", "Economic Buyer"],
  ["meddic_decision_criteria", "Decision Criteria"],
  ["meddic_decision_process", "Decision Process"],
  ["meddic_champion", "Champion"],
];

function QualificationProfile({ qualification }: { qualification: Record<string, string> }) {
  const bonusCaptured = BONUS_MEDDIC_FIELDS.filter(([key]) => qualification[key]);

  return (
    <div className="admin-qualification">
      <h3 className="admin-qualification__title">Qualification (5 required questions)</h3>
      <dl className="admin-qualification__list">
        {REQUIRED_QUAL_FIELDS.map(([key, label]) => (
          <div key={key} className="admin-qualification__row">
            <dt>{label}</dt>
            <dd className={qualification[key] ? "" : "admin-qualification__missing"}>
              {qualification[key] || "Not captured"}
            </dd>
          </div>
        ))}
      </dl>
      {bonusCaptured.length > 0 && (
        <>
          <h4 className="admin-qualification__subtitle">Additional insights (MEDDIC)</h4>
          <dl className="admin-qualification__list">
            {bonusCaptured.map(([key, label]) => (
              <div key={key} className="admin-qualification__row">
                <dt>{label}</dt>
                <dd>{qualification[key]}</dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </div>
  );
}

// Fetched only once its session is expanded, same lazy-load reasoning as
// SessionTranscript below — most sessions won't be looked at.
function CallSummary({ visitorId }: { visitorId: string }) {
  const [summary, setSummary] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    getAdminCallSummary(visitorId).then((r) => setSummary(r.summary));
  }, [visitorId]);

  if (summary === undefined) return <div className="admin__loading">Generating summary…</div>;
  if (!summary) return <div className="admin__empty">No summary yet — the call may still be in progress.</div>;

  return (
    <div className="admin-call-summary">
      <h3 className="admin-call-summary__title">AI Call Summary</h3>
      <p>{summary}</p>
    </div>
  );
}

// Already attached inline on the session object (server.py's
// admin_visitor_detail), same as `qualification` above — no separate
// fetch needed, it's cheap data with no LLM cost behind it.
function CallRating({ rating }: { rating: AdminCallRating | null }) {
  if (!rating) return <div className="admin__empty">No feedback screen result for this session.</div>;
  if (rating.skipped) {
    return (
      <div className="admin-call-rating">
        <h3 className="admin-call-rating__title">Post-call feedback</h3>
        <p className="admin__empty">Visitor skipped the feedback screen.</p>
      </div>
    );
  }

  return (
    <div className="admin-call-rating">
      <h3 className="admin-call-rating__title">Post-call feedback</h3>
      <dl className="admin-qualification__list">
        <div className="admin-qualification__row">
          <dt>Sentiment</dt>
          <dd>{rating.sentiment ? SENTIMENT_LABELS[rating.sentiment] ?? rating.sentiment : "—"}</dd>
        </div>
        <div className="admin-qualification__row">
          <dt>Reason given</dt>
          <dd className={rating.reason ? "" : "admin-qualification__missing"}>{rating.reason || "Not given"}</dd>
        </div>
        <div className="admin-qualification__row">
          <dt>Tags</dt>
          <dd className={rating.tags.length ? "" : "admin-qualification__missing"}>
            {rating.tags.length ? rating.tags.join(", ") : "None selected"}
          </dd>
        </div>
        <div className="admin-qualification__row">
          <dt>Call duration</dt>
          <dd>{rating.call_duration_secs != null ? `${rating.call_duration_secs}s` : "—"}</dd>
        </div>
        <div className="admin-qualification__row">
          <dt>Ended via</dt>
          <dd>{rating.disconnect_reason || "—"}</dd>
        </div>
      </dl>
    </div>
  );
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
                    <>
                      <QualificationProfile qualification={s.qualification} />
                      <CallRating rating={s.rating} />
                      <CallSummary visitorId={s.visitor_id} />
                      <SessionTranscript visitorId={s.visitor_id} />
                    </>
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
