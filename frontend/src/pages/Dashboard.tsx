import { useEffect, useState } from "react";
import Icon from "../components/Icon";
import Sparkline from "../components/Sparkline";
import { getDashboard } from "../lib/api";
import { useRegisterComponent } from "../lib/uiRegistry";
import { useHighlight } from "../lib/useHighlight";
import type { DashboardData } from "../lib/types";

const RANGES = ["7D", "30D", "90D", "Custom"];

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [range, setRange] = useState("30D");
  const insights = useHighlight();
  const activeCampaigns = useHighlight();

  useEffect(() => {
    getDashboard().then(setData).catch(() => setData(null));
  }, []);

  useRegisterComponent("dashboard", "insights", { highlight: insights.highlight });
  useRegisterComponent("dashboard", "active-campaigns", { highlight: activeCampaigns.highlight });

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

      <div className="section__header">
        <h2 className="section__title">Insights</h2>
        <span className="section__subtitle">Last 30 days</span>
      </div>

      <div className="insights-grid card" ref={insights.ref}>
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

      <div className="section card" ref={activeCampaigns.ref}>
        <div className="section__header">
          <div>
            <h2 className="section__title">Active Campaigns</h2>
            <p className="section__subtitle">Status & engagement of running programs</p>
          </div>
          <a className="section__link" href="#">
            View all →
          </a>
        </div>
        {data.activeCampaigns.map((c) => (
          <div key={c.name} className="campaign-row">
            <div>
              <p className="campaign-row__name">{c.name}</p>
              <p className="campaign-row__segment">{c.segment}</p>
            </div>
            <div className="campaign-row__right">
              <div className="progress-bar">
                <div
                  className="progress-bar__fill"
                  style={{
                    width: `${c.percent}%`,
                    background: c.status === "Paused" ? "#dc2626" : "#d97706",
                  }}
                />
              </div>
              <span>{c.percent}%</span>
              <span className={`status-pill status-pill--${c.status.toLowerCase()}`}>{c.status}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="section card">
        <div className="section__header">
          <div>
            <h2 className="section__title">Campaign Performance</h2>
            <p className="section__subtitle">Sent · delivered · opened · clicked by channel</p>
          </div>
        </div>
        {data.campaignPerformance.map((c) => (
          <div key={c.channel} className="channel-row">
            <div className="channel-row__head">
              <span className="channel-row__name">{c.channel}</span>
              <span className="channel-row__sent">{c.sent.toLocaleString()} sent</span>
            </div>
            <div className="channel-row__stats">
              <span className="channel-row__stat">
                Delivered <b>{c.delivered}%</b>
              </span>
              <span className="channel-row__stat">
                Opened <b>{c.opened}%</b>
              </span>
              <span className="channel-row__stat">
                Clicked <b>{c.clicked}%</b>
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="section card">
        <div className="section__header">
          <div>
            <h2 className="section__title">Top Content by Views</h2>
            <p className="section__subtitle">Most-watched assets in this range</p>
          </div>
        </div>
        {data.topContent.map((c) => (
          <div key={c.title} className="content-row">
            <span>{c.title}</span>
            <span className="content-row__views">{c.views.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
