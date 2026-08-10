import { useEffect, useState } from "react";
import { getAdminAttempts, type AdminAttempt } from "../../lib/api";

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

export default function AdminAttempts() {
  const [attempts, setAttempts] = useState<AdminAttempt[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getAdminAttempts()
      .then(setAttempts)
      .catch(() => setError("Couldn't reach the admin API."));
  }, []);

  if (error) return <div className="admin__error">{error}</div>;
  if (!attempts) return <div className="admin__loading">Loading…</div>;

  return (
    <div>
      <h1 className="admin__page-title">Attempts log ({attempts.length})</h1>
      <div className="admin__table-wrap">
        <table className="admin__table">
          <thead>
            <tr>
              <th>When</th>
              <th>Path</th>
              <th>Status</th>
              <th>Email</th>
              <th>Name</th>
              <th>Company</th>
            </tr>
          </thead>
          <tbody>
            {attempts.map((a) => (
              <tr key={a.id}>
                <td>{formatTimestamp(a.created_at)}</td>
                <td>{a.path}</td>
                <td>
                  {a.status === "allowed" ? (
                    <span className="admin__pill admin__pill--allowed">Allowed</span>
                  ) : (
                    <span className="admin__pill admin__pill--blocked">Blocked · personal email</span>
                  )}
                </td>
                <td>{a.email}</td>
                <td>{a.name || "—"}</td>
                <td>{a.company || "—"}</td>
              </tr>
            ))}
            {attempts.length === 0 && (
              <tr>
                <td colSpan={6} className="admin__empty">No attempts logged yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
