export interface RegistryAction {
  id: string;
  description: string;
}

export interface RegistryComponent {
  id: string;
  label: string;
  description: string;
  actions: RegistryAction[];
}

export interface RegistryPage {
  id: string;
  label: string;
  components: RegistryComponent[];
}

/**
 * Describes what the agent can point at and do, in terms the LLM (or the
 * keyword fallback) can reason over. `page` + component `id` must match the
 * ids the frontend registers under (frontend/src/lib/uiRegistry.ts) — same
 * convention, not shared code, since frontend/backend are separate packages.
 *
 * Extend this whenever a new page or actionable component is added on the
 * frontend — that's the whole point of a registry: one place to update
 * instead of teaching the agent new prompts by hand.
 */
export const UI_REGISTRY: RegistryPage[] = [
  {
    id: "dashboard",
    label: "Dashboard",
    components: [
      {
        id: "insights",
        label: "Insights panel",
        description: "The four insight cards: Campaign Insights, HCP Insights, Field Rep Insights, Agentic IQ.",
        actions: [{ id: "highlight", description: "Draw attention to the insights panel" }],
      },
      {
        id: "active-campaigns",
        label: "Active Campaigns",
        description: "List of running campaigns with progress and status (Paused / Optimizing).",
        actions: [{ id: "highlight", description: "Draw attention to the active campaigns list" }],
      },
    ],
  },
  {
    id: "analytics",
    label: "Analytics",
    components: [
      {
        id: "funnel",
        label: "Engagement Funnel",
        description: "Sent, Viewed, Played, Completed, Shared funnel for campaign engagement.",
        actions: [{ id: "highlight", description: "Draw attention to the engagement funnel" }],
      },
    ],
  },
  {
    id: "content-studio",
    label: "Content Studio",
    components: [
      {
        id: "video-tab",
        label: "Magic Video",
        description: "Video content formats — short videos, digital twin avatars, broadcast ads.",
        actions: [{ id: "click", description: "Switch Content Studio to the Video tab" }],
      },
      {
        id: "aid-tab",
        label: "Magic Aid",
        description: "HCP detailing and field-rep enablement formats.",
        actions: [{ id: "click", description: "Switch Content Studio to the Aid tab" }],
      },
      {
        id: "mail-tab",
        label: "Magic Mail",
        description: "Email and CRM messaging formats.",
        actions: [{ id: "click", description: "Switch Content Studio to the Mail tab" }],
      },
      {
        id: "canvas-tab",
        label: "Magic Canvas",
        description: "Static, display and web creative formats — infographics, banners, social posts.",
        actions: [{ id: "click", description: "Switch Content Studio to the Canvas tab" }],
      },
      {
        id: "doc-tab",
        label: "Magic Doc",
        description: "Long-form documents — monographs, brochures, payer dossiers.",
        actions: [{ id: "click", description: "Switch Content Studio to the Doc tab" }],
      },
    ],
  },
  {
    id: "brand-kit",
    label: "Brand Kit",
    components: [
      {
        id: "logo",
        label: "Logo",
        description: "Where the workspace logo is uploaded and replaced.",
        actions: [{ id: "highlight", description: "Draw attention to the logo upload control" }],
      },
      {
        id: "palette",
        label: "Palette",
        description: "The brand color fields: Primary, Accent, Callout Background, Text.",
        actions: [{ id: "highlight", description: "Draw attention to the palette editor" }],
      },
    ],
  },
];

export interface FlatAction {
  page: string;
  pageLabel: string;
  component: string;
  componentLabel: string;
  method: string;
  keywords: string[];
}

export function flattenRegistry(registry: RegistryPage[]): FlatAction[] {
  const flat: FlatAction[] = [];
  for (const page of registry) {
    for (const component of page.components) {
      for (const action of component.actions) {
        const text = `${page.label} ${component.id} ${component.label} ${component.description} ${action.id} ${action.description}`;
        const keywords = text
          .toLowerCase()
          .split(/[^a-z0-9]+/)
          .filter(Boolean);
        flat.push({
          page: page.id,
          pageLabel: page.label,
          component: component.id,
          componentLabel: component.label,
          method: action.id,
          keywords: Array.from(new Set(keywords)),
        });
      }
    }
  }
  return flat;
}
