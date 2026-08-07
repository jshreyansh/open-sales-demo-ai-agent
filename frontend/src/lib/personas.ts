import { AGENT_NAME, AGENT_PHOTO } from "./persona";

// The pre-join "pick your rep" screen's catalog. Only one persona actually
// has a working agent behind it right now (AGENT_NAME/AGENT_PHOTO from
// persona.ts, wired through the whole backend); the rest exist so the
// picker doesn't look like a picker of one, and are marked `available:
// false` so they render locked instead of selectable. Picking one of them
// does nothing today — this is deliberately just the illusion of choice
// until more personas are actually built out.
export interface Persona {
  id: string;
  name: string;
  position: string;
  about: string;
  nationality: string;
  flag: string;
  photo?: string;
  available: boolean;
}

export const PERSONAS: Persona[] = [
  {
    id: "us-female",
    name: AGENT_NAME,
    position: "Senior Sales Manager",
    about: "I still get a kick out of walking people through this demo.",
    nationality: "American",
    flag: "🇺🇸",
    photo: AGENT_PHOTO,
    available: true,
  },
  {
    id: "us-male",
    name: "Ryan Cole",
    position: "Senior Sales Manager",
    about: "I'll get straight to what matters to you — no filler, no fluff.",
    nationality: "American",
    flag: "🇺🇸",
    available: false,
  },
  {
    id: "fr-male",
    name: "Lucas Moreau",
    position: "Senior Sales Manager",
    about: "Ask me anything — I'd rather answer than pitch.",
    nationality: "French",
    flag: "🇫🇷",
    available: false,
  },
  {
    id: "fr-female",
    name: "Camille Laurent",
    position: "Senior Sales Manager",
    about: "I like a good question more than a good script.",
    nationality: "French",
    flag: "🇫🇷",
    available: false,
  },
  {
    id: "gb-male",
    name: "Oliver Bennett",
    position: "Senior Sales Manager",
    about: "Calm, clear, and happy to go as deep as you want.",
    nationality: "British",
    flag: "🇬🇧",
    available: false,
  },
  {
    id: "gb-female",
    name: "Emily Clarke",
    position: "Senior Sales Manager",
    about: "I keep demos tight and focused on what you actually need.",
    nationality: "British",
    flag: "🇬🇧",
    available: false,
  },
  {
    id: "in-male",
    name: "Arjun Mehta",
    position: "Senior Sales Manager",
    about: "I'll find the one thing in here that actually solves your problem.",
    nationality: "Indian",
    flag: "🇮🇳",
    available: false,
  },
  {
    id: "in-female",
    name: "Ananya Sharma",
    position: "Senior Sales Manager",
    about: "Curious about your workflow first, product second.",
    nationality: "Indian",
    flag: "🇮🇳",
    available: false,
  },
];
