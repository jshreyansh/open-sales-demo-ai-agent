export type Stage = "A" | "C" | "T" | "L";

export interface ContentFormat {
  title: string;
  tool: string;
  description: string;
  stages: Stage[];
  audience: string;
  soon: boolean;
}

export interface MagicEngine {
  id: string;
  tabId: string;
  label: string;
  description: string;
  formats: ContentFormat[];
}

/**
 * Mirrors Content Studio's real catalog at contentiq.swishx.com/studio,
 * inspected 2026-08-05 (30 formats across 5 Magic Engines, exact copy/stages).
 */
export const MAGIC_ENGINES: MagicEngine[] = [
  {
    id: "video",
    tabId: "Video",
    label: "Magic Video",
    description: "All motion content — from a 30-second reel to a broadcast DTC spot.",
    formats: [
      {
        title: "Short Video",
        tool: "MagicReel™",
        description:
          "A 30–180s customisable video built from the brand dossier. Used across HCP and patient channels: email, social, congress, web, rep follow-up.",
        stages: ["A", "C"],
        audience: "HCP · Patient",
        soon: false,
      },
      {
        title: "Digital Twin Master Video",
        tool: "MagicAvatar™",
        description:
          "The doctor's own voice and photo generate a lip-synced presenter, so the asset feels as if the physician made it personally for the patient.",
        stages: ["A", "L"],
        audience: "Patient",
        soon: false,
      },
      {
        title: "Broadcast / DTC Video Ad",
        tool: "MagicSpot",
        description:
          "A 30–60s DTC television or streaming spot — the single largest DTC spend category in US pharma marketing.",
        stages: ["A"],
        audience: "Patient",
        soon: true,
      },
      {
        title: "MOA / Explainer Animation",
        tool: "MagicMotion",
        description:
          "Mechanism-of-action animation visualising how the drug works at molecular and cellular level.",
        stages: ["C"],
        audience: "HCP · Patient",
        soon: true,
      },
      {
        title: "Webinar & Event Video",
        tool: "MagicStage",
        description:
          "Speaker-led webinar and congress event video — recorded, chaptered, and cut down into shareable clips.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
      },
      {
        title: "Patient Story Video",
        tool: "MagicStory",
        description:
          "Patient testimonial and lived-experience storytelling for disease awareness and adherence, with the consent and typicality guardrails the format demands.",
        stages: ["A", "L"],
        audience: "Patient",
        soon: true,
      },
    ],
  },
  {
    id: "aid",
    tabId: "Aid",
    label: "Magic Aid",
    description: "HCP detailing and field enablement — what the rep presents, and what they leave behind.",
    formats: [
      {
        title: "Interactive Visual Aid (IVA / CLM)",
        tool: "MagicCLM",
        description:
          "The rep-facing interactive detail aid — clickable MOA tabs, safety callouts, chapter jumps, inline quiz points and talking prompts, delivered through CLM.",
        stages: ["C", "T"],
        audience: "HCP",
        soon: true,
      },
      {
        title: "e-Detail / Remote Deck",
        tool: "MagicDetail",
        description:
          "The remote-detailing deck a rep presents over video — a tighter, self-navigating cut of the visual aid built for a 10-minute virtual call.",
        stages: ["C", "T"],
        audience: "HCP",
        soon: true,
      },
      {
        title: "Leave-Behind",
        tool: "MagicLeave",
        description:
          "The printed or digital piece the rep leaves with the physician — the claims that must survive without the rep in the room.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
      },
      {
        title: "Reprint Carrier",
        tool: "MagicCarrier",
        description:
          "The branded wrapper around a published journal reprint — heavily scrutinised, because the framing must not overstate what the paper found.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
      },
      {
        title: "Dosing & Titration Guide",
        tool: "MagicDose",
        description:
          "The practical dosing, titration and administration reference — pure label derivation, where accuracy matters more than persuasion.",
        stages: ["T", "L"],
        audience: "HCP",
        soon: true,
      },
      {
        title: "FAQ / Objection Handler",
        tool: "MagicAnswer",
        description:
          "The rep-facing answer set for the questions and objections that actually come up in the room, each answer grounded on-label.",
        stages: ["C", "T"],
        audience: "HCP",
        soon: true,
      },
    ],
  },
  {
    id: "mail",
    tabId: "Mail",
    label: "Magic Mail",
    description: "Email and CRM messaging — approved sends, multi-touch sequences, newsletters.",
    formats: [
      {
        title: "Approved Email",
        tool: "MagicSend",
        description:
          "The rep-triggered approved email — the highest-volume, cleanest-ROI proof of the platform, and the format the go-to-market leads with.",
        stages: ["C", "T", "L"],
        audience: "HCP",
        soon: true,
      },
      {
        title: "Multi-touch Campaign",
        tool: "MagicFlow",
        description:
          "A sequenced journey across touches and channels, where the Content Strategist designs the arc and every touch inherits cleared modules.",
        stages: ["A", "C", "T", "L"],
        audience: "HCP · Patient",
        soon: true,
      },
      {
        title: "e-Newsletter",
        tool: "MagicBrief",
        description:
          "The recurring scientific or brand newsletter — lowest MLR burden of the thirty, and the most punishing to produce by hand at cadence.",
        stages: ["L"],
        audience: "HCP",
        soon: true,
      },
    ],
  },
  {
    id: "canvas",
    tabId: "Canvas",
    label: "Magic Canvas",
    description: "Static, display and web creative — from a single banner to a branded destination.",
    formats: [
      {
        title: "Infographic",
        tool: "MagicChart",
        description:
          "Data and disease-state storytelling as a single designed visual, tuned to an HCP or a patient reading level.",
        stages: ["A", "C"],
        audience: "HCP · Patient",
        soon: false,
      },
      {
        title: "Banner / Display Ad",
        tool: "MagicBanner",
        description:
          "The programmatic display set — every IAB size, every variant, each carrying its own ISI treatment and PI link.",
        stages: ["A"],
        audience: "HCP · Patient",
        soon: false,
      },
      {
        title: "Journal / Print Ad",
        tool: "MagicPress",
        description:
          "The peer-reviewed journal spread, where the brief summary / PI page is not an afterthought but half the deliverable.",
        stages: ["A", "C"],
        audience: "HCP",
        soon: false,
      },
      {
        title: "Social Post / Campaign",
        tool: "MagicPost",
        description:
          "Organic and paid social, where the character limit collides with fair balance and the unbranded/branded decision is the whole game.",
        stages: ["A"],
        audience: "Patient · HCP",
        soon: false,
      },
      {
        title: "Savings / Co-pay Card",
        tool: "MagicSave",
        description:
          "The co-pay offer and its terms — the access instrument that converts a first prescription into a filled one.",
        stages: ["T"],
        audience: "Patient",
        soon: false,
      },
      {
        title: "Congress Poster / Booth",
        tool: "MagicBooth",
        description: "Scientific poster and booth panel graphics, produced against congress deadlines that never move.",
        stages: ["C"],
        audience: "HCP",
        soon: false,
      },
      {
        title: "Point-of-Care Asset",
        tool: "MagicPoint",
        description:
          "Waiting-room and exam-room media — posters, screens, and take-ones reaching the patient minutes before the conversation.",
        stages: ["A"],
        audience: "Patient",
        soon: true,
      },
      {
        title: "Web Destination",
        tool: "MagicSite",
        description: "The branded HCP or patient site — an interactive build, which is why it sits in Canvas rather than Doc.",
        stages: ["A", "C", "L"],
        audience: "HCP · Patient",
        soon: true,
      },
    ],
  },
  {
    id: "doc",
    tabId: "Doc",
    label: "Magic Doc",
    description: "Long-form documents — monographs, brochures, medical decks and payer dossiers.",
    formats: [
      {
        title: "Product Monograph",
        tool: "MagicMono",
        description: "The comprehensive clinical reference on the brand — the longest promotional document a medical team will write.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
      },
      {
        title: "HCP / Sales Brochure",
        tool: "MagicFolio",
        description: "The core HCP brochure — the claims, the evidence, the safety, in the order a prescriber actually reads them.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
      },
      {
        title: "Patient Brochure / Leaflet",
        tool: "MagicLeaflet",
        description:
          "Plain-language patient education, held to a reading level and to the same fair-balance standard as any promotional piece.",
        stages: ["A", "L"],
        audience: "Patient",
        soon: true,
      },
      {
        title: "AMCP / Formulary Dossier",
        tool: "MagicDossier",
        description:
          "The AMCP-format payer dossier — the deepest source-grounding requirement of all thirty formats, which is why it builds last.",
        stages: ["T"],
        audience: "Payer",
        soon: true,
      },
      {
        title: "MSL / Medical Deck",
        tool: "MagicMSL",
        description: "The scientific-exchange deck for Medical Science Liaisons — governed by medical affairs under Vault MedComms, not promotional MLR.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
      },
      {
        title: "KOL / Speaker Deck",
        tool: "MagicSpeaker",
        description: "The locked, on-label speaker deck a paid KOL presents to peers — content-lock enforcement is the whole compliance surface.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
      },
      {
        title: "White Paper / Publication Summary",
        tool: "MagicPaper",
        description: "Thought-leadership or a plain-language summary of published evidence — usually unbranded, and the framing decision is the control.",
        stages: ["C"],
        audience: "HCP",
        soon: true,
      },
    ],
  },
];

export const STAGE_LABELS: Record<Stage, string> = {
  A: "Awareness",
  C: "Consideration",
  T: "Trial / Adoption",
  L: "Adherence / Loyalty",
};
