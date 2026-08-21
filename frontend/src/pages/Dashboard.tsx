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

      {/* Four cards in a 2x2 grid, each with ONE headline number.
          Before this it was four full-width lanes stacked down the page,
          every card giving its three metrics identical size — so twelve
          numbers arrived at the same volume with nothing telling you which
          mattered, and the whole thing ran past a thousand pixels tall on
          the first screen a prospect ever sees. Giving each card a hero and
          two supporting figures is what makes it scannable; the grid is what
          makes it fit. */}
      <div className="insight-grid" data-hl="insights:highlight" data-hl-cue="spotlight">
        {data.insights.map((card) => {
          const [hero, ...rest] = card.metrics;
          return (
            <div key={card.id} className="insight-tile card" style={{ ["--accent-color" as string]: card.accent }}>
              <div className="insight-tile__head">
                <span className="insight-tile__icon">
                  <Icon name={card.icon} />
                </span>
                <span className="insight-tile__label">{card.label}</span>
              </div>

              <div className="insight-tile__hero">
                <span className="insight-tile__hero-value">{hero.value}</span>
                {hero.sub && <span className="insight-tile__hero-sub">{hero.sub}</span>}
              </div>
              <div className="insight-tile__hero-label">{hero.label}</div>

              <div className="insight-tile__rest">
                {rest.map((m) => (
                  <div key={m.label} className="insight-tile__metric">
                    <div className="insight-tile__metric-value">{m.value}</div>
                    <div className="insight-tile__metric-label">{m.label}</div>
                  </div>
                ))}
              </div>

              {/* Full-width along the card's foot rather than tucked beside
                  the first metric, where it was reading as a stray scribble
                  instead of a trend. */}
              <div className="insight-tile__spark">
                <Sparkline values={card.sparkline} color={card.accent} fluid />
              </div>
            </div>
          );
        })}
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
        {/* Two per row inside the card. Full-width rows put the completion
            bar and status pill about a thousand pixels from the dossier they
            describe, which is the same reading problem as the lists below. */}
        <div className="dossier-grid">
          {data.brandDossiers.map((d) => (
            <div key={d.name} className="dossier-row">
              <div className="dossier-row__top">
                <p className="dossier-row__name">{d.name}</p>
                <span className="status-pill" style={DOSSIER_TONE[d.status]}>
                  {d.status}
                </span>
              </div>
              <p className="dossier-row__meta">{d.meta}</p>
              <div className="dossier-row__bar">
                <div className="progress-bar">
                  <div className="progress-bar__fill" style={{ width: `${d.percent}%`, background: DOSSIER_TONE[d.status].color }} />
                </div>
                <span className="dossier-row__pct">{d.percent}%</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Two lists side by side rather than stacked full-width. On a 1200px
          lane each row's number ended up a thousand pixels from its label,
          so reading one line meant crossing the whole screen; halving the
          width puts label and value back in the same glance. */}
      <div className="dash-split">
        <div className="section card">
          <div className="section__header">
            <div>
              <h2 className="section__title">Review Throughput by Stage</h2>
              <p className="section__subtitle">Where content moves — and where it gets sent back</p>
            </div>
          </div>
          {data.reviewStages.map((s) => (
            <div key={s.stage} className="stage-row">
              <div className="stage-row__head">
                <span className="stage-row__name">{s.stage}</span>
                <span className="stage-row__count">{s.submissions.toLocaleString()} submissions</span>
              </div>
              {/* First-pass rate as a bar, not a third number in a line of
                  numbers: it is a proportion, and a proportion is faster to
                  compare across four stages as a length than as digits. */}
              <div className="stage-row__bar">
                <div className="stage-row__bar-fill" style={{ width: `${s.firstPass}%` }} />
              </div>
              <div className="stage-row__stats">
                <span><b>{s.firstPass}%</b> first-pass</span>
                <span><b>{s.avgDays}d</b> in stage</span>
                <span><b>{s.sentBack}%</b> sent back</span>
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
          {data.topAssets.map((a, i) => (
            <div key={a.title} className="asset-row">
              {/* The rank is real information here — the list is ordered by
                  reuse — so it earns a marker. */}
              <span className="asset-row__rank">{i + 1}</span>
              <span className="asset-row__title">{a.title}</span>
              <span className="asset-row__uses">{a.uses.toLocaleString()}<span className="asset-row__uses-unit"> reuses</span></span>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
