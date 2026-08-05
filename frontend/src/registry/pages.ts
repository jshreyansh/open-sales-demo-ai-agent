export interface NavItem {
  id: string;
  label: string;
  route: string;
  status: "available" | "soon";
  icon: string;
  indent?: boolean;
}

export interface NavGroup {
  id: string;
  label: string | null;
  items: NavItem[];
}

/**
 * Mirrors the real ContentIQ (contentiq.swishx.com) sidebar — grouping and
 * icons matched against real product screenshots (both expanded and
 * collapsed states). MLR Review sits alone under its own "Compliance" group,
 * separate from "Activate".
 * Top-level nav only — flows inside each page are out of scope until built
 * individually.
 */
export const NAV_REGISTRY: NavGroup[] = [
  {
    id: "overview",
    label: "Overview",
    items: [
      { id: "dashboard", label: "Dashboard", route: "/dashboard", status: "available", icon: "dashboard" },
      { id: "analytics", label: "Analytics", route: "/analytics/overview", status: "available", icon: "bar-chart" },
    ],
  },
  {
    id: "create",
    label: "Create",
    items: [
      { id: "content-studio", label: "Content Studio", route: "/studio", status: "available", icon: "sparkles" },
      { id: "magic-video", label: "Magic Video", route: "/studio?e=video", status: "available", icon: "play", indent: true },
      { id: "magic-aid", label: "Magic Aid", route: "/studio?e=aid", status: "soon", icon: "layers", indent: true },
      { id: "magic-mail", label: "Magic Mail", route: "/studio?e=mail", status: "soon", icon: "mail", indent: true },
      { id: "magic-canvas", label: "Magic Canvas", route: "/studio?e=canvas", status: "available", icon: "image", indent: true },
      { id: "magic-doc", label: "Magic Doc", route: "/studio?e=doc", status: "soon", icon: "file-text", indent: true },
    ],
  },
  {
    id: "library",
    label: "Library",
    items: [
      { id: "brand-dossiers", label: "Brand Dossiers", route: "/studio/dossier", status: "available", icon: "book-open" },
      { id: "brand-kit", label: "Brand Kit", route: "/brand-library", status: "available", icon: "palette" },
      { id: "content-library", label: "Content Library", route: "/content-library", status: "available", icon: "folder" },
      { id: "claims-library", label: "Claims Library", route: "#", status: "soon", icon: "quote" },
      { id: "templates", label: "Templates", route: "/templates", status: "available", icon: "layout-grid" },
    ],
  },
  {
    id: "compliance",
    label: "Compliance",
    items: [{ id: "mlr-review", label: "MLR Review", route: "/approvals", status: "available", icon: "shield" }],
  },
  {
    id: "activate",
    label: "Activate",
    items: [
      { id: "campaigns", label: "Campaigns", route: "/campaigns", status: "available", icon: "send" },
      { id: "audience", label: "Audience", route: "/audience", status: "available", icon: "users" },
      { id: "re-engage", label: "Re-engage", route: "#", status: "soon", icon: "refresh-cw" },
    ],
  },
];
