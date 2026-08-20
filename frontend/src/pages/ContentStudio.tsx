import { useEffect, useRef, useState } from "react";
import { formatSlug, MAGIC_ENGINES, STAGE_LABELS, type ContentFormat, type MagicEngine, type Stage } from "../registry/contentStudio";
import { registerComponent, unregisterComponent, useRegisterComponent } from "../lib/uiRegistry";
import { registerBeforeArm, setFallbackGroups } from "../lib/highlightBridge";
import Icon from "../components/Icon";
import FormatModal from "../components/FormatModal";

interface ContentStudioProps {
  initialTab?: string;
  onOpenStudio: (studioId: string) => void;
}

const AUDIENCES = ["HCP", "Patient", "Payer"];
const totalFormats = MAGIC_ENGINES.reduce((sum, e) => sum + e.formats.length, 0);

// Which always-mounted tab button stands in for a given format card when
// the card itself isn't rendered yet (wrong tab/filter active) -- one small
// table instead of the inline if/else this used to be, set once (not per
// element, not per render) via highlightBridge.ts's shared resolver. Every
// one of the 30 formats maps to its own engine's tab.
const FORMAT_TAB_GROUPS: Record<string, string> = Object.fromEntries(
  MAGIC_ENGINES.flatMap((engine) => engine.formats.map((f) => [`${formatSlug(f.tool)}:open`, `tab:${engine.tabId}`])),
);
setFallbackGroups("content-studio", FORMAT_TAB_GROUPS);

// A previous preview modal closing out, and the destination tab's own grid
// getting a beat to actually be seen, before the next preview opens --
// without this, opening a second (or a different-tab) format fired the tab
// switch and the modal open in the exact same instant as the first, which
// read as the content just swapping/flickering rather than the agent
// closing one preview and moving deliberately to the next.
const CLOSE_PAUSE_MS = 400;
const TAB_SETTLE_MS = 700;

export default function ContentStudio({ initialTab, onOpenStudio }: ContentStudioProps) {
  const [tab, setTab] = useState(initialTab ?? "All");
  const [objective, setObjective] = useState<Stage | null>(null);
  const [audience, setAudience] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ format: ContentFormat; engine: MagicEngine } | null>(null);

  // The format-open handlers below are registered once (empty-deps effect,
  // see below) and must still read the CURRENT tab/selected at call time to
  // decide whether a close/tab-switch pause is needed -- refs mirrored every
  // render, rather than adding tab/selected to that effect's deps, which
  // would re-register (and briefly un-register) all 30 formats on every tab
  // change instead of once.
  const tabRef = useRef(tab);
  tabRef.current = tab;
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  // Pending close/tab-switch timers for whichever open sequence is
  // currently in flight -- cleared on a fresh open call (so a rapid second
  // action doesn't layer on top of a still-running sequence) and on unmount.
  const sequenceTimers = useRef<number[]>([]);
  useEffect(() => {
    return () => {
      for (const id of sequenceTimers.current) window.clearTimeout(id);
    };
  }, []);

  // Runs BEFORE the next content-studio highlight arms/holds -- see
  // registerBeforeArm's own docstring. Closes whatever preview modal is
  // currently open right away, so by the time the NEXT format's highlight
  // is actually visible (a moment later, once the transition finishes),
  // the old modal is already gone instead of still sitting on top of it
  // for the whole 2.2s hold.
  useEffect(() => {
    registerBeforeArm("content-studio", () => {
      if (selectedRef.current !== null) setSelected(null);
    });
  }, []);

  useRegisterComponent("content-studio", "video-tab", { click: () => setTab("Video") });
  useRegisterComponent("content-studio", "aid-tab", { click: () => setTab("Aid") });
  useRegisterComponent("content-studio", "mail-tab", { click: () => setTab("Mail") });
  useRegisterComponent("content-studio", "canvas-tab", { click: () => setTab("Canvas") });
  useRegisterComponent("content-studio", "doc-tab", { click: () => setTab("Doc") });

  // Every individual format gets its own registry component (id = its
  // MagicXxx tool name, slugified — see backend/src/agent/registry.py for
  // the matching Python-side mirror) so the agent can open one specific
  // format's modal directly, not just switch tabs. Registered via the raw
  // functions (not useRegisterComponent) in a single effect, since these
  // must stay registered regardless of which tab/filter is active —
  // calling a hook 30 times in a loop would also violate rules of hooks.
  // The visual cue (real card if mounted, else the tab button) is resolved
  // generically by highlightBridge.ts before this handler ever runs -- it
  // only needs to perform the actual state change.
  useEffect(() => {
    const ids: string[] = [];
    for (const engine of MAGIC_ENGINES) {
      for (const format of engine.formats) {
        const id = formatSlug(format.tool);
        ids.push(id);
        registerComponent("content-studio", id, {
          open: () => {
            for (const timerId of sequenceTimers.current) window.clearTimeout(timerId);
            sequenceTimers.current = [];

            const currentlyOpen = selectedRef.current !== null;
            const switchingTab = tabRef.current !== engine.tabId;
            const openThis = () => setSelected({ format, engine });

            if (currentlyOpen) setSelected(null);

            if (!currentlyOpen && !switchingTab) {
              openThis();
              return;
            }
            const afterClose = window.setTimeout(
              () => {
                if (!switchingTab) {
                  openThis();
                  return;
                }
                setTab(engine.tabId);
                const afterTabSettle = window.setTimeout(openThis, TAB_SETTLE_MS);
                sequenceTimers.current.push(afterTabSettle);
              },
              currentlyOpen ? CLOSE_PAUSE_MS : 0
            );
            sequenceTimers.current.push(afterClose);
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
      {/* Headline only, no supporting copy. This page is narrated live — the
          prose underneath every heading competed with what the presenter was
          already saying, and pushed the actual format grid below the fold. */}
      <h1 className="page__title page__title--solo">Content Studio</h1>

      <div className="hero-banner">
        <div className="hero-banner__text">
          <h2>
            Get medical-grade, MLR-ready content in <span style={{ color: "var(--accent)" }}>minutes, not weeks</span>.
          </h2>
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
            data-hl={t === "All" ? undefined : `${t.toLowerCase()}-tab:click`}
            data-hl-group={`tab:${t}`}
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
              {/* engine.description is intentionally not rendered — the cards
                  below already say what the engine makes. It stays on the
                  registry record for the format modal / future surfaces. */}
              {soonCount > 0 && <span className="engine-section__soon">{soonCount} coming soon</span>}
            </div>
            <div className="format-grid">
              {formats.map((f) => (
                // A SOON format is a genuinely unbuilt one, so its card is a
                // real `disabled` button: unclickable and out of the tab
                // order, not just styled to look inert. This only closes the
                // human path — the agent opens a format by calling the
                // registered `open` handler directly (see the effect above),
                // which never goes through a DOM click, so a scripted
                // walkthrough can still preview an unreleased format.
                <button
                  key={f.title}
                  data-hl={`${formatSlug(f.tool)}:open`}
                  className={`format-card ${f.soon ? "format-card--soon" : ""}`}
                  disabled={f.soon}
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
