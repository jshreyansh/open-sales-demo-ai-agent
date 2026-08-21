import { useEffect, useState } from "react";
import Icon from "../components/Icon";
import Sparkline from "../components/Sparkline";
import { getDashboard } from "../lib/api";
import type { DashboardData } from "../lib/types";

const RANGES = ["7D", "30D", "90D", "Custom"];

// Inline colours rather than new `.status-pill--*` modifiers: index.css only
// ships the two the campaign list needed (paused/optimizing), and the
// stylesheet is off-limits this session. Approvals.tsx already tones
// `.approvals-state-badge` inline for exactly this reason, so the pattern is
// established — the class still supplies the pill shape and the leading dot.
const DOSSIER_TONE: Record<string, { background: string; color: string }> = {
  Live: { background: "rgba(22, 163, 74, 0.1)", color: "#16a34a" },
  "In Build": { background: "rgba(217, 119, 6, 0.1)", color: "#d97706" },
};

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [range, setRange] = useState("30D");

  useEffect(() => {
    getDashboard().then(setData).catch(() => setData(null));
  }, []);

  if (!data) {
    return (
      <div className="page">
        <p className="stub-page__note">Loading dashboard…</p>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page__header">
        <h1 className="page__title">Dashboard</h1>
        <div>
          <div className="page__header-label">Date Range</div>
          <div className="pill-toggle-group">
            {RANGES.map((r) => (
              <button
                key={r}
                className={`pill-toggle ${range === r ? "pill-toggle--active" : ""}`}
                onClick={() => setRange(r)}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="section__header">
        <h2 className="section__title">Insights</h2>
        <span className="section__subtitle">Last 30 days</span>
      </div>

      <div className="insights-grid card" data-hl="insights:highlight" data-hl-cue="spotlight">
        {data.insights.map((card) => (
          <div key={card.id} className="insight-card" style={{ ["--accent-color" as string]: card.accent }}>
            <div className="insight-card__head">
              <div className="insight-card__icon">
                <Icon name={card.icon} />
              </div>
              <div>
                <p className="insight-card__label">{card.label}</p>
                <p className="insight-card__desc">{card.description}</p>
              </div>
            </div>
            <div className="insight-card__metrics-row">
              {card.metrics.map((m, i) => (
                <div key={m.label} className="insight-card__metric">
                  <div className="insight-card__metric-label">{m.label}</div>
                  <div className="insight-card__metric-value">
                    {m.value}
                    {m.sub && <span className="insight-card__metric-sub">{m.sub}</span>}
                  </div>
                  {i === 0 && <Sparkline values={card.sparkline} color={card.accent} />}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="section card" data-hl="brand-dossiers:highlight" data-hl-cue="spotlight">
        <div className="section__header">
          <div>
            <h2 className="section__title">Brand Dossiers</h2>
            <p className="section__subtitle">Source-of-truth packs every generation is built from</p>
          </div>
          <a className="section__link" href="#">
            View all →
          </a>
        </div>
        {data.brandDossiers.map((d) => (
          <div key={d.name} className="campaign-row">
            <div>
              <p className="campaign-row__name">{d.name}</p>
              <p className="campaign-row__segment">{d.meta}</p>
            </div>
            <div className="campaign-row__right">
              <div className="progress-bar">
                <div className="progress-bar__fill" style={{ width: `${d.percent}%`, background: DOSSIER_TONE[d.status].color }} />
              </div>
              <span>{d.percent}%</span>
              <span className="status-pill" style={DOSSIER_TONE[d.status]}>
                {d.status}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="section card">
        <div className="section__header">
          <div>
            <h2 className="section__title">Review Throughput by Stage</h2>
            <p className="section__subtitle">Where content moves — and where it gets sent back</p>
          </div>
        </div>
        {data.reviewStages.map((s) => (
          <div key={s.stage} className="channel-row">
            <div className="channel-row__head">
              <span className="channel-row__name">{s.stage}</span>
              <span className="channel-row__sent">{s.submissions.toLocaleString()} submissions</span>
            </div>
            <div className="channel-row__stats">
              <span className="channel-row__stat">
                First-pass <b>{s.firstPass}%</b>
              </span>
              <span className="channel-row__stat">
                Avg in stage <b>{s.avgDays}d</b>
              </span>
              <span className="channel-row__stat">
                Sent back <b>{s.sentBack}%</b>
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="section card">
        <div className="section__header">
          <div>
            <h2 className="section__title">Top Library Assets</h2>
            <p className="section__subtitle">Most-reused assets in this range</p>
          </div>
        </div>
        {data.topAssets.map((a) => (
          <div key={a.title} className="content-row">
            <span>{a.title}</span>
            {/* Class name is a leftover from the view-count era; it only sets
                the muted colour, so it's reused rather than renamed — the
                stylesheet is being edited elsewhere this session. */}
            <span className="content-row__views">{a.uses.toLocaleString()} reuses</span>
          </div>
        ))}
      </div>
    </div>
  );
}
