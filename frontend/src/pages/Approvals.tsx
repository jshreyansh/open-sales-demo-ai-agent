import { useEffect, useMemo, useState } from "react";
import { getApprovals } from "../lib/api";
import { useRegisterComponent } from "../lib/uiRegistry";
import type { ApprovalsData, ApprovalEntityKind, ApprovalRow, ApprovalState } from "../lib/types";

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
  // The detail panel this page was missing — a real, stored submission id
  // rather than an index, so a direct agent action ("open this submission")
  // survives the list re-filtering out from under it.
  const [openRowId, setOpenRowId] = useState<string | null>(null);

  useEffect(() => {
    getApprovals().then(setData).catch(() => setData(null));
  }, []);

  // Opens the first pending row still awaiting a decision — the one a
  // prospect asking "what does a review actually look like" means, not an
  // arbitrary row. Falls back to the first row overall so the action still
  // does something sensible once every demo item happens to be decided.
  useRegisterComponent("mlr-review", "submission-detail", {
    open: () =>
      setData((current) => {
        if (current) {
          const target = current.rows.find((r) => r.canDecide) ?? current.rows[0];
          if (target) setOpenRowId(target.id);
        }
        return current;
      }),
  });

  const openRow = data?.rows.find((r) => r.id === openRowId) ?? null;

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

      <div className="card" style={{ padding: 0, overflow: "hidden" }} data-hl="queue:highlight" data-hl-cue="spotlight">
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
                <tr key={r.id} className="approvals-row--clickable" onClick={() => setOpenRowId(r.id)}>
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

      {openRow && data && (
        <SubmissionDetailPanel row={openRow} stages={data.stages} onClose={() => setOpenRowId(null)} />
      )}
    </div>
  );
}

// Decorative — matches the confirmed scope: the timeline reads real
// progress off the row's own stageIndex/currentStage, but Approve/Reject/
// Withdraw don't mutate anything. This is a live product's review gate
// shown for narration, not a real one.
function SubmissionDetailPanel({
  row,
  stages,
  onClose,
}: {
  row: ApprovalRow;
  stages: string[];
  onClose: () => void;
}) {
  const s = STATE_STYLES[row.state];
  // Alternates by entity kind purely for visual variety across rows — both
  // are real, already-uploaded showcase videos, not per-row assets (this
  // demo has no per-submission media of its own).
  const previewSrc = row.entityKind === "asset" ? "/videos/tecentriq-reel.mp4" : "/videos/avatar-showcase.mp4";

  return (
    <>
      <div className="modal-overlay submission-panel__overlay" onClick={onClose} />
      <div className="submission-panel" data-hl="submission-detail:panel">
        <div className="submission-panel__header">
          <div>
            <p className="page__subtitle" style={{ margin: 0 }}>
              {row.entityKind === "asset" ? "Asset" : "Campaign"} · {row.entity.therapy} · Submission #{row.submissionNumber}
            </p>
            <h2 style={{ margin: "2px 0 0", fontSize: 20 }}>{row.entity.name}</h2>
          </div>
          <button className="btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="submission-panel__submitter">
          <span className="approvals-avatar">{initials(row.submittedBy.name)}</span>
          <div>
            <p style={{ margin: 0, fontWeight: 600 }}>Submitted by {row.submittedBy.name}</p>
            <p className="stub-page__note" style={{ margin: 0 }}>{relativeTime(row.submittedAt)}</p>
          </div>
          <span className="approvals-state-badge" style={{ background: s.bg, color: s.color, marginLeft: "auto" }}>
            {s.label}
          </span>
        </div>

        {row.canDecide && (
          <div className="submission-panel__awaiting">
            Awaiting decision from <strong>Any Approver</strong>
          </div>
        )}

        <div className="submission-panel__section-label">Content preview</div>
        <video
          key={previewSrc}
          className="submission-panel__preview"
          src={previewSrc}
          controls
          playsInline
        />

        <div className="submission-panel__section-label">Approval timeline</div>
        <div className="submission-panel__timeline">
          {stages.map((stage, i) => {
            const stepState = i < row.stageIndex - 1 ? "done" : i === row.stageIndex - 1 ? "current" : "pending";
            return (
              <div key={stage} className={`submission-timeline-step submission-timeline-step--${stepState}`}>
                <span className="submission-timeline-step__dot" />
                <div>
                  <p style={{ margin: 0, fontWeight: 600 }}>{stage}</p>
                  <p className="stub-page__note" style={{ margin: 0 }}>
                    {stepState === "done" ? "Approved" : stepState === "current" ? "Awaiting decision" : "Not yet started"}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        <div className="submission-panel__actions">
          <button className="btn btn--primary" style={{ width: "100%" }} onClick={onClose}>
            Approve {row.currentStage}
          </button>
          <div className="submission-panel__actions-row">
            <button className="btn" onClick={onClose}>
              Reject
            </button>
            <button className="btn" onClick={onClose}>
              Withdraw
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
