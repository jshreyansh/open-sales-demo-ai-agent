/**
 * Dummy data for the MagicReel / MagicAvatar studio mockups — mirrors the
 * real product's flow shape (audience cards, topic-per-audience, script
 * structures, etc, from marketingiq-web's MagicReelStudioV2/BriefStep) but
 * with invented content, no real generation behind it. Reuses brand names
 * already established in backend/src/data/dashboard.py for consistency
 * across the demo.
 */

// Real showcase renders for both wizards' result screens (see
// AssetVideoPlayer.tsx) -- served from public/videos (Vite copies public/
// as-is, so these are plain root-relative paths, not bundled imports).
export const DEFAULT_REEL_VIDEO_URL = "/videos/tecentriq-reel.mp4";
export const DEFAULT_AVATAR_VIDEO_URL = "/videos/avatar-showcase.mp4";

export interface Scene {
  id: string;
  narration: string;
  visual: string;
  negativePrompt: string;
  onScreenText: string;
  hasCitation: boolean;
}

export const AUDIENCES = [
  { id: "doctor", label: "Doctor / HCP", desc: "Clinical detail, peer-to-peer tone" },
  { id: "rep", label: "Sales Rep / Medical Rep", desc: "30-sec pitch, objection handling" },
  { id: "patient", label: "Patient", desc: "Plain-language, what to expect" },
  { id: "consumer", label: "Consumer", desc: "Benefit-led, everyday language" },
  { id: "procurement", label: "Hospital Procurement", desc: "Formulary value, evidence, supply & cost" },
  { id: "retailer", label: "Retailer / Stockist", desc: "Demand, margins, stocking decisions" },
];

export const TOPICS_BY_AUDIENCE: Record<string, string[]> = {
  doctor: ["Product Introduction", "Mechanism of Action", "Indications", "Dosage & Safety", "Drug Interactions", "Side Effects"],
  rep: ["Key Selling Points", "Objection Handling", "Competitive Positioning"],
  patient: ["What to Expect", "How to Take It", "Common Questions"],
  consumer: ["Why It Helps", "Getting Started"],
  procurement: ["Formulary Value", "Evidence Summary", "Supply & Cost"],
  retailer: ["Demand Drivers", "Margins", "Stocking Guidance"],
};

export const GOALS = ["New Launch", "Awareness", "Retention"];

// Tecentriq is first (the wizard's default, DOSSIERS[0]) so the reel it
// walks through by default matches the real MagicReel showcase render on
// the result screen (see DEFAULT_REEL_VIDEO_URL) instead of narrating one
// brand's metadata while a different brand's video plays at the end.
// Deliberately ONE dossier, not a catalogue. A grid of brands invites
// "can you show me that one instead?" -- and only this one has a matching
// real rendered reel on the result screen (DEFAULT_REEL_VIDEO_URL), so any
// other pick would narrate one brand while a different brand's video plays.
// The "Add dossier" affordance next to it carries the story that a real
// workspace holds many, without offering ones we can't actually show.
export const DOSSIERS = [
  { id: "tecentriq", brand: "Tecentriq", therapy: "Oncology · Specialists" },
];

export const PRESET_VOICES = [
  { id: "v1", name: "Ananya", gender: "Female" },
  { id: "v2", name: "Rohan", gender: "Male" },
  { id: "v3", name: "Priya", gender: "Female" },
  { id: "v4", name: "Karan", gender: "Male" },
];

export const LANGUAGES = ["English", "Hindi", "Tamil", "Bengali", "Marathi"];

export const SCRIPT_STRUCTURES = [
  { id: "problem-solution", label: "Problem → Solution", badge: "Team-written", arc: "Problem → Solution → Proof" },
  { id: "product-proof", label: "Product → Proof", badge: "Team-written", arc: "Product → Benefits → Proof" },
  { id: "custom", label: "Use my own script", badge: "YOUR WORDS", arc: "Your script → Voice → Visuals" },
];

export const TARGET_LENGTHS = [15, 30, 45, 60, 90, 120];

export const MUSIC_TRACKS = [
  { id: "m1", title: "Gentle Optimism", mood: "Uplifting", duration: "1:42" },
  { id: "m2", title: "Clinical Calm", mood: "Neutral", duration: "2:05" },
  { id: "m3", title: "Forward Motion", mood: "Energetic", duration: "1:30" },
];

const DEFAULT_NEGATIVE_PROMPT =
  "cartoon, animated character, 3D render, CGI, illustration, sparkling eyes, waxy skin, on-screen text, packaging label";

export function generateDummyScenes(topic: string, brand: string): Scene[] {
  return [
    {
      id: "s1",
      narration: `${brand} addresses a clear gap in ${topic.toLowerCase()} — one your peers are already asking about.`,
      visual:
        "A modern consultation room, deep navy-to-white gradient walls, large clinical window casting soft daylight. A clinician in a white coat sits at a polished desk, sharp but unhurried expression, discussing with a patient.",
      negativePrompt: DEFAULT_NEGATIVE_PROMPT,
      onScreenText: topic,
      hasCitation: true,
    },
    {
      id: "s2",
      narration: `Backed by clinical evidence, ${brand} delivers consistent results across patient profiles.`,
      visual: "Clean clinical setting, a data visualization overlay showing efficacy trends across a neutral, photoreal background.",
      negativePrompt: DEFAULT_NEGATIVE_PROMPT,
      onScreenText: "Clinical evidence",
      hasCitation: true,
    },
    {
      id: "s3",
      narration: `${brand} is available now — ask your rep for the full prescribing information.`,
      visual: "A product pack shot centered against a brand-color gradient background, soft studio lighting.",
      negativePrompt: DEFAULT_NEGATIVE_PROMPT,
      onScreenText: "",
      hasCitation: false,
    },
  ];
}
