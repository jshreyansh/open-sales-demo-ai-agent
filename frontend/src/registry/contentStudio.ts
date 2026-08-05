export type Stage = "A" | "C" | "T" | "L";

export type PromoClass = "Promotional" | "Mixed" | "Non-promotional";

export type TeamRole = "Project Manager" | "Content Strategist" | "Medical Writer" | "Creative Producer" | "MLR Reviewer";

export interface FormatSample {
  title: string;
  subtitle: string;
  duration: string;
  badge: string;
}

export interface ContentFormat {
  title: string;
  tool: string;
  description: string;
  stages: Stage[];
  audience: string;
  soon: boolean;
  promo: PromoClass;
  leadRole: TeamRole;
  requiredInputs: string[];
  eliminates: string;
  samples?: FormatSample[];
}

export interface MagicEngine {
  id: string;
  tabId: string;
  label: string;
  description: string;
  icon: string;
  formats: ContentFormat[];
}

/**
 * Mirrors Content Studio's real catalog at contentiq.swishx.com/studio —
 * cross-checked against the actual source (lib/contentiq/formats.ts,
 * components/studio/ContentStudioGallery.tsx in the marketingiq-web repo)
 * on 2026-08-06, not just the live DOM, so leadRole/requiredInputs/eliminates
 * match the real per-format records exactly.
 */
export const MAGIC_ENGINES: MagicEngine[] = [
  {
    id: "video",
    tabId: "Video",
    label: "Magic Video",
    description: "All motion content — from a 30-second reel to a broadcast DTC spot.",
    icon: "play",
    formats: [
      {
        title: "Short Video",
        tool: "MagicReel™",
        description:
          "A 30–180s customisable video built from the brand dossier. Used across HCP and patient channels: email, social, congress, web, rep follow-up.",
        stages: ["A", "C"],
        audience: "HCP · Patient",
        soon: false,
        promo: "Promotional",
        leadRole: "Creative Producer",
        requiredInputs: [
          "Foundational dossier / brand KB",
          "Approved label / PI",
          "Reference library",
          "Brand identity kit",
          "Target channel & duration",
          "Voice / music / caption prefs",
        ],
        eliminates:
          "Script-to-storyboard-to-render agency cycles, reference chasing, and version proliferation across channels.",
        samples: [
          { title: "Tecentriq — Mechanism", subtitle: "Doctor", duration: "1:42", badge: "HD" },
          { title: "Bisberry — Intro", subtitle: "Doctor", duration: "3:12", badge: "CINEMATIC" },
        ],
      },
      {
        title: "Digital Twin Master Video",
        tool: "MagicAvatar™",
        description:
          "The doctor's own voice and photo generate a lip-synced presenter, so the asset feels as if the physician made it personally for the patient.",
        stages: ["A", "L"],
        audience: "Patient",
        soon: false,
        promo: "Promotional",
        leadRole: "Creative Producer",
        requiredInputs: [
          "Doctor voice sample & consent",
          "Doctor photo",
          "Base video or approved script",
          "Consent & rights documentation",
          "Brand identity kit",
        ],
        eliminates: "Bespoke per-doctor production entirely — a custom edit per physician becomes a templated generation.",
      },
      {
        title: "Broadcast / DTC Video Ad",
        tool: "MagicSpot",
        description:
          "A 30–60s DTC television or streaming spot — the single largest DTC spend category in US pharma marketing.",
        stages: ["A"],
        audience: "Patient",
        soon: true,
        promo: "Promotional",
        leadRole: "Creative Producer",
        requiredInputs: [
          "Creative brief & patient insight",
          "Approved label / PI",
          "Indication statement",
          "ISI + broadcast major statement (audio + on-screen)",
          "Adequate-provision fulfilment plan",
        ],
        eliminates: "The multi-week storyboard-shoot-edit cycle and the fair-balance rework that dominates DTC MLR rejections.",
      },
      {
        title: "MOA / Explainer Animation",
        tool: "MagicMotion",
        description: "Mechanism-of-action animation visualising how the drug works at molecular and cellular level.",
        stages: ["C"],
        audience: "HCP · Patient",
        soon: true,
        promo: "Promotional",
        leadRole: "Creative Producer",
        requiredInputs: [
          "Scientific source (pathway data, PK/PD, publications)",
          "Approved label",
          "Reference library",
          "Audience level (HCP vs patient)",
          "Brand identity kit",
        ],
        eliminates:
          "The specialist 3D-studio cycle (8–12 weeks) and the accuracy back-and-forth between animators and medical teams.",
      },
      {
        title: "Webinar & Event Video",
        tool: "MagicStage",
        description: "Speaker-led webinar and congress event video — recorded, chaptered, and cut down into shareable clips.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
        promo: "Mixed",
        leadRole: "Creative Producer",
        requiredInputs: ["Speaker deck & notes", "Approved claims", "Event branding", "Disclosure requirements"],
        eliminates: "Post-production editing cycles and the manual cut-down of a long recording into channel segments.",
      },
      {
        title: "Patient Story Video",
        tool: "MagicStory",
        description:
          "Patient testimonial and lived-experience storytelling for disease awareness and adherence, with the consent and typicality guardrails the format demands.",
        stages: ["A", "L"],
        audience: "Patient",
        soon: true,
        promo: "Promotional",
        leadRole: "Creative Producer",
        requiredInputs: ["Patient consent & release", "Story outline", "Approved label boundaries", "ISI / fair balance where branded"],
        eliminates: "Casting, shooting and the compliance rework that follows an unguarded testimonial.",
      },
    ],
  },
  {
    id: "aid",
    tabId: "Aid",
    label: "Magic Aid",
    description: "HCP detailing and field enablement — what the rep presents, and what they leave behind.",
    icon: "layers",
    formats: [
      {
        title: "Interactive Visual Aid (IVA / CLM)",
        tool: "MagicCLM",
        description:
          "The rep-facing interactive detail aid — clickable MOA tabs, safety callouts, chapter jumps, inline quiz points and talking prompts, delivered through CLM.",
        stages: ["C", "T"],
        audience: "HCP",
        soon: true,
        promo: "Promotional",
        leadRole: "Creative Producer",
        requiredInputs: ["Brand dossier", "Approved claims & references", "ISI and fair balance", "Brand template", "CLM/Veeva packaging spec"],
        eliminates: "The agency CLM build cycle and the slide-by-slide re-approval on every claim change.",
      },
      {
        title: "e-Detail / Remote Deck",
        tool: "MagicDetail",
        description:
          "The remote-detailing deck a rep presents over video — a tighter, self-navigating cut of the visual aid built for a 10-minute virtual call.",
        stages: ["C", "T"],
        audience: "HCP",
        soon: true,
        promo: "Promotional",
        leadRole: "Content Strategist",
        requiredInputs: ["Approved claims & references", "Call objective", "ISI and fair balance", "Brand template"],
        eliminates: "Rebuilding the field deck for remote, and the drift between the in-person and virtual versions.",
      },
      {
        title: "Leave-Behind",
        tool: "MagicLeave",
        description: "The printed or digital piece the rep leaves with the physician — the claims that must survive without the rep in the room.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
        promo: "Promotional",
        leadRole: "Medical Writer",
        requiredInputs: ["Approved claims & references", "ISI", "Brand template", "Print/digital spec"],
        eliminates: "The design-and-approve loop for what is, structurally, a derivative of the detail aid.",
      },
      {
        title: "Reprint Carrier",
        tool: "MagicCarrier",
        description: "The branded wrapper around a published journal reprint — heavily scrutinised, because the framing must not overstate what the paper found.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
        promo: "Promotional",
        leadRole: "Medical Writer",
        requiredInputs: ["The reprint itself", "Approved claims", "Fair balance & ISI", "Journal permissions"],
        eliminates: "The framing-rework cycle where marketing copy outruns the underlying publication.",
      },
      {
        title: "Dosing & Titration Guide",
        tool: "MagicDose",
        description: "The practical dosing, titration and administration reference — pure label derivation, where accuracy matters more than persuasion.",
        stages: ["T", "L"],
        audience: "HCP",
        soon: true,
        promo: "Promotional",
        leadRole: "Medical Writer",
        requiredInputs: ["Approved label / PI dosing section", "Renal/hepatic adjustments", "Special populations", "Brand template"],
        eliminates: "Manual transcription from the PI and the errors that review then has to catch.",
      },
      {
        title: "FAQ / Objection Handler",
        tool: "MagicAnswer",
        description: "The rep-facing answer set for the questions and objections that actually come up in the room, each answer grounded on-label.",
        stages: ["C", "T"],
        audience: "HCP",
        soon: true,
        promo: "Promotional",
        leadRole: "Medical Writer",
        requiredInputs: ["Brand dossier FAQ section", "Competitive context", "Approved claims", "On-label boundaries"],
        eliminates: "The field-medical round-trip for every question a rep cannot answer on-label.",
      },
    ],
  },
  {
    id: "mail",
    tabId: "Mail",
    label: "Magic Mail",
    description: "Email and CRM messaging — approved sends, multi-touch sequences, newsletters.",
    icon: "mail",
    formats: [
      {
        title: "Approved Email",
        tool: "MagicSend",
        description: "The rep-triggered approved email — the highest-volume, cleanest-ROI proof of the platform, and the format the go-to-market leads with.",
        stages: ["C", "T", "L"],
        audience: "HCP",
        soon: true,
        promo: "Promotional",
        leadRole: "Content Strategist",
        requiredInputs: ["Approved claims & references", "ISI", "Brand template", "CRM/Veeva approved-email spec"],
        eliminates: "The per-variant approval cycle that makes approved email so slow to refresh.",
      },
      {
        title: "Multi-touch Campaign",
        tool: "MagicFlow",
        description: "A sequenced journey across touches and channels, where the Content Strategist designs the arc and every touch inherits cleared modules.",
        stages: ["A", "C", "T", "L"],
        audience: "HCP · Patient",
        soon: true,
        promo: "Promotional",
        leadRole: "Content Strategist",
        requiredInputs: ["Objective & journey stage", "Audience segments", "Approved module library", "Channel mix & cadence"],
        eliminates: "Designing and approving each touch as an unrelated asset instead of a sequence.",
      },
      {
        title: "e-Newsletter",
        tool: "MagicBrief",
        description: "The recurring scientific or brand newsletter — lowest MLR burden of the thirty, and the most punishing to produce by hand at cadence.",
        stages: ["L"],
        audience: "HCP",
        soon: true,
        promo: "Mixed",
        leadRole: "Medical Writer",
        requiredInputs: ["Content calendar", "Source publications", "Approved claims where branded", "Template"],
        eliminates: "The editorial assembly cycle repeated every single issue.",
      },
    ],
  },
  {
    id: "canvas",
    tabId: "Canvas",
    label: "Magic Canvas",
    description: "Static, display and web creative — from a single banner to a branded destination.",
    icon: "image",
    formats: [
      {
        title: "Infographic",
        tool: "MagicChart",
        description: "Data and disease-state storytelling as a single designed visual, tuned to an HCP or a patient reading level.",
        stages: ["A", "C"],
        audience: "HCP · Patient",
        soon: false,
        promo: "Promotional",
        leadRole: "Creative Producer",
        requiredInputs: ["Source data / trial results", "Reference library", "Audience level", "Brand identity kit"],
        eliminates: "The design round-trips on a piece whose content is already settled.",
      },
      {
        title: "Banner / Display Ad",
        tool: "MagicBanner",
        description: "The programmatic display set — every IAB size, every variant, each carrying its own ISI treatment and PI link.",
        stages: ["A"],
        audience: "HCP · Patient",
        soon: false,
        promo: "Promotional",
        leadRole: "Creative Producer",
        requiredInputs: ["Approved claim (short form)", "ISI / PI link", "Brand identity kit", "IAB size matrix"],
        eliminates: "Hand-resizing a creative concept across dozens of ad slots and re-clearing each one.",
      },
      {
        title: "Journal / Print Ad",
        tool: "MagicPress",
        description: "The peer-reviewed journal spread, where the brief summary / PI page is not an afterthought but half the deliverable.",
        stages: ["A", "C"],
        audience: "HCP",
        soon: false,
        promo: "Promotional",
        leadRole: "Creative Producer",
        requiredInputs: ["Approved claims & references", "Full PI for the brief-summary page", "Fair balance", "Print spec"],
        eliminates: "The typesetting-and-PI-placement cycle that dominates print production.",
      },
      {
        title: "Social Post / Campaign",
        tool: "MagicPost",
        description: "Organic and paid social, where the character limit collides with fair balance and the unbranded/branded decision is the whole game.",
        stages: ["A"],
        audience: "Patient · HCP",
        soon: false,
        promo: "Promotional",
        leadRole: "Content Strategist",
        requiredInputs: ["Campaign angle", "Branded vs unbranded framing", "ISI / fair balance where branded", "Platform specs"],
        eliminates: "The per-post compliance negotiation on a channel that demands volume.",
      },
      {
        title: "Savings / Co-pay Card",
        tool: "MagicSave",
        description: "The co-pay offer and its terms — the access instrument that converts a first prescription into a filled one.",
        stages: ["T"],
        audience: "Patient",
        soon: false,
        promo: "Promotional",
        leadRole: "Medical Writer",
        requiredInputs: ["Offer terms & eligibility", "Legal restrictions (no federal beneficiaries)", "Brand identity kit", "Redemption mechanics"],
        eliminates: "Legal round-trips on eligibility language that is highly templated.",
      },
      {
        title: "Congress Poster / Booth",
        tool: "MagicBooth",
        description: "Scientific poster and booth panel graphics, produced against congress deadlines that never move.",
        stages: ["C"],
        audience: "HCP",
        soon: false,
        promo: "Promotional",
        leadRole: "Creative Producer",
        requiredInputs: ["Abstract / data", "Reference library", "Congress spec & dimensions", "Brand identity kit"],
        eliminates: "The pre-congress crunch where design capacity, not science, is the constraint.",
      },
      {
        title: "Point-of-Care Asset",
        tool: "MagicPoint",
        description: "Waiting-room and exam-room media — posters, screens, and take-ones reaching the patient minutes before the conversation.",
        stages: ["A"],
        audience: "Patient",
        soon: true,
        promo: "Promotional",
        leadRole: "Creative Producer",
        requiredInputs: ["Disease-state framing", "ISI / PI access", "Channel network spec", "Brand identity kit"],
        eliminates: "Per-network creative resizing and the separate approval each placement triggers.",
      },
      {
        title: "Web Destination",
        tool: "MagicSite",
        description: "The branded HCP or patient site — an interactive build, which is why it sits in Canvas rather than Doc.",
        stages: ["A", "C", "L"],
        audience: "HCP · Patient",
        soon: true,
        promo: "Promotional",
        leadRole: "Content Strategist",
        requiredInputs: [
          "Site architecture & objective",
          "Approved claims & references",
          "ISI, PI fulfilment, adequate provision",
          "Brand identity kit",
          "Audience gating rules",
        ],
        eliminates: "The digital-agency build cycle and the page-by-page MLR pass that follows every content change.",
      },
    ],
  },
  {
    id: "doc",
    tabId: "Doc",
    label: "Magic Doc",
    description: "Long-form documents — monographs, brochures, medical decks and payer dossiers.",
    icon: "file-text",
    formats: [
      {
        title: "Product Monograph",
        tool: "MagicMono",
        description: "The comprehensive clinical reference on the brand — the longest promotional document a medical team will write.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
        promo: "Promotional",
        leadRole: "Medical Writer",
        requiredInputs: ["Full clinical dataset", "Approved label / PI", "Reference library", "Fair balance & ISI"],
        eliminates: "The multi-month medical-writing cycle on a document derived almost entirely from the dossier.",
      },
      {
        title: "HCP / Sales Brochure",
        tool: "MagicFolio",
        description: "The core HCP brochure — the claims, the evidence, the safety, in the order a prescriber actually reads them.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
        promo: "Promotional",
        leadRole: "Medical Writer",
        requiredInputs: ["Approved claims & references", "ISI", "Fair balance", "Brand template"],
        eliminates: "Rewriting from scratch what the dossier already holds in full.",
      },
      {
        title: "Patient Brochure / Leaflet",
        tool: "MagicLeaflet",
        description: "Plain-language patient education, held to a reading level and to the same fair-balance standard as any promotional piece.",
        stages: ["A", "L"],
        audience: "Patient",
        soon: true,
        promo: "Promotional",
        leadRole: "Medical Writer",
        requiredInputs: ["Approved label in plain language", "Reading-level target", "ISI / safety in patient language", "Brand identity kit"],
        eliminates: "The health-literacy rewrite loop between medical, legal and creative.",
      },
      {
        title: "AMCP / Formulary Dossier",
        tool: "MagicDossier",
        description: "The AMCP-format payer dossier — the deepest source-grounding requirement of all thirty formats, which is why it builds last.",
        stages: ["T"],
        audience: "Payer",
        soon: true,
        promo: "Promotional",
        leadRole: "Medical Writer",
        requiredInputs: ["Full clinical & economic evidence", "Health-economic models", "AMCP format specification", "Unapproved-use governance rules"],
        eliminates: "The specialist HEOR writing cycle and the evidence-assembly effort behind it.",
      },
      {
        title: "MSL / Medical Deck",
        tool: "MagicMSL",
        description: "The scientific-exchange deck for Medical Science Liaisons — governed by medical affairs under Vault MedComms, not promotional MLR.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
        promo: "Non-promotional",
        leadRole: "Medical Writer",
        requiredInputs: ["Full scientific data & publications", "Reference library", "Medical-affairs governance rules", "Scientific-exchange boundaries"],
        eliminates:
          "The medical-writing and citation cycle for scientific decks — with a promotional-content firewall holding it non-promotional.",
      },
      {
        title: "KOL / Speaker Deck",
        tool: "MagicSpeaker",
        description: "The locked, on-label speaker deck a paid KOL presents to peers — content-lock enforcement is the whole compliance surface.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
        promo: "Mixed",
        leadRole: "Content Strategist",
        requiredInputs: ["Approved claims & references", "Indication, ISI, fair balance", "Speaker disclosure requirements", "Locked-content rules"],
        eliminates: "Deck-build and approval cycles, and the version-control risk of speakers using outdated decks.",
      },
      {
        title: "White Paper / Publication Summary",
        tool: "MagicPaper",
        description: "Thought-leadership or a plain-language summary of published evidence — usually unbranded, and the framing decision is the control.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
        promo: "Non-promotional",
        leadRole: "Medical Writer",
        requiredInputs: ["Source publications & data", "Reference library", "Unbranded / disease framing", "Branded-claim boundaries"],
        eliminates: "The literature-synthesis and writing cycle.",
      },
    ],
  },
];

/**
 * Stable id derived from the format's tool name (all 30 are unique) — used
 * as the uiRegistry component id so the agent can open one specific
 * format's modal directly, not just switch engine tabs. The backend
 * registry (backend/src/agent/registry.py) hardcodes these same slugs
 * since there's no shared code between the two packages — keep them in
 * sync by hand if a format's tool name ever changes.
 */
export function formatSlug(tool: string): string {
  return tool
    .toLowerCase()
    .replace(/[™®]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

export const STAGE_LABELS: Record<Stage, string> = {
  A: "Awareness",
  C: "Consideration",
  T: "Trial / Adoption",
  L: "Adherence / Loyalty",
};

export interface TeamRoleInfo {
  role: TeamRole;
  initials: string;
  color: string;
}

/** Fixed order — every format modal renders all 5, dimming the ones that aren't lead. */
export const TEAM_ROLES: TeamRoleInfo[] = [
  { role: "Project Manager", initials: "PM", color: "#7C3AED" },
  { role: "Content Strategist", initials: "CS", color: "#E8590C" },
  { role: "Medical Writer", initials: "MW", color: "#C2410C" },
  { role: "Creative Producer", initials: "CP", color: "#0D9488" },
  { role: "MLR Reviewer", initials: "MR", color: "#2563EB" },
];

export interface MlrInput {
  label: string;
  note: string;
  promoOnly: boolean;
}

/** Shared across every format — only which ones "apply" changes, based on promo class. */
export const MLR_INPUTS: MlrInput[] = [
  { label: "On-label claims only", note: "Every claim consistent with the approved PI/label", promoOnly: false },
  { label: "Substantiation", note: "Each claim linked to an approved reference", promoOnly: false },
  { label: "Fair balance", note: "Risk in prominence similar to benefit", promoOnly: true },
  { label: "ISI and safety", note: "Safety information, boxed warnings, AEs, REMS", promoOnly: true },
  { label: "Indication statement", note: "Correct indication & name prominence, 21 CFR 202.1", promoOnly: true },
  { label: "Claims / reference linkage", note: "Modular tagging so cleared modules skip re-review", promoOnly: false },
  { label: "Audience / channel metadata", note: "HCP vs patient vs payer, channel-specific formatting", promoOnly: false },
  { label: "Adequate provision / PI", note: "Prominent PI links for digital; adequate provision for broadcast", promoOnly: true },
];
