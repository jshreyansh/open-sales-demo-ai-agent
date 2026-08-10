import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getAdminStats, type AdminStats } from "../../lib/api";

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

// Deliberately a handful of numbers that answer "how is the demo actually
// being used" — not a kitchen-sink analytics dump. Real sessions vs. blocked
// attempts, and the dashboard/meet split, are the two things worth knowing
// at a glance; everything else lives one click away on the Visitors tab.
export default function AdminDashboard() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAdminStats()
      .then(setStats)
      .catch(() => setError("Couldn't reach the admin API."));
  }, []);

  if (error) return <div className="admin__error">{error}</div>;
  if (!stats) return <div className="admin__loading">Loading…</div>;

  const totalAttempts = stats.total_sessions + stats.blocked_attempts;
  const blockedPct = totalAttempts > 0 ? Math.round((stats.blocked_attempts / totalAttempts) * 100) : 0;

  return (
    <div>
      <h1 className="admin__page-title">Dashboard</h1>

      <div className="admin-stats">
        <div className="admin-stat-card">
          <div className="admin-stat-card__label">Unique visitors</div>
          <div className="admin-stat-card__value">{stats.total_visitors}</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-card__label">Total sessions</div>
          <div className="admin-stat-card__value">{stats.total_sessions}</div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-card__label">Dashboard vs. Meet</div>
          <div className="admin-stat-card__value">
            {stats.dashboard_sessions} <span className="admin-stat-card__unit">/</span> {stats.meet_sessions}
          </div>
        </div>
        <div className="admin-stat-card">
          <div className="admin-stat-card__label">Blocked attempts</div>
          <div className="admin-stat-card__value">
            {stats.blocked_attempts}
            {totalAttempts > 0 && <span className="admin-stat-card__unit"> ({blockedPct}%)</span>}
          </div>
        </div>
      </div>

      <h2 className="admin__section-title">Most recent visitors</h2>
      <div className="admin__table-wrap">
        <table className="admin__table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Company</th>
              <th>Email</th>
              <th>Last seen</th>
            </tr>
          </thead>
          <tbody>
            {stats.recent_visitors.map((v) => (
              <tr key={v.email}>
                <td>{v.name || "—"}</td>
                <td>{v.company || "—"}</td>
                <td>
                  <Link className="admin__link" to={`/admin/visitors/${encodeURIComponent(v.email)}`}>
                    {v.email}
                  </Link>
                </td>
                <td>{formatTimestamp(v.last_seen_at)}</td>
              </tr>
            ))}
            {stats.recent_visitors.length === 0 && (
              <tr>
                <td colSpan={4} className="admin__empty">No visitors yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
