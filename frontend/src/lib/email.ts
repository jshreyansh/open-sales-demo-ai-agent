// Shared by every gate that asks for a work email (Meeting Mode's pre-join
// screen, the dashboard gate) — pulled out to one place instead of two
// near-identical copies, since the whole point is that both surfaces enforce
// the exact same rule.

// Common free/personal providers — blocked so the gate (see FEEDBACK:
// Dushyant's "some sort of gating is required before this agent conversation
// starts") doubles as light friction against casual clicks and a real
// MEDDIC data point (company + a work email) rather than just a name.
const PERSONAL_EMAIL_DOMAINS = new Set([
  "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com",
  "aol.com", "protonmail.com", "live.com", "msn.com", "mail.com",
  "gmx.com", "yandex.com", "zoho.com", "me.com",
]);

// Explicit exceptions to the rule above. Kept as whole addresses rather than
// domains so allowing one person can never accidentally allow all of gmail —
// the gate is doing real work and a wildcard here would quietly switch it off.
const ALLOWED_PERSONAL_EMAILS = new Set([
  // Shreyans, so he can run the flow end to end on an address he actually
  // reads mail on. swishx.com deliverability is currently unreliable (85 hard
  // bounces on that domain in Postmark), which makes testing the OTP on a
  // work address a coin flip.
  "jshreyansh34@gmail.com",
]);

const EMAIL_FORMAT_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateWorkEmail(value: string): string | null {
  const trimmed = value.trim();
  if (!EMAIL_FORMAT_RE.test(trimmed)) return "Enter a valid email address";
  if (ALLOWED_PERSONAL_EMAILS.has(trimmed.toLowerCase())) return null;
  const domain = trimmed.slice(trimmed.lastIndexOf("@") + 1).toLowerCase();
  if (PERSONAL_EMAIL_DOMAINS.has(domain)) return "Please use your work email, not a personal one";
  return null;
}
