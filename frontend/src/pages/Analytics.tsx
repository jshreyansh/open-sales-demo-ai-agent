import { useEffect, useState } from "react";
import Icon from "../components/Icon";
import WeeklySendChart from "../components/WeeklySendChart";
import { getAnalyticsOverview } from "../lib/api";
import type { AnalyticsOverview } from "../lib/types";

const TABS = ["Overview", "Channel", "Specialty", "Geo", "By Campaigns", "MagicReel Analytics", "MagicAvatar Analytics"];

export default function Analytics() {
  const [data, setData] = useState<AnalyticsOverview | null>(null);
  const [tab, setTab] = useState("Overview");

  useEffect(() => {
    getAnalyticsOverview().then(setData).catch(() => setData(null));
  }, []);

  if (!data) {
    return (
      <div className="page">
        <p className="stub-page__note">Loading analytics…</p>
      </div>
    );
  }

  const funnelMax = Math.max(...data.engagementFunnel.map((f) => f.value));

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <h1 className="page__title">Analytics</h1>
          <p className="page__subtitle">Campaign performance analytics</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn">Last 30 days</button>
          <button className="btn">Export Report</button>
        </div>
      </div>

      <div className="stat-grid">
        {data.stats.map((s) => (
          <div key={s.id} className="card">
            <div className="stat-card__icon" style={{ background: `${s.accent}1a`, color: s.accent }}>
              <Icon name={s.icon} size={17} />
            </div>
            <div className="stat-card__value">{s.value.toLocaleString()}</div>
            <div className="stat-card__label">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="tabs-row">
        {TABS.map((t) => (
          <button key={t} className={`tab-item ${tab === t ? "tab-item--active" : ""}`} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      {tab === "Overview" ? (
        <div className="analytics-grid">
          <div className="card">
            <div className="section__header">
              <h2 className="section__title">Weekly Send Volume by Channel</h2>
              <div className="chart-legend">
                {data.weeklySendVolume.channels.map((c) => (
                  <span key={c.channel}>
                    <span className="chart-legend__dot" style={{ background: c.color }} />
                    {c.channel}
                  </span>
                ))}
              </div>
            </div>
            <WeeklySendChart weeks={data.weeklySendVolume.weeks} channels={data.weeklySendVolume.channels} />
          </div>

          <div className="card" data-hl="funnel:highlight" data-hl-cue="spotlight">
            <h2 className="section__title">Engagement Funnel</h2>
            <p className="section__subtitle">
              Sent · Viewed · Played · Completed · Shared. Includes campaign sends + manual shares — Viewed may exceed Sent.
            </p>
            <div style={{ marginTop: 16 }}>
              {data.engagementFunnel.map((f) => (
                <div key={f.stage} className="funnel-row">
                  <span className="funnel-row__label">{f.stage}</span>
                  <div className="progress-bar">
                    <div
                      className="progress-bar__fill"
                      style={{ width: `${(f.value / funnelMax) * 100}%`, background: f.color }}
                    />
                  </div>
                  <span className="funnel-row__value">{f.value.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : (
        <div className="card">
          <p className="stub-page__note">{tab} — not built yet.</p>
        </div>
      )}
    </div>
  );
}
