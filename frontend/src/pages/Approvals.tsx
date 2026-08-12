import { useEffect, useMemo, useState } from "react";
import { getApprovals } from "../lib/api";
import { useRegisterComponent } from "../lib/uiRegistry";
import { useHighlight } from "../lib/useHighlight";
import type { ApprovalsData, ApprovalEntityKind, ApprovalState } from "../lib/types";

type Tab = "pending" | "approved" | "rejected" | "withdrawn" | "all";

const TABS: { id: Tab; label: string }[] = [
  { id: "pending", label: "Pending" },
  { id: "approved", label: "Approved" },
  { id: "rejected", label: "Rejected" },
  { id: "withdrawn", label: "Withdrawn" },
  { id: "all", label: "All" },
];

const STATE_STYLES: Record<ApprovalState, { bg: string; color: string; label: string }> = {
  pending: { bg: "rgba(245,158,11,0.1)", color: "#D97706", label: "Pending" },
  approved: { bg: "rgba(16,185,129,0.1)", color: "#059669", label: "Approved" },
  rejected: { bg: "rgba(239,68,68,0.1)", color: "#DC2626", label: "Rejected" },
  withdrawn: { bg: "rgba(0,0,0,0.06)", color: "#6B7280", label: "Withdrawn" },
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}

function relativeTime(iso: string): string {
  const diff = Math.max(0, Date.now() - new Date(iso).getTime());
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m} minute${m === 1 ? "" : "s"} ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
  const d = Math.floor(h / 24);
  return `${d} day${d === 1 ? "" : "s"} ago`;
}

export default function Approvals() {
  const [data, setData] = useState<ApprovalsData | null>(null);
  const [tab, setTab] = useState<Tab>("pending");
  const [search, setSearch] = useState("");
  const [entityFilter, setEntityFilter] = useState<"all" | ApprovalEntityKind>("all");
  const [stageFilter, setStageFilter] = useState("all");
  const queue = useHighlight();

  useEffect(() => {
    getApprovals().then(setData).catch(() => setData(null));
  }, []);

  useRegisterComponent("mlr-review", "queue", { highlight: queue.spotlight });

  const tabCounts = useMemo(() => {
    const counts: Record<Tab, number> = { pending: 0, approved: 0, rejected: 0, withdrawn: 0, all: data?.rows.length ?? 0 };
    for (const r of data?.rows ?? []) counts[r.state]++;
    return counts;
  }, [data]);

  const subtitle = useMemo(() => {
    if (!data || data.rows.length === 0) return "No submissions yet";
    const reviewed = tabCounts.approved + tabCounts.rejected;
    const awaiting = data.rows.filter((r) => r.canDecide).length;
    const base = `${tabCounts.pending} pending · ${reviewed} reviewed`;
    return awaiting > 0 ? `${base} · ${awaiting} awaiting your decision` : base;
  }, [data, tabCounts]);

  const filteredRows = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    return data.rows.filter((r) => {
      if (tab !== "all" && r.state !== tab) return false;
      if (entityFilter !== "all" && r.entityKind !== entityFilter) return false;
      if (stageFilter !== "all" && r.currentStage !== stageFilter) return false;
      if (q && !`${r.entity.name} ${r.entity.therapy} ${r.submittedBy.name}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [data, tab, entityFilter, stageFilter, search]);

  if (!data) {
    return (
      <div className="page">
        <p className="stub-page__note">Loading approvals…</p>
      </div>
    );
  }

  return (
    <div className="page">
      <h1 className="page__title">Approvals</h1>
      <p className="page__subtitle">{subtitle}</p>

      <div className="tabs-row" style={{ marginTop: 16 }}>
        {TABS.map((t) => (
          <button key={t.id} className={`tab-item ${tab === t.id ? "tab-item--active" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}
            {tabCounts[t.id] > 0 && <span className="approvals-tab-count">{tabCounts[t.id]}</span>}
          </button>
        ))}
      </div>

      <div className="filter-bar" style={{ borderBottom: "none", marginBottom: 12 }}>
        <input
          className="approvals-search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search submissions…"
        />
        <select className="select-field" style={{ width: "auto" }} value={entityFilter} onChange={(e) => setEntityFilter(e.target.value as "all" | ApprovalEntityKind)}>
          <option value="all">All types</option>
          <option value="asset">Asset</option>
          <option value="campaign">Campaign</option>
        </select>
        <select className="select-field" style={{ width: "auto" }} value={stageFilter} onChange={(e) => setStageFilter(e.target.value)}>
          <option value="all">All stages</option>
          {data.stages.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <div className="card" style={{ padding: 0, overflow: "hidden" }} ref={queue.ref}>
        <table className="approvals-table">
          <thead>
            <tr>
              {["Submission", "Type", "Therapy", "Current stage", "State", "Submitted by", "Submitted"].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredRows.map((r) => {
              const s = STATE_STYLES[r.state];
              return (
                <tr key={r.id}>
                  <td>
                    <div className="approvals-table__primary">{r.entity.name}</div>
                    <div className="approvals-table__meta">
                      #{r.submissionNumber} · {r.entityKind === "asset" ? "Asset" : "Campaign"}
                    </div>
                  </td>
                  <td>
                    <span className="approvals-type-pill">{r.entity.type}</span>
                  </td>
                  <td className="approvals-table__meta">{r.entity.therapy}</td>
                  <td>
                    <span className="approvals-stage-chip">
                      {r.stageIndex}/{r.stageTotal} {r.currentStage}
                    </span>
                  </td>
                  <td>
                    <span className="approvals-state-badge" style={{ background: s.bg, color: s.color }}>
                      {s.label}
                    </span>
                  </td>
                  <td>
                    <div className="approvals-submitter">
                      <span className="approvals-avatar">{initials(r.submittedBy.name)}</span>
                      {r.submittedBy.name}
                    </div>
                  </td>
                  <td className="approvals-table__meta">{relativeTime(r.submittedAt)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {filteredRows.length === 0 && (
          <div style={{ textAlign: "center", padding: "48px 0" }}>
            <p className="stub-page__note">
              {tab === "pending" ? "All caught up" : "Nothing here yet"}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
