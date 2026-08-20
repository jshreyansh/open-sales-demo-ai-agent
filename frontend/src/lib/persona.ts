import agentPhoto from "../assets/fiona.png";

// The one place the agent's name lives on the frontend (see backend/src/persona.py
// for its backend twin — the two can't share a literal across languages, but each
// side only needs one constant changed, not every string that mentions the name).
export const AGENT_NAME = "Fiona";
export const AGENT_INITIAL = AGENT_NAME.charAt(0).toUpperCase();
export const AGENT_PHOTO = agentPhoto;

// Mirrors backend/src/context/store.py's OPENING_GREETING — kept in sync by hand
// (this is what the browser shows instantly, before the voice pipeline's own copy
// of the same line ever reaches it), but the *name* portion tracks AGENT_NAME here
// same as the backend's tracks AGENT_NAME there.
export const AGENT_GREETING =
  `Hi, I'm ${AGENT_NAME}, sales rep at SwishX. Want me to give you a walkthrough of the ` +
  "platform, or is there something specific on your mind first?";
