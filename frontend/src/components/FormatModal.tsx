import { useEffect } from "react";
import Icon from "./Icon";
import { MLR_INPUTS, STAGE_LABELS, TEAM_ROLES } from "../registry/contentStudio";
import type { ContentFormat } from "../registry/contentStudio";

interface FormatModalProps {
  format: ContentFormat;
  engineLabel: string;
  engineIcon: string;
  onClose: () => void;
}

export default function FormatModal({ format, engineLabel, engineIcon, onClose }: FormatModalProps) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const objectiveStage = format.stages.map((s) => STAGE_LABELS[s]).join(", ");
  const primaryAudience = format.audience.replace(/ · /g, " + ");
  const applyingCount = format.promo === "Non-promotional" ? MLR_INPUTS.filter((m) => !m.promoOnly).length : MLR_INPUTS.length;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <div className="modal__icon">
            <Icon name={engineIcon} size={20} />
          </div>
          <div className="modal__header-text">
            <div className="modal__eyebrow">{engineLabel.toUpperCase()}</div>
            <h2 className="modal__title">{format.title}</h2>
            <div className="modal__tool">
              {format.tool}
              {format.soon && <span className="modal__placeholder"> · placeholder name</span>}
            </div>
          </div>
          {format.soon && <span className="modal__soon-pill">SOON</span>}
          <button className="modal__close" onClick={onClose} aria-label="Close">
            <Icon name="x" size={16} />
          </button>
        </div>

        <div className="modal__body">
          <p className="modal__desc">{format.description}</p>

          <div className="modal__meta-row">
            <div className="modal__meta-item">
              <div className="modal__meta-label">Engine</div>
              <div className="modal__meta-value">{engineLabel}</div>
            </div>
            <div className="modal__meta-item">
              <div className="modal__meta-label">Primary Audience</div>
              <div className="modal__meta-value">{primaryAudience}</div>
            </div>
            <div className="modal__meta-item">
              <div className="modal__meta-label">Objective Stage</div>
              <div className="modal__meta-value">{objectiveStage}</div>
            </div>
            <div className="modal__meta-item">
              <div className="modal__meta-label">Promotional Class</div>
              <div className="modal__meta-value">{format.promo}</div>
            </div>
          </div>

          {format.samples && (
            <div className="modal__section">
              <div className="modal__section-head">
                <h3>Samples</h3>
                <span className="modal__section-sub">Made with {format.tool}</span>
              </div>
              <div className="modal__samples-row">
                {format.samples.map((s) => (
                  <div key={s.title} className="modal__sample-card">
                    <div className="modal__sample-thumb">
                      <span className="modal__sample-badge">{s.badge}</span>
                      <span className="modal__sample-play">
                        <Icon name="play" size={16} />
                      </span>
                      <span className="modal__sample-duration">{s.duration}</span>
                    </div>
                    <div className="modal__sample-title">{s.title}</div>
                    <div className="modal__sample-sub">
                      {s.subtitle} · {s.duration}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="modal__section">
            <div className="modal__section-head">
              <h3>How the team builds it</h3>
              <span className="modal__section-sub">Every one of the 30 formats runs this same team, in this order. Only the lead changes.</span>
            </div>
            <div className="modal__team-row">
              {TEAM_ROLES.map((r) => {
                const isLead = r.role === format.leadRole;
                return (
                  <div key={r.role} className={`modal__team-card ${isLead ? "modal__team-card--lead" : ""}`}>
                    {isLead && <span className="modal__lead-pill">LEAD</span>}
                    <div
                      className={`modal__avatar ${isLead ? "modal__avatar--lead" : ""}`}
                      style={{ background: isLead ? r.color : undefined }}
                    >
                      {r.initials}
                    </div>
                    <div className={`modal__team-role ${isLead ? "modal__team-role--lead" : ""}`} style={{ color: isLead ? r.color : undefined }}>
                      {r.role}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="modal__inputs-grid">
            <div>
              <h3>Required inputs</h3>
              <ul className="modal__input-list">
                {format.requiredInputs.map((i) => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
            </div>
            <div>
              <h3>
                MLR inputs, upstream <span className="modal__section-sub">generated in place</span>
              </h3>
              <ul className="modal__mlr-list">
                {MLR_INPUTS.map((m) => {
                  const applies = !m.promoOnly || format.promo !== "Non-promotional";
                  return (
                    <li key={m.label} className={applies ? "" : "modal__mlr-row--na"}>
                      <Icon name={applies ? "check-circle" : "minus"} size={15} />
                      <div>
                        <b>{m.label}</b>
                        <div className="modal__mlr-desc">{applies ? m.note : "n/a — non-promotional path"}</div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>

          <div className="modal__removes">
            <Icon name="clock" size={16} />
            <div>
              <b>Removes</b>
              <div className="modal__removes-text">{format.eliminates}</div>
            </div>
          </div>

          <p className="modal__summary">
            This asset is {format.promo.toLowerCase()}, so {applyingCount} of the 8 upstream MLR inputs apply.
          </p>
        </div>

        <div className="modal__footer">
          {format.soon ? (
            <button className="btn modal__cta modal__cta--soon" disabled>
              <Icon name="clock" size={14} /> Coming Soon
            </button>
          ) : (
            <button className="btn-primary modal__cta">Open {format.tool} Studio →</button>
          )}
        </div>
      </div>
    </div>
  );
}
