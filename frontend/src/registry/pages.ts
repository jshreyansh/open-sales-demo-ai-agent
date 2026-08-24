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
 * Started as a mirror of the real ContentIQ (contentiq.swishx.com) sidebar,
 * now deliberately narrowed to the three groups this demo actually walks a
 * prospect through: Home, Create, Library. The activation surface
 * (Campaigns / Audience / Re-engage), Analytics and Claims Library were cut
 * because nothing behind them is built here, and a nav full of stubs reads
 * as an unfinished product during a live demo. MLR Review moved out of its
 * own "Compliance" group into Library — one heading for everything that is
 * a stored, browsable collection.
 *
 * Analytics and Templates were both cut entirely — page, renderPage() case,
 * and backend registry entry — rather than left half-alive as unclickable
 * orphans; there was no product behind either.
 *
 * Top-level nav only — flows inside each page are out of scope until built
 * individually.
 */
export const NAV_REGISTRY: NavGroup[] = [
  {
    id: "home",
    // No heading: this group is a single item whose own label already reads
    // "Home", so a group label above it would just say the word twice.
    label: null,
    items: [{ id: "home", label: "Home", route: "/home", status: "available", icon: "dashboard" }],
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
      // MLR Review leads the group: it's the only entry here that has work
      // waiting in it (the sidebar renders its pending count), so it reads
      // first rather than being buried under the static collections.
      { id: "mlr-review", label: "MLR Review", route: "/approvals", status: "available", icon: "shield" },
      { id: "brand-dossiers", label: "Brand Dossiers", route: "/studio/dossier", status: "available", icon: "book-open" },
      { id: "brand-kit", label: "Brand Kit", route: "/brand-library", status: "available", icon: "palette" },
      { id: "content-library", label: "Content Library", route: "/content-library", status: "available", icon: "folder" },
    ],
  },
];
