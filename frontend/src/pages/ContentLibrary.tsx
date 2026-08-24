import { useState } from "react";
import { useRegisterComponent } from "../lib/uiRegistry";

interface LibraryItem {
  id: string;
  title: string;
  engine: string;
  audience: string;
  video: string;
  script: string;
}

// The Content Library holds every video generated on the platform so far —
// which today is exactly two, both real showcase pieces already produced
// through SwishX. Deliberately not padded out with placeholder rows: the
// count here should mean something, not manufacture a fake library size.
const ITEMS: LibraryItem[] = [
  {
    id: "tecentriq-reel",
    title: "Tecentriq — MagicReel showcase",
    engine: "MagicReel™",
    audience: "Doctor / HCP · Oncology",
    video: "/videos/tecentriq-reel.mp4",
    script:
      "Tecentriq (atezolizumab) — a PD-L1 checkpoint inhibitor. This is one of the real, finished pieces SwishX has generated: a short-form MLR-ready video built straight from the brand's approved dossier, claims and references already attached.",
  },
  {
    id: "avatar-showcase",
    title: "Digital Twin — MagicAvatar showcase",
    engine: "MagicAvatar™",
    audience: "Patient · Adherence",
    video: "/videos/avatar-showcase.mp4",
    script:
      "A Digital Twin presenter generated from a physician's own photo and voice sample, lip-synced to a patient-facing adherence message — produced end to end on the platform, not a mockup.",
  },
];

export default function ContentLibrary() {
  const [preview, setPreview] = useState<LibraryItem | null>(null);

  useRegisterComponent("content-library", "grid", {
    highlight: () => {},
  });
  useRegisterComponent("content-library", "preview", {
    open: () => setPreview(ITEMS[0]),
  });

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <h1 className="page__title">Content Library</h1>
          <p className="page__subtitle">{ITEMS.length} items · every video generated on the platform so far</p>
        </div>
      </div>

      <div className="library-grid" data-hl="grid:highlight" data-hl-cue="spotlight">
        {ITEMS.map((item) => (
          <div key={item.id} className="library-card">
            <button className="library-card__thumb" onClick={() => setPreview(item)} aria-label={`Preview ${item.title}`}>
              <video src={item.video} muted playsInline preload="metadata" />
              <span className="library-card__engine">{item.engine}</span>
            </button>
            <div className="library-card__body">
              <p className="library-card__title">{item.title}</p>
              <p className="stub-page__note" style={{ margin: "2px 0 8px" }}>{item.audience}</p>
              <button className="btn" style={{ width: "100%" }} onClick={() => setPreview(item)}>
                ▶ Preview
              </button>
            </div>
          </div>
        ))}
      </div>

      {preview && (
        <div className="modal-overlay" onClick={() => setPreview(null)}>
          <div className="modal library-preview-modal" onClick={(e) => e.stopPropagation()}>
            <div className="library-preview-modal__header">
              <span className="dossier-card__category">{preview.engine}</span>
              <p style={{ margin: 0, fontWeight: 700 }}>{preview.title}</p>
              <button className="btn" style={{ marginLeft: "auto" }} onClick={() => setPreview(null)}>
                ✕
              </button>
            </div>
            <div className="library-preview-modal__body">
              <video src={preview.video} controls autoPlay className="library-preview-modal__video" />
              <div>
                <p className="filter-bar__label" style={{ marginBottom: 6 }}>Script</p>
                <p style={{ fontSize: 13, lineHeight: 1.6, color: "#333" }}>{preview.script}</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
