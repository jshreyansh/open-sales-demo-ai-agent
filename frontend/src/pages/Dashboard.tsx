import { useEffect, useRef, useState } from "react";
import Icon from "../components/Icon";
import Sparkline from "../components/Sparkline";
import { getDashboard, sendMessage, type AgentAction } from "../lib/api";
import { getVisitorId } from "../lib/session";
import type { DashboardData } from "../lib/types";

interface ChatMessage {
  role: "user" | "agent";
  text: string;
}

const visitorId = getVisitorId();
const RANGES = ["7D", "30D", "90D", "Custom"];

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [range, setRange] = useState("30D");
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "agent", text: "Hi, I'm Emma. Ask me to show you around the dashboard." },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const insightsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getDashboard().then(setData).catch(() => setData(null));
  }, []);

  function executeAction(action?: AgentAction) {
    if (!action || !insightsRef.current) return;
    if (action.method === "highlight") {
      insightsRef.current.classList.add("panel--highlighted");
      setTimeout(() => insightsRef.current?.classList.remove("panel--highlighted"), 1500);
    }
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || sending) return;
    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setSending(true);
    try {
      const { reply, action } = await sendMessage(visitorId, text);
      setMessages((prev) => [...prev, { role: "agent", text: reply }]);
      executeAction(action);
    } catch {
      setMessages((prev) => [...prev, { role: "agent", text: "Sorry, I couldn't reach the demo backend." }]);
    } finally {
      setSending(false);
    }
  }

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

      <div className="insights-grid card" ref={insightsRef}>
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
        ))}
      </div>

      <div className="section card">
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

      <div className="chat">
        <div className="chat__header">Emma</div>
        <div className="chat__messages">
          {messages.map((m, i) => (
            <div key={i} className={`chat__message chat__message--${m.role}`}>
              {m.text}
            </div>
          ))}
        </div>
        <div className="chat__input">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Ask anything..."
            disabled={sending}
          />
          <button onClick={handleSend} disabled={sending}>
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
