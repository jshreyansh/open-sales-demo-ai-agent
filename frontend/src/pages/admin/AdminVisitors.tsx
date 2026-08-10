import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getAdminVisitors, type AdminVisitor } from "../../lib/api";

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export default function AdminVisitors() {
  const [visitors, setVisitors] = useState<AdminVisitor[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAdminVisitors()
      .then(setVisitors)
      .catch(() => setError("Couldn't reach the admin API."));
  }, []);

  if (error) return <div className="admin__error">{error}</div>;
  if (!visitors) return <div className="admin__loading">Loading…</div>;

  return (
    <div>
      <h1 className="admin__page-title">Visitors ({visitors.length})</h1>
      <div className="admin__table-wrap">
        <table className="admin__table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Company</th>
              <th>Email</th>
              <th>Paths tried</th>
              <th>Sessions</th>
              <th>First seen</th>
              <th>Last seen</th>
              <th>Blocked attempt?</th>
            </tr>
          </thead>
          <tbody>
            {visitors.map((v) => (
              <tr key={v.email}>
                <td>
                  <Link className="admin__link admin__row-link" to={`/admin/visitors/${encodeURIComponent(v.email)}`}>
                    {v.name || "—"}
                  </Link>
                </td>
                <td>{v.company || "—"}</td>
                <td>{v.email}</td>
                <td>{v.paths_tried.join(", ") || "—"}</td>
                <td className="admin__num">{v.session_count}</td>
                <td>{formatTimestamp(v.first_seen_at)}</td>
                <td>{formatTimestamp(v.last_seen_at)}</td>
                <td>{v.ever_blocked ? <span className="admin__pill admin__pill--blocked">Yes</span> : "No"}</td>
              </tr>
            ))}
            {visitors.length === 0 && (
              <tr>
                <td colSpan={8} className="admin__empty">No visitors yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
