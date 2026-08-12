import { useEffect, useRef, useState } from "react";
import { formatSlug, MAGIC_ENGINES, STAGE_LABELS, type ContentFormat, type MagicEngine, type Stage } from "../registry/contentStudio";
import { registerComponent, unregisterComponent, useRegisterComponent } from "../lib/uiRegistry";
import { applyPulse, useHighlight } from "../lib/useHighlight";
import Icon from "../components/Icon";
import FormatModal from "../components/FormatModal";

interface ContentStudioProps {
  initialTab?: string;
  onOpenStudio: (studioId: string) => void;
}

const AUDIENCES = ["HCP", "Patient", "Payer"];
const totalFormats = MAGIC_ENGINES.reduce((sum, e) => sum + e.formats.length, 0);

export default function ContentStudio({ initialTab, onOpenStudio }: ContentStudioProps) {
  const [tab, setTab] = useState(initialTab ?? "All");
  const [objective, setObjective] = useState<Stage | null>(null);
  const [audience, setAudience] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ format: ContentFormat; engine: MagicEngine } | null>(null);

  // One cue instance per engine tab (fixed, known set — same pattern as
  // Dashboard's insights/activeCampaigns) so the agent's tab-click actions
  // can pulse the actual tab button that was "clicked". Also the fallback
  // target for a format-card open when the card itself isn't mounted yet
  // (see the format-card ref map + open callback below).
  const videoTabCue = useHighlight<HTMLButtonElement>();
  const aidTabCue = useHighlight<HTMLButtonElement>();
  const mailTabCue = useHighlight<HTMLButtonElement>();
  const canvasTabCue = useHighlight<HTMLButtonElement>();
  const docTabCue = useHighlight<HTMLButtonElement>();
  const TAB_CUES: Record<string, ReturnType<typeof useHighlight<HTMLButtonElement>>> = {
    Video: videoTabCue,
    Aid: aidTabCue,
    Mail: mailTabCue,
    Canvas: canvasTabCue,
    Doc: docTabCue,
  };

  // A dynamic ref map, not fixed hook instances — 30 possible targets, and
  // only whichever are currently visible under the active tab/filter are
  // ever actually mounted. Populated by each rendered format-card's ref
  // callback below.
  const formatCardRefs = useRef<Map<string, HTMLButtonElement>>(new Map());

  useRegisterComponent("content-studio", "video-tab", { click: () => { videoTabCue.pulse(); setTab("Video"); } });
  useRegisterComponent("content-studio", "aid-tab", { click: () => { aidTabCue.pulse(); setTab("Aid"); } });
  useRegisterComponent("content-studio", "mail-tab", { click: () => { mailTabCue.pulse(); setTab("Mail"); } });
  useRegisterComponent("content-studio", "canvas-tab", { click: () => { canvasTabCue.pulse(); setTab("Canvas"); } });
  useRegisterComponent("content-studio", "doc-tab", { click: () => { docTabCue.pulse(); setTab("Doc"); } });

  // Every individual format gets its own registry component (id = its
  // MagicXxx tool name, slugified — see backend/src/agent/registry.py for
  // the matching Python-side mirror) so the agent can open one specific
  // format's modal directly, not just switch tabs. Registered via the raw
  // functions (not useRegisterComponent) in a single effect, since these
  // must stay registered regardless of which tab/filter is active —
  // calling a hook 30 times in a loop would also violate rules of hooks.
  useEffect(() => {
    const ids: string[] = [];
    for (const engine of MAGIC_ENGINES) {
      for (const format of engine.formats) {
        const id = formatSlug(format.tool);
        ids.push(id);
        registerComponent("content-studio", id, {
          open: () => {
            // The card is only mounted if it was already visible under the
            // tab/filter state THIS render — switching tab below doesn't
            // mount it until next render, so there's genuinely nothing to
            // pulse yet in that case. Falling back to the tab button (always
            // mounted) keeps the "something visibly reacted" cue honest
            // instead of silently doing nothing — the modal opening right
            // after is the rest of the visual confirmation.
            const card = formatCardRefs.current.get(id);
            if (card) {
              applyPulse(card);
            } else {
              TAB_CUES[engine.tabId]?.pulse();
            }
            setTab(engine.tabId);
            setSelected({ format, engine });
          },
        });
      }
    }
    return () => {
      for (const id of ids) unregisterComponent("content-studio", id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
          <button
            key={t}
            ref={TAB_CUES[t]?.ref}
            className={`tab-item ${tab === t ? "tab-item--active" : ""}`}
            onClick={() => setTab(t)}
          >
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
              <span className="engine-section__icon">
                <Icon name={engine.icon} size={15} />
              </span>
              <h3 className="engine-section__title">{engine.label}</h3>
              <span className="engine-section__desc">{engine.description}</span>
              {soonCount > 0 && <span className="engine-section__soon">{soonCount} coming soon</span>}
            </div>
            <div className="format-grid">
              {formats.map((f) => (
                <button
                  key={f.title}
                  ref={(el) => {
                    const id = formatSlug(f.tool);
                    if (el) formatCardRefs.current.set(id, el);
                    else formatCardRefs.current.delete(id);
                  }}
                  className="format-card"
                  onClick={() => setSelected({ format: f, engine })}
                >
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
                </button>
              ))}
            </div>
          </div>
        );
      })}

      {selected && (
        <FormatModal
          format={selected.format}
          engineLabel={selected.engine.label}
          engineIcon={selected.engine.icon}
          onClose={() => setSelected(null)}
          onOpenStudio={(studioId) => {
            setSelected(null);
            onOpenStudio(studioId);
          }}
        />
      )}
    </div>
  );
}
