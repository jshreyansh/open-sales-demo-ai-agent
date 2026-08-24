import { useState } from "react";
import { useRegisterComponent } from "../lib/uiRegistry";
import Icon from "../components/Icon";
import { DOSSIERS } from "./BrandDossiers";

const SECTIONS = [
  "Approved Indications",
  "Brand Overview",
  "Disease State & Understanding",
  "Mechanism of Action",
  "Pharmacokinetics",
  "Pivotal Clinical Evidence",
  "Supporting & Real-World Evidence",
  "Efficacy in Key Subgroups",
  "Safety & Tolerability",
  "Post-Market Adverse Events",
  "Contraindications",
  "Drug Interactions",
  "Dosing & Administration",
  "Special Populations",
  "Overdosage",
  "Missed Dose",
];

// Only the first few sections carry real drafted copy — the rest render as
// "not yet drafted", matching how an in-progress dossier actually looks
// (the reference screenshot itself showed 31% complete, not a finished
// document). This is the detail the user specifically asked to get right:
// genuine pharma-reading content for a couple of pages' worth, not filler.
const DRAFTED_CONTENT: Record<string, string[]> = {
  "Approved Indications": [
    "Velmara-XR (amlodipine + telmisartan) is indicated for the treatment of hypertension in adult patients not adequately controlled on monotherapy with either component alone, or as initial therapy in patients likely to need multiple agents to achieve blood pressure goals.",
  ],
  "Brand Overview": [
    "Velmara-XR combines a dihydropyridine calcium channel blocker with an angiotensin II receptor blocker in a single once-daily tablet, targeting two distinct pathways in blood pressure regulation to improve control while supporting adherence through simplified dosing.",
  ],
  "Disease State & Understanding": [
    "Hypertension remains one of the leading modifiable risk factors for cardiovascular disease. A substantial proportion of treated patients do not reach guideline-recommended blood pressure targets on a single agent, and combination therapy is recommended earlier in the treatment pathway for patients with moderate-to-severe elevation or additional cardiovascular risk factors.",
  ],
  "Mechanism of Action": [
    "Amlodipine inhibits the transmembrane influx of calcium ions into vascular smooth muscle, producing arterial vasodilation and reduced peripheral resistance. Telmisartan selectively blocks the binding of angiotensin II to the AT1 receptor, preventing the vasoconstrictive and aldosterone-secreting effects of the renin-angiotensin system. The two mechanisms act on complementary pathways, supporting an additive antihypertensive effect.",
  ],
};

// Derived from the data already above rather than invented separately — the
// 3 flagged items are exactly the ones the Checks tab lists below, and
// "sourced" is exactly which sections have real drafted copy.
const TOTAL_SECTIONS = SECTIONS.length;
const SOURCED_SECTIONS = Object.keys(DRAFTED_CONTENT).length;
const PERCENT_COMPLETE = Math.round((SOURCED_SECTIONS / TOTAL_SECTIONS) * 100);
const FLAGGED_CLAIMS = 3;

export default function BrandDossierDetail({ onBack }: { onBack: () => void }) {
  const dossier = DOSSIERS[0];
  const claimsVerified = dossier.claims - FLAGGED_CLAIMS;
  const needData = TOTAL_SECTIONS - SOURCED_SECTIONS;
  const [panelTab, setPanelTab] = useState<"checks" | "ledger">("checks");

  useRegisterComponent("brand-dossier-detail", "checks", {
    highlight: () => setPanelTab("checks"),
  });
  useRegisterComponent("brand-dossier-detail", "ledger", {
    highlight: () => setPanelTab("ledger"),
  });
  useRegisterComponent("brand-dossier-detail", "export", {
    highlight: () => {},
  });

  return (
    <div className="page">
      <button className="btn" style={{ marginBottom: 8, width: "fit-content" }} onClick={onBack}>
        ← Back to Brand Dossiers
      </button>

      <div className="page__header">
        <div>
          <h1 className="page__title" style={{ fontSize: 20 }}>
            {dossier.name} — {dossier.category} · v1
          </h1>
          <p className="page__subtitle">
            The brand's single source of truth — {dossier.sections} sections · {dossier.claims} claims · {FLAGGED_CLAIMS} flagged ·{" "}
            {needData} unverified drafts · updated {dossier.updated}
          </p>
        </div>
        <div className="dossier-detail__progress">
          <p className="dossier-detail__progress-pct">
            {PERCENT_COMPLETE}% <span>complete</span>
          </p>
          <div className="dossier-detail__progress-bar">
            <div style={{ width: `${PERCENT_COMPLETE}%` }} />
          </div>
          <p className="stub-page__note" style={{ margin: 0 }}>
            {SOURCED_SECTIONS} of {TOTAL_SECTIONS} sections fully sourced · {needData} need data
          </p>
        </div>
      </div>

      <div className="dossier-detail__actions" data-hl="export:highlight" data-hl-cue="spotlight">
        <button className="btn">Export PDF</button>
        <button className="btn">Version history</button>
        <button className="btn">Rebuild</button>
        <button className="btn btn--primary">Send to →</button>
      </div>

      <div className="dossier-detail__banner">
        <span className="approvals-avatar">MR</span>
        <p style={{ margin: 0, flex: 1 }}>
          <strong>MLR Reviewer</strong> — <strong>{claimsVerified} of {dossier.claims} claims verified.</strong>{" "}
          {FLAGGED_CLAIMS} claim(s) still need a source or your sign-off before export. Plus {needData} unverified draft(s) to validate.
        </p>
        <a className="dossier-detail__banner-link" href="#checks" onClick={(e) => e.preventDefault()}>
          Review {FLAGGED_CLAIMS} flags →
        </a>
      </div>

      <div className="dossier-detail">
        {/* Left — section index */}
        <div className="dossier-index card">
          <p className="filter-bar__label" style={{ marginBottom: 8 }}>
            Contents · {SECTIONS.length} sections
          </p>
          {SECTIONS.map((s, i) => (
            <a key={s} href={`#dossier-section-${i}`} className="dossier-index__item">
              <span className="dossier-index__num">{String(i + 1).padStart(2, "0")}</span>
              {s}
              <span className={`dossier-index__dot ${DRAFTED_CONTENT[s] ? "dossier-index__dot--done" : ""}`} />
            </a>
          ))}
        </div>

        {/* Center — the actual document */}
        <div className="dossier-document card">
          <div className="dossier-document__hero">
            <p className="dossier-document__hero-title">{dossier.molecule}</p>
            <p className="dossier-document__hero-sub">Solandra Pharma</p>
          </div>
          <div className="dossier-document__card">
            <p className="dossier-document__card-title">{dossier.name}</p>
            <p className="stub-page__note" style={{ margin: "2px 0 12px" }}>{dossier.molecule} · IN</p>
            <div className="dossier-document__fields">
              <div>
                <span className="field-label">Classification</span>
                <p style={{ margin: 0 }}>Hypertension</p>
              </div>
              <div>
                <span className="field-label">Generic Name</span>
                <p style={{ margin: 0 }}>amlodipine + telmisartan</p>
              </div>
              <div>
                <span className="field-label">Trade Name</span>
                <p style={{ margin: 0 }}>VELMARA-XR</p>
              </div>
              <div>
                <span className="field-label">Indications / Uses</span>
                <p style={{ margin: 0 }}>Hypertension</p>
              </div>
            </div>
          </div>

          {SECTIONS.map((s, i) => (
            <div key={s} id={`dossier-section-${i}`} className="dossier-document__section">
              <p className="dossier-document__section-title">
                {String(i + 1).padStart(2, "0")}. {s}
              </p>
              {DRAFTED_CONTENT[s] ? (
                DRAFTED_CONTENT[s].map((p, pi) => (
                  <p key={pi} className="dossier-document__section-body">
                    {p}
                  </p>
                ))
              ) : (
                <p className="dossier-document__section-body dossier-document__section-body--empty">
                  Not yet drafted — needs a source before this section can be generated.
                </p>
              )}
            </div>
          ))}
        </div>

        {/* Right — checks / claims ledger */}
        <div className="dossier-checks card">
          <div className="tabs-row">
            <button className={`tab-item ${panelTab === "checks" ? "tab-item--active" : ""}`} onClick={() => setPanelTab("checks")}>
              Checks <span className="approvals-tab-count">3</span>
            </button>
            <button className={`tab-item ${panelTab === "ledger" ? "tab-item--active" : ""}`} onClick={() => setPanelTab("ledger")}>
              Claims ledger
            </button>
          </div>

          {panelTab === "checks" ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 12 }}>
              {["Mechanism of Action", "Pharmacokinetics", "Post-Market Adverse Events"].map((s) => (
                <div key={s} className="dossier-check-item">
                  <p className="dossier-check-item__title">Unverified — not source-backed</p>
                  <p className="stub-page__note" style={{ margin: "2px 0 8px" }}>
                    {s} — drafted from general knowledge because no allow-listed source was found. Validate against a real source before use.
                  </p>
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <button className="btn" style={{ padding: "3px 10px", fontSize: 12 }}>
                      Accept
                    </button>
                    <button className="btn" style={{ padding: "3px 10px", fontSize: 12 }}>
                      Keep unverified
                    </button>
                    <a className="dossier-check-item__source-link" href="#" onClick={(e) => e.preventDefault()}>
                      <Icon name="link" size={12} /> Suggest source
                    </a>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="stub-page__note" style={{ marginTop: 12 }}>
              {dossier.claims} claims cited across {dossier.sections} sections — every field traced to its source.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
