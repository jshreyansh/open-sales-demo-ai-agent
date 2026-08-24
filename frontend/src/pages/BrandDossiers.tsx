import { useRegisterComponent } from "../lib/uiRegistry";

export interface DossierSummary {
  id: string;
  name: string;
  molecule: string;
  category: string;
  sections: number;
  claims: number;
  updated: string;
}

// Two dummy dossiers, invented names (not the reference screenshot's) —
// enough to show the grid pattern without manufacturing a large fake
// library. The detail page always opens the first one; see
// BrandDossierDetail.tsx.
export const DOSSIERS: DossierSummary[] = [
  {
    id: "velmara-xr",
    name: "Velmara-XR",
    molecule: "Amlodipine + Telmisartan",
    category: "HCP Scientific",
    sections: 16,
    claims: 22,
    updated: "Aug 20, 2026",
  },
  {
    id: "zynocort-d",
    name: "Zynocort-D",
    molecule: "Fluticasone + Azelastine",
    category: "Commercial dossier",
    sections: 14,
    claims: 58,
    updated: "Aug 11, 2026",
  },
];

export default function BrandDossiers({ onOpen }: { onOpen: (dossierId: string) => void }) {
  useRegisterComponent("brand-dossiers", "grid", {
    highlight: () => {},
    // The detail page always shows DOSSIERS[0] (see BrandDossierDetail.tsx),
    // so opening "a" dossier always means opening that one.
    open: () => onOpen(DOSSIERS[0].id),
  });

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <h1 className="page__title">Brand Dossiers</h1>
          <p className="page__subtitle">A brand's master knowledge base — the single source of truth, kept complete and MLR-ready.</p>
        </div>
        <button className="btn btn--primary">+ Create Brand Dossier</button>
      </div>

      <p className="filter-bar__label" style={{ marginBottom: 10 }}>
        Existing dossiers &nbsp;{DOSSIERS.length}
      </p>

      <div className="dossier-grid" data-hl="grid:highlight" data-hl-cue="spotlight">
        {DOSSIERS.map((d) => (
          <button key={d.id} className="dossier-card" onClick={() => onOpen(d.id)}>
            <div className="dossier-card__head">
              <span className="dossier-card__icon">📄</span>
              <span className="dossier-card__verified">Verified</span>
            </div>
            <p className="dossier-card__name">{d.name}</p>
            <p className="dossier-card__molecule">{d.molecule}</p>
            <span className="dossier-card__category">{d.category}</span>
            <p className="dossier-card__meta">
              {d.sections} sections · {d.claims} claims cited
            </p>
            <div className="dossier-card__footer">
              <span className="stub-page__note">Updated {d.updated}</span>
              <span className="dossier-card__open">Open →</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
