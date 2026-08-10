// Hand-written sidebar nav tree, mirroring the ordering already declared in
// swishx-docs' meta.json files (content/docs/**/meta.json) — static and
// small enough that adding a new page here by hand is simpler than parsing
// those meta.json files into a tree at runtime.
export interface DocsNavPage {
  type: "page";
  title: string;
  slug: string;
}

export interface DocsNavGroup {
  type: "group";
  title: string;
  items: DocsNavNode[];
}

export type DocsNavNode = DocsNavPage | DocsNavGroup;

function page(title: string, slug: string): DocsNavPage {
  return { type: "page", title, slug };
}

function group(title: string, items: DocsNavNode[]): DocsNavGroup {
  return { type: "group", title, items };
}

export const DOCS_NAV: DocsNavNode[] = [
  group("Getting Started", [
    page("Quickstart", "getting-started/quickstart"),
    page("Authentication", "getting-started/authentication"),
  ]),
  group("Core Concepts", [
    page("The reasoning pipeline", "concepts/reasoning-pipeline"),
    page("Models", "concepts/models"),
    page("Model routing", "concepts/model-routing"),
    page("Compliance & verification", "concepts/compliance-verification"),
  ]),
  group("API Reference", [
    page("Errors", "api-reference/errors"),
    page("Rate limits", "api-reference/rate-limits"),
    group("Videos", [
      page("Create a video generation", "api-reference/videos/create"),
      page("Retrieve a video generation", "api-reference/videos/retrieve"),
      page("List video generations", "api-reference/videos/list"),
      page("Cancel a video generation", "api-reference/videos/cancel"),
    ]),
    group("Images", [page("Create a keyframe image", "api-reference/images/create")]),
  ]),
  group("Guides", [
    page("Setting up a brand dossier", "guides/brand-dossier"),
    page("Polling for results", "guides/polling-for-results"),
    page("Error handling", "guides/error-handling"),
  ]),
  page("Changelog", "changelog"),
];
