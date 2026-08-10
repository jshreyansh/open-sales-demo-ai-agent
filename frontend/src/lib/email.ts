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

const EMAIL_FORMAT_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function validateWorkEmail(value: string): string | null {
  const trimmed = value.trim();
  if (!EMAIL_FORMAT_RE.test(trimmed)) return "Enter a valid email address";
  const domain = trimmed.slice(trimmed.lastIndexOf("@") + 1).toLowerCase();
  if (PERSONAL_EMAIL_DOMAINS.has(domain)) return "Please use your work email, not a personal one";
  return null;
}
