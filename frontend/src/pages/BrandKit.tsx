import { useEffect, useState } from "react";
import { getBrandKit, saveBrandKit } from "../lib/api";
import { useRegisterComponent } from "../lib/uiRegistry";
import { useHighlight } from "../lib/useHighlight";
import type { BrandKitData } from "../lib/types";

type PaletteKey = keyof BrandKitData["palette"];

const PALETTE_FIELDS: { key: PaletteKey; label: string }[] = [
  { key: "primary", label: "Primary" },
  { key: "accent", label: "Accent" },
  { key: "calloutBackground", label: "Callout Background" },
  { key: "text", label: "Text" },
];

export default function BrandKit() {
  const [data, setData] = useState<BrandKitData | null>(null);
  const [original, setOriginal] = useState<BrandKitData | null>(null);
  const [saving, setSaving] = useState(false);
  const logo = useHighlight();
  const palette = useHighlight();

  useEffect(() => {
    getBrandKit().then((d) => {
      setData(d);
      setOriginal(d);
    });
  }, []);

  useRegisterComponent("brand-kit", "logo", { highlight: logo.spotlight });
  useRegisterComponent("brand-kit", "palette", { highlight: palette.spotlight });

  if (!data) {
    return (
      <div className="page">
        <p className="stub-page__note">Loading brand kit…</p>
      </div>
    );
  }

  function updatePalette(key: PaletteKey, value: string) {
    setData((d) => (d ? { ...d, palette: { ...d.palette, [key]: value } } : d));
  }

  async function handleSave() {
    if (!data) return;
    setSaving(true);
    try {
      const saved = await saveBrandKit(data);
      setData(saved);
      setOriginal(saved);
    } finally {
      setSaving(false);
    }
  }

  function handleReset() {
    setData(original);
  }

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <h1 className="page__title">Brand Kit</h1>
          <p className="page__subtitle">Set your workspace brand once — every generated asset picks it up.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn" onClick={handleReset}>
            Reset
          </button>
          <button className="btn btn--primary" onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>

      <div className="brand-kit">
        <div>
          <div className="card" style={{ marginBottom: 16 }} ref={logo.ref}>
            <h3 style={{ marginTop: 0, marginBottom: 4 }}>Logo</h3>
            <p className="stub-page__note" style={{ marginTop: 0, fontSize: 12 }}>
              Shared with Settings › Account — update it here or there and both stay in sync.
            </p>
            <div className="logo-box">
              <div className="logo-box__preview">{data.logoInitials}</div>
              <div>
                <button className="btn">Replace logo</button>
                <p className="stub-page__note" style={{ fontSize: 11, marginTop: 6 }}>
                  PNG, JPEG, WebP, GIF, SVG or HEIC · up to 15 MB
                </p>
              </div>
            </div>
          </div>

          <div className="card" style={{ marginBottom: 16 }} ref={palette.ref}>
            <h3 style={{ marginTop: 0, marginBottom: 12 }}>Palette</h3>
            <div className="brand-kit__field-group">
              {PALETTE_FIELDS.map((f) => (
                <div key={f.key}>
                  <label className="field-label">{f.label}</label>
                  <div className="color-field">
                    <input
                      type="color"
                      className="color-field__swatch"
                      value={data.palette[f.key]}
                      onChange={(e) => updatePalette(f.key, e.target.value)}
                    />
                    <input
                      className="color-field__input"
                      value={data.palette[f.key]}
                      onChange={(e) => updatePalette(f.key, e.target.value)}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0, marginBottom: 12 }}>Typography</h3>
            <div className="brand-kit__field-group">
              <div>
                <label className="field-label">Heading Font</label>
                <select className="select-field" value={data.typography.headingFont} onChange={() => {}}>
                  <option>{data.typography.headingFont}</option>
                </select>
              </div>
              <div>
                <label className="field-label">Body Font</label>
                <select className="select-field" value={data.typography.bodyFont} onChange={() => {}}>
                  <option>{data.typography.bodyFont}</option>
                </select>
              </div>
            </div>
          </div>
        </div>

        <div>
          <p className="filter-bar__label" style={{ marginBottom: 8 }}>
            Live Preview
          </p>
          <div className="preview-card">
            <div className="preview-card__banner" style={{ background: data.palette.primary, color: "white" }}>
              <p className="preview-card__banner-title">{data.preview.title}</p>
              <p className="preview-card__banner-subtitle">{data.preview.subtitle}</p>
            </div>
            <div className="preview-card__body">
              <h4 className="preview-card__heading">{data.preview.heading}</h4>
              <p className="preview-card__text">{data.preview.body}</p>
              <div
                className="preview-card__callout"
                style={{ background: data.palette.calloutBackground, borderColor: data.palette.text, color: data.palette.text }}
              >
                <strong>{data.preview.calloutLabel}</strong>
                <div>{data.preview.calloutBody}</div>
              </div>
            </div>
          </div>

          <div className="swatch-row">
            {PALETTE_FIELDS.map((f) => (
              <div key={f.key} className="swatch">
                <div className="swatch__color" style={{ background: data.palette[f.key] }} />
                <div className="swatch__label">{f.label.toUpperCase()}</div>
                <div className="swatch__hex">{data.palette[f.key]}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
