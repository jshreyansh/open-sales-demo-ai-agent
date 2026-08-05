import { useState } from "react";
import { MAGIC_ENGINES, STAGE_LABELS, type Stage } from "../registry/contentStudio";
import { useRegisterComponent } from "../lib/uiRegistry";

interface ContentStudioProps {
  initialTab?: string;
}

const AUDIENCES = ["HCP", "Patient", "Payer"];
const totalFormats = MAGIC_ENGINES.reduce((sum, e) => sum + e.formats.length, 0);

export default function ContentStudio({ initialTab }: ContentStudioProps) {
  const [tab, setTab] = useState(initialTab ?? "All");
  const [objective, setObjective] = useState<Stage | null>(null);
  const [audience, setAudience] = useState<string | null>(null);

  useRegisterComponent("content-studio", "video-tab", { click: () => setTab("Video") });
  useRegisterComponent("content-studio", "aid-tab", { click: () => setTab("Aid") });
  useRegisterComponent("content-studio", "mail-tab", { click: () => setTab("Mail") });
  useRegisterComponent("content-studio", "canvas-tab", { click: () => setTab("Canvas") });
  useRegisterComponent("content-studio", "doc-tab", { click: () => setTab("Doc") });

  const engines = tab === "All" ? MAGIC_ENGINES : MAGIC_ENGINES.filter((e) => e.tabId === tab);

  return (
    <div className="page">
      <h1 className="page__title">Content Studio</h1>
      <p className="page__subtitle">Thirty content formats across five Magic Engines — each one MLR-ready the moment it is generated.</p>

      <div className="hero-banner">
        <div className="hero-banner__text">
          <h2>
            Get medical-grade, MLR-ready content in <span style={{ color: "var(--accent)" }}>minutes, not weeks</span>.
          </h2>
          <p>
            MLR readiness is an input, not a downstream check. Every asset is generated already carrying its on-label claims,
            references, fair balance and ISI — so it enters review clean.
          </p>
        </div>
        <div className="hero-banner__stats">
          <div>
            <div className="hero-banner__stat-value">{totalFormats}</div>
            <div className="hero-banner__stat-label">formats</div>
          </div>
          <div>
            <div className="hero-banner__stat-value">{MAGIC_ENGINES.length}</div>
            <div className="hero-banner__stat-label">Magic Engines</div>
          </div>
          <div>
            <div className="hero-banner__stat-value">5</div>
            <div className="hero-banner__stat-label">co-workers</div>
          </div>
          <div>
            <div className="hero-banner__stat-value">{Object.keys(STAGE_LABELS).length}</div>
            <div className="hero-banner__stat-label">objective stages</div>
          </div>
        </div>
      </div>

      <div className="tabs-row">
        {["All", ...MAGIC_ENGINES.map((e) => e.tabId)].map((t) => (
          <button key={t} className={`tab-item ${tab === t ? "tab-item--active" : ""}`} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      <div className="filter-bar">
        <span className="filter-bar__label">Objective</span>
        {(Object.keys(STAGE_LABELS) as Stage[]).map((s) => (
          <button
            key={s}
            className={`filter-pill ${objective === s ? "filter-pill--active" : ""}`}
            onClick={() => setObjective(objective === s ? null : s)}
          >
            {STAGE_LABELS[s]}
          </button>
        ))}
        <span style={{ width: 1, height: 20, background: "var(--border)" }} />
        <span className="filter-bar__label">Audience</span>
        {AUDIENCES.map((a) => (
          <button
            key={a}
            className={`filter-pill ${audience === a ? "filter-pill--active" : ""}`}
            onClick={() => setAudience(audience === a ? null : a)}
          >
            {a}
          </button>
        ))}
      </div>

      {engines.map((engine) => {
        const formats = engine.formats.filter(
          (f) => (!objective || f.stages.includes(objective)) && (!audience || f.audience.includes(audience)),
        );
        if (formats.length === 0) return null;
        const soonCount = engine.formats.filter((f) => f.soon).length;
        return (
          <div key={engine.id} className="engine-section">
            <div className="engine-section__head">
              <h3 className="engine-section__title">{engine.label}</h3>
              <span className="engine-section__desc">{engine.description}</span>
              {soonCount > 0 && <span className="engine-section__soon">{soonCount} coming soon</span>}
            </div>
            <div className="format-grid">
              {formats.map((f) => (
                <div key={f.title} className="format-card">
                  <div className="format-card__head">
                    <h4 className="format-card__title">{f.title}</h4>
                    {f.soon && <span className="format-card__soon-badge">SOON</span>}
                  </div>
                  <p className="format-card__tool">{f.tool}</p>
                  <p className="format-card__desc">{f.description}</p>
                  <div className="format-card__footer">
                    {(["A", "C", "T", "L"] as Stage[]).map((s) => (
                      <span key={s} className={`stage-badge ${f.stages.includes(s) ? "stage-badge--active" : ""}`}>
                        {s}
                      </span>
                    ))}
                    <span>{f.audience}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
