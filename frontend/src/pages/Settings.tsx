import { Fragment, useEffect, useState } from "react";
import { useRegisterComponent } from "../lib/uiRegistry";

type SettingsTab = "account" | "integrations" | "billing" | "plans";

const TABS: { id: SettingsTab; label: string }[] = [
  { id: "account", label: "Account" },
  { id: "integrations", label: "Integrations" },
  { id: "billing", label: "Billing & credits" },
  { id: "plans", label: "Plans" },
];

export default function Settings({ initialTab }: { initialTab: SettingsTab }) {
  const [tab, setTab] = useState<SettingsTab>(initialTab);
  useEffect(() => setTab(initialTab), [initialTab]);

  // Each tab is independently agent-reachable — see registry.py. Highlight
  // only switches the tab visually; there's nothing else to "do" here since
  // the whole settings surface is decorative in this demo.
  useRegisterComponent("settings-account", "account", { highlight: () => setTab("account") });
  useRegisterComponent("settings-integrations", "integrations", { highlight: () => setTab("integrations") });
  useRegisterComponent("settings-billing", "billing", { highlight: () => setTab("billing") });
  useRegisterComponent("settings-plans", "plans", { highlight: () => setTab("plans") });

  return (
    <div className="page">
      <h1 className="page__title">Settings</h1>
      <p className="page__subtitle">Workspace name, plan, and the integrations that keep content compliant.</p>

      <div className="tabs-row" style={{ marginTop: 16, marginBottom: 20 }}>
        {TABS.map((t) => (
          <button key={t.id} className={`tab-item ${tab === t.id ? "tab-item--active" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "account" && <AccountTab />}
      {tab === "integrations" && <IntegrationsTab />}
      {tab === "billing" && <BillingTab />}
      {tab === "plans" && <PlansTab />}
    </div>
  );
}

function AccountTab() {
  return (
    <div className="card" style={{ padding: 20, maxWidth: 640 }} data-hl="account:highlight" data-hl-cue="spotlight">
      <p className="filter-bar__label" style={{ marginBottom: 4 }}>Account</p>
      <h2 style={{ margin: "0 0 16px", fontSize: 16 }}>Your organisation's account details</h2>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div>
          <span className="field-label">Account name</span>
          <input className="select-field" style={{ width: "100%" }} defaultValue="Shreyansh Jaiswal" readOnly />
        </div>
        <div>
          <span className="field-label">Company</span>
          <input className="select-field" style={{ width: "100%" }} defaultValue="SwishX Demo" readOnly />
        </div>
      </div>
      <div style={{ marginTop: 16 }}>
        <span className="field-label">Therapy areas</span>
        <div style={{ marginTop: 6 }}>
          <span className="dossier-card__category">Cardiology</span>
        </div>
      </div>
    </div>
  );
}

interface Integration {
  id: string;
  name: string;
  description: string;
  logo: string;
  connected: boolean;
}

const INTEGRATIONS: Integration[] = [
  {
    id: "veeva-promomats",
    name: "Veeva Vault PromoMats",
    description: "Compliant, end-to-end commercial content management and MLR review for life sciences — the industry standard for routing promotional content through approval.",
    logo: "/logos/veeva-promomats.png",
    connected: true,
  },
  {
    id: "indegene-cortex",
    name: "Indegene Cortex",
    description: "Indegene's enterprise generative-AI platform for life sciences — content supply chain, MLR acceleration, and medical writing workflows.",
    logo: "/logos/indegene.jpg",
    connected: true,
  },
];

function IntegrationsTab() {
  const [state, setState] = useState<Record<string, boolean>>(
    Object.fromEntries(INTEGRATIONS.map((i) => [i.id, i.connected]))
  );
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 14 }} data-hl="integrations:highlight" data-hl-cue="spotlight">
      {INTEGRATIONS.map((i) => (
        <div key={i.id} className="card" style={{ padding: 16 }}>
          <div style={{ display: "flex", gap: 12 }}>
            <span className="integration-card__logo">
              <img src={i.logo} alt={i.name} />
            </span>
            <div style={{ flex: 1 }}>
              <p style={{ margin: 0, fontWeight: 700, fontSize: 14 }}>{i.name}</p>
              <p className="stub-page__note" style={{ margin: "4px 0 0", fontSize: 12, lineHeight: 1.5 }}>{i.description}</p>
            </div>
          </div>
          <div className="integration-card__footer">
            <label className="integration-toggle">
              <input
                type="checkbox"
                checked={state[i.id]}
                onChange={() => setState((s) => ({ ...s, [i.id]: !s[i.id] }))}
              />
              <span className="integration-toggle__track">
                <span className="integration-toggle__thumb" />
              </span>
              <span className={`integration-toggle__label ${state[i.id] ? "integration-toggle__label--on" : ""}`}>
                {state[i.id] ? "Connected" : "Disconnected"}
              </span>
            </label>
            <div style={{ display: "flex", gap: 6 }}>
              <button className="btn" style={{ padding: "4px 10px", fontSize: 12 }}>Edit</button>
              <button className="btn" style={{ padding: "4px 10px", fontSize: 12 }}>Logs</button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

const TOP_UP_PACKS = [
  { credits: "30,000", price: "₹50,000", perCredit: "₹1.67", validity: "3 months" },
  { credits: "75,000", price: "₹1,10,000", perCredit: "₹1.47", validity: "6 months" },
];

// What each credit-spending action actually costs — grounded to formats and
// channels this demo actually has (MagicReel, MagicAvatar, MagicCanvas,
// WhatsApp, HCP consent). No SMS/Email/rep-quiz rows: those aren't
// demoed anywhere in this build, so a credits table claiming a price for
// them would be the same "describes a capability that isn't there" mistake
// dashboard.py's own hard rule exists to avoid.
const CREDIT_SECTIONS: { section: string; rows: { action: string; credits: string; output: string }[] }[] = [
  {
    section: "AI content creation",
    rows: [
      { action: "MagicReel HD video (60s)", credits: "5,000", output: "10 videos" },
      { action: "MagicReel premium cinematic 4K video (60s)", credits: "15,000", output: "3 videos" },
      { action: "MagicCanvas interactive image / flyer / PDF", credits: "500", output: "100 assets" },
      { action: "MagicAvatar Master HD video (60s)", credits: "5,000", output: "10 videos" },
      { action: "MagicAvatar Master premium cinematic 4K video (60s)", credits: "15,000", output: "3 videos" },
      { action: "Digital Twin video & audio overlay (MagicAvatar)", credits: "100", output: "500 overlays" },
    ],
  },
  {
    section: "Distribution — per recipient, per send",
    rows: [
      { action: "HCP consent form", credits: "1", output: "50,000 recipients" },
      { action: "WhatsApp send", credits: "2", output: "25,000 recipients" },
    ],
  },
  {
    section: "Edits",
    rows: [
      { action: "Content edits (first 5 per piece)", credits: "Free", output: "—" },
      { action: "Additional edits (beyond 5, per edit)", credits: "200", output: "250 edits" },
    ],
  },
];

function CreditsTable() {
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <table className="approvals-table">
        <thead>
          <tr>
            <th>Action</th>
            <th>Credits used</th>
            <th>Output with 50k credits</th>
          </tr>
        </thead>
        <tbody>
          {CREDIT_SECTIONS.map((sec) => (
            <Fragment key={sec.section}>
              <tr className="credits-table__section-row">
                <td colSpan={3}>{sec.section}</td>
              </tr>
              {sec.rows.map((r) => (
                <tr key={r.action}>
                  <td>{r.action}</td>
                  <td style={{ color: "var(--accent-text)", fontWeight: 600 }}>{r.credits}</td>
                  <td className="approvals-table__meta">{r.output}</td>
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
      <p className="stub-page__note" style={{ margin: 0, padding: "12px 14px", borderTop: "1px solid var(--border)" }}>
        Example campaign: 1 MagicReel HD + 5,000 HCPs via WhatsApp — 5,000 + (5,000 × 2) = 15,000 credits consumed.
      </p>
    </div>
  );
}

function BillingTab() {
  const [view, setView] = useState<"usage" | "buy">("usage");
  return (
    <div data-hl="billing:highlight" data-hl-cue="spotlight">
      <div className="billing-banner">
        <div className="billing-banner__copy">
          <span className="billing-banner__tag">Credits & billing</span>
          <h2>Manage top-ups and platform consumption in one place.</h2>
        </div>
        <div className="billing-banner__usage-card">
          <div className="billing-banner__usage-head">
            <span className="field-label">Credit usage</span>
            <span className="stub-page__note">76% consumed</span>
          </div>
          <div className="billing-banner__usage-stats">
            <div><span className="field-label">Used</span><p style={{ margin: 0 }}>1,97,611</p></div>
            <div><span className="field-label">Available</span><p style={{ margin: 0, color: "var(--accent-text)" }}>62,389</p></div>
            <div><span className="field-label">Total</span><p style={{ margin: 0 }}>2,60,000</p></div>
          </div>
          <div className="dossier-detail__progress-bar" style={{ margin: "10px 0 0" }}>
            <div style={{ width: "76%" }} />
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, margin: "14px 0" }}>
        <div className="card" style={{ padding: 18 }}>
          <span className="field-label">Current credit pool</span>
          <p style={{ margin: "6px 0 2px", fontSize: 24, fontWeight: 700 }}>2,60,000</p>
          <p className="stub-page__note" style={{ margin: 0 }}>1,97,611 already consumed</p>
        </div>
        <div className="card" style={{ padding: 18 }}>
          <span className="field-label">Therapy areas</span>
          <p style={{ margin: "6px 0 2px", fontSize: 24, fontWeight: 700 }}>1 enabled</p>
          <p className="stub-page__note" style={{ margin: 0 }}>Conditions and indications enabled for your workspace</p>
        </div>
      </div>

      <div className="tabs-row" style={{ marginBottom: 14 }}>
        <button className={`tab-item ${view === "usage" ? "tab-item--active" : ""}`} onClick={() => setView("usage")}>
          Credits & usage
        </button>
        <button className={`tab-item ${view === "buy" ? "tab-item--active" : ""}`} onClick={() => setView("buy")}>
          What credits buy you
        </button>
      </div>

      {view === "usage" ? (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table className="approvals-table">
            <thead>
              <tr>{["Top-up credits", "Price", "Price / credit", "Validity"].map((h) => <th key={h}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {TOP_UP_PACKS.map((p) => (
                <tr key={p.credits}>
                  <td>{p.credits}</td>
                  <td>{p.price}</td>
                  <td>{p.perCredit}</td>
                  <td>{p.validity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <CreditsTable />
      )}
    </div>
  );
}

function PlansTab() {
  const plans = [
    { name: "Pay-as-you-go", price: "Free", current: true, features: ["MagicReel HD video", "5 free edits per piece", "English, Hindi, +8 more"] },
    { name: "Growth", price: "₹19,999/mo", popular: true, features: ["Everything in Pay-as-you-go", "Digital Twin + MagicAvatar", "Brand Kit (single brand)", "+20% bonus credits"] },
    { name: "Enterprise", price: "Contact us", features: ["Everything in Growth", "Unlimited edits", "Multiple workspaces", "Volume credit packs"] },
  ];
  return (
    <div data-hl="plans:highlight" data-hl-cue="spotlight">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14 }}>
        {plans.map((p) => (
          <div key={p.name} className="card" style={{ padding: 18, border: p.popular ? "2px solid var(--accent)" : undefined }}>
            {p.popular && <span className="dossier-card__verified" style={{ color: "var(--accent-text)", background: "var(--accent-tint-08)" }}>Most popular</span>}
            {p.current && <span className="dossier-card__category">Current plan</span>}
            <h3 style={{ margin: "8px 0 2px" }}>{p.name}</h3>
            <p style={{ fontSize: 20, fontWeight: 700, margin: "0 0 12px" }}>{p.price}</p>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, lineHeight: 1.9, color: "#444" }}>
              {p.features.map((f) => <li key={f}>{f}</li>)}
            </ul>
            <button className={`btn ${p.popular ? "btn--primary" : ""}`} style={{ width: "100%", marginTop: 14 }}>
              {p.current ? "Your plan" : "Talk to us"}
            </button>
          </div>
        ))}
      </div>

      <p className="filter-bar__label" style={{ margin: "24px 0 10px" }}>What credits buy you</p>
      <CreditsTable />
    </div>
  );
}
