export interface NavItem {
  id: string;
  label: string;
  route: string;
  status: "available" | "soon";
}

export interface NavGroup {
  id: string;
  label: string | null;
  items: NavItem[];
}

/**
 * Mirrors the real ContentIQ (contentiq.swishx.com/dashboard) sidebar,
 * inspected 2026-08-05. Top-level nav only — flows inside each page are
 * out of scope until we build them out individually.
 */
export const NAV_REGISTRY: NavGroup[] = [
  {
    id: "root",
    label: null,
    items: [
      { id: "dashboard", label: "Dashboard", route: "/dashboard", status: "available" },
      { id: "analytics", label: "Analytics", route: "/analytics/overview", status: "available" },
    ],
  },
  {
    id: "create",
    label: "Create",
    items: [
      { id: "content-studio", label: "Content Studio", route: "/studio", status: "available" },
      { id: "magic-video", label: "Magic Video", route: "/studio?e=video", status: "available" },
      { id: "magic-aid", label: "Magic Aid", route: "/studio?e=aid", status: "soon" },
      { id: "magic-mail", label: "Magic Mail", route: "/studio?e=mail", status: "soon" },
      { id: "magic-canvas", label: "Magic Canvas", route: "/studio?e=canvas", status: "available" },
      { id: "magic-doc", label: "Magic Doc", route: "/studio?e=doc", status: "soon" },
    ],
  },
  {
    id: "library",
    label: "Library",
    items: [
      { id: "brand-dossiers", label: "Brand Dossiers", route: "/studio/dossier", status: "available" },
      { id: "brand-kit", label: "Brand Kit", route: "/brand-library", status: "available" },
      { id: "content-library", label: "Content Library", route: "/content-library", status: "available" },
      { id: "claims-library", label: "Claims Library", route: "#", status: "soon" },
      { id: "templates", label: "Templates", route: "/templates", status: "available" },
    ],
  },
  {
    id: "compliance",
    label: "Compliance",
    items: [{ id: "mlr-review", label: "MLR Review", route: "/approvals", status: "available" }],
  },
  {
    id: "activate",
    label: "Activate",
    items: [
      { id: "campaigns", label: "Campaigns", route: "/campaigns", status: "available" },
      { id: "audience", label: "Audience", route: "/audience", status: "available" },
      { id: "re-engage", label: "Re-engage", route: "#", status: "soon" },
    ],
  },
];
