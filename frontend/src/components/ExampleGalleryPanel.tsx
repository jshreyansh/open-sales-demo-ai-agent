import { useEffect, useState } from "react";
import Icon from "./Icon";
import AssetVideoPlayer from "./studio/AssetVideoPlayer";
import { GALLERY_EXAMPLES, GALLERY_TAGLINE } from "../registry/exampleGallery";

interface ExampleGalleryPanelProps {
  onClose: () => void;
}

// Which icon represents each config field -- kept here rather than in the
// data file, since it's a display concern, not something about the example
// itself.
const CONFIG_ICON: Record<string, string> = {
  Audience: "users",
  Purpose: "target",
  Voice: "waveform",
  Language: "globe",
};

// A real blocking modal (near-black dimmed backdrop, liquid-glass card),
// rendered at the top level of MeetingShell and position:fixed to the
// viewport (see its mount comment there).
//
// Layout: two columns -- a large portrait video (2:3, the star of the modal)
// and an info column that fills the video's height, with the spec grid
// bottom-aligned against it. The prev/next arrows and the slide counter live
// on the backdrop outside the card, the way a real lightbox does; the award
// badge and the close button sit inside the card's top edge.
//
// This is the one meeting surface a visitor can actually touch themselves:
// real pointer-events throughout (unlike .meet__stage-inner, a "screen share"
// only the agent drives), plus Esc to close, arrow keys to navigate, and
// backdrop-click to dismiss. See runtime.py's instruction 13 for when the
// agent opens it.
export default function ExampleGalleryPanel({ onClose }: ExampleGalleryPanelProps) {
  const [index, setIndex] = useState(0);
  // Which way the last move went, so the incoming slide enters from the side
  // you'd expect rather than always the same one. Without it the change is a
  // hard content swap — the video remounts (new src) and the whole info
  // column repaints in a single frame.
  const [dir, setDir] = useState<"next" | "prev">("next");
  const example = GALLERY_EXAMPLES[index];

  function goPrev() {
    setDir("prev");
    setIndex((i) => (i - 1 + GALLERY_EXAMPLES.length) % GALLERY_EXAMPLES.length);
  }
  function goNext() {
    setDir("next");
    setIndex((i) => (i + 1) % GALLERY_EXAMPLES.length);
  }

  // Both handlers below use setIndex's updater form, so this effect never
  // needs to re-bind on index changes -- onClose is the only real dependency.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft") goPrev();
      if (e.key === "ArrowRight") goNext();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="meet__gallery-overlay" onClick={onClose}>
      <button
        className="meet__gallery-edge-arrow meet__gallery-edge-arrow--prev"
        onClick={(e) => {
          e.stopPropagation();
          goPrev();
        }}
        aria-label="Previous example"
      >
        <Icon name="chevron-left" size={24} />
      </button>

      <div className="meet__gallery-modal" onClick={(e) => e.stopPropagation()}>
        <button className="meet__gallery-close" onClick={onClose} aria-label="Close example gallery">
          <Icon name="x" size={19} />
        </button>

        <div
          className={`meet__gallery-modal-video meet__gallery-slide meet__gallery-slide--${dir}`}
          key={`v-${example.id}`}
        >
          <div className="meet__gallery-duration-badge">
            <span className="meet__gallery-duration-dot" />
            {example.duration}
          </div>
          <AssetVideoPlayer key={example.id} src={example.videoUrl} />
        </div>

        <div
          className={`meet__gallery-modal-info meet__gallery-slide meet__gallery-slide--${dir}`}
          key={`i-${example.id}`}
        >
          {/* In the info column's flow, directly above the heading — so it
              stays aligned with it at any card width (see the CSS note). */}
          <div className="meet__gallery-badge">
            <div className="meet__gallery-badge-inner">
              <div className="meet__gallery-badge-medal">
                <Icon name="trophy" size={15} className="meet__gallery-badge-icon" />
                <span className="meet__gallery-badge-spark meet__gallery-badge-spark--a" />
                <span className="meet__gallery-badge-spark meet__gallery-badge-spark--b" />
              </div>
              <span className="meet__gallery-badge-text">
                <span className="meet__gallery-badge-kicker">Hall of fame</span>
                <span className="meet__gallery-badge-label">Best Content Showcase</span>
              </span>
            </div>
          </div>

          <div className="meet__gallery-format">{example.format}</div>
          <p className="meet__gallery-tagline">{GALLERY_TAGLINE}</p>

          <div className="meet__gallery-highlight">
            <div className="meet__gallery-highlight-head">
              <div className="meet__gallery-highlight-icon">
                <Icon name="film" size={23} />
              </div>
              <div className="meet__gallery-highlight-titles">
                <div className="meet__gallery-kicker">Featured generation</div>
                <div className="meet__gallery-title">{example.title}</div>
              </div>
            </div>
            <p className="meet__gallery-desc">{example.description}</p>
          </div>

          <div className="meet__gallery-config">
            {example.configs.map((c) => (
              <div key={c.label} className="meet__gallery-config-item">
                <div className="meet__gallery-config-label">
                  <Icon name={CONFIG_ICON[c.label]} size={18} />
                  {c.label}
                </div>
                <div className="meet__gallery-chips">
                  {(Array.isArray(c.value) ? c.value : [c.value]).map((v) => (
                    <span key={v} className="meet__gallery-chip">
                      {v}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <button
        className="meet__gallery-edge-arrow meet__gallery-edge-arrow--next"
        onClick={(e) => {
          e.stopPropagation();
          goNext();
        }}
        aria-label="Next example"
      >
        <Icon name="chevron-right" size={24} />
      </button>
    </div>
  );
}
