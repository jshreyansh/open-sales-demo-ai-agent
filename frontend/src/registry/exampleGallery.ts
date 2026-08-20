import { DEFAULT_REEL_VIDEO_URL, DEFAULT_AVATAR_VIDEO_URL } from "./studioData";

// The four config fields worth surfacing per example -- mapped to an icon
// in ExampleGalleryPanel.tsx by this same label, so the data here doesn't
// need to know about icon names. `value` accepts an array for fields that
// can genuinely have more than one real answer (e.g. a reel generated in
// multiple languages) -- kept singular for both examples below since
// that's what's actually true of these two videos, not fabricated to
// look fuller.
export interface GalleryConfig {
  label: "Audience" | "Purpose" | "Voice" | "Language";
  value: string | string[];
}

export interface GalleryExample {
  id: string;
  title: string;
  format: string;
  duration: string;
  description: string;
  videoUrl: string;
  configs: GalleryConfig[];
}

// The evergreen line under the format name -- describes the sandbox's
// value prop in general, not this specific example, so it's one shared
// constant rather than per-example copy.
export const GALLERY_TAGLINE = "AI-generated content crafted for accuracy and impact.";

// Real rendered examples for the standalone example gallery (see
// ExampleGalleryPanel.tsx) -- shown when a prospect explicitly asks for
// real, live generation instead of walking a flow (runtime.py's
// instruction 13). configs are the couple of basic settings worth
// surfacing per example (not every field the wizard collects) so the
// gallery reads as "here's roughly what was configured to get this,"
// without turning into a full spec sheet.
export const GALLERY_EXAMPLES: GalleryExample[] = [
  {
    id: "reel-tecentriq",
    title: "Tecentriq — Mechanism of Action",
    format: "MagicReel™ · Short Video",
    duration: "1:42",
    description:
      "An HCP-facing reel explaining Tecentriq's PD-L1 inhibition and its six approved indications, with Roche's brand system applied automatically at generation.",
    videoUrl: DEFAULT_REEL_VIDEO_URL,
    configs: [
      { label: "Audience", value: "HCP — Oncologists" },
      { label: "Purpose", value: "Mechanism of Action" },
      { label: "Voice", value: "Ananya (AI Voice)" },
      { label: "Language", value: "English" },
    ],
  },
  {
    id: "avatar-piyush",
    title: "Dr. Piyush Agarwal — Patient Counseling",
    format: "MagicAvatar™ · Digital Twin",
    duration: "0:43",
    description:
      "An AI-cloned physician avatar delivering patient counseling guidance in the doctor's own likeness and voice, generated from a short reference clip.",
    videoUrl: DEFAULT_AVATAR_VIDEO_URL,
    configs: [
      { label: "Audience", value: "Patients" },
      { label: "Purpose", value: "Patient Counseling" },
      { label: "Voice", value: "Dr. Piyush's Cloned Voice" },
      { label: "Language", value: "English" },
    ],
  },
];
