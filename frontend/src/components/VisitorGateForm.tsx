import { useState } from "react";
import { validateWorkEmail } from "../lib/email";
import { lookupVisitor, reportGateAttempt } from "../lib/api";
import { setVisitorProfile, type VisitorProfile } from "../lib/session";

interface VisitorGateFormProps {
  visitorId: string;
  path: "dashboard" | "meet";
  submitLabel: string;
  submittingLabel?: string;
  onGated: (profile: VisitorProfile) => void;
  // Already known this tab (see session.ts's getVisitorProfile) — e.g. the
  // visitor gated on /demo/dashboard earlier and is now reaching /demo/meet
  // in the same tab. Starts the form straight on the "known" step, pre-filled,
  // so the only thing left to do is the one explicit action button (still
  // required for Meeting Mode, since joining a live call is its own deliberate
  // step distinct from just having given an email once already).
  initialProfile?: VisitorProfile;
}

type Step = "email" | "known" | "new";

// Shared by both gated entry points (Meeting Mode's pre-join screen and the
// dashboard gate) — one identity-capture flow, not two near-copies. Deliberately
// email-first: a returning visitor (same email, looked up via
// /api/visitor/lookup) never has to retype their name/company, matching what
// was asked for; a new visitor sees those fields only once their email has
// actually cleared validation.
export default function VisitorGateForm({ visitorId, path, submitLabel, submittingLabel, onGated, initialProfile }: VisitorGateFormProps) {
  const [step, setStep] = useState<Step>(initialProfile ? "known" : "email");
  const [email, setEmail] = useState(initialProfile?.email ?? "");
  const [emailError, setEmailError] = useState<string | null>(null);
  const [name, setName] = useState(initialProfile?.name ?? "");
  const [company, setCompany] = useState(initialProfile?.company ?? "");
  const [checking, setChecking] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleEmailSubmit() {
    if (checking) return;
    const error = validateWorkEmail(email);
    if (error) {
      setEmailError(error);
      void reportGateAttempt(visitorId, email.trim(), path, "blocked_personal_email");
      return;
    }
    setEmailError(null);
    setChecking(true);
    const result = await lookupVisitor(email.trim());
    setChecking(false);
    if (result.known && result.name && result.company) {
      setName(result.name);
      setCompany(result.company);
      setStep("known");
    } else {
      setStep("new");
    }
  }

  function handleChangeEmail() {
    setStep("email");
    setName("");
    setCompany("");
  }

  async function handleFinalSubmit() {
    if (submitting) return;
    if (step === "new" && (!name.trim() || !company.trim())) return;
    setSubmitting(true);
    const trimmedEmail = email.trim();
    const trimmedName = name.trim();
    const trimmedCompany = company.trim();
    await reportGateAttempt(visitorId, trimmedEmail, path, "allowed", trimmedName, trimmedCompany);
    const profile: VisitorProfile = { name: trimmedName, company: trimmedCompany, email: trimmedEmail };
    setVisitorProfile(profile);
    onGated(profile);
    // On success the parent unmounts this form, nothing left to reset here.
  }

  if (step === "email") {
    return (
      <div className="prejoin__fields">
        <div className="prejoin__name">
          <label htmlFor="gate-email">Work email</label>
          <input
            id="gate-email"
            type="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              if (emailError) setEmailError(null);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleEmailSubmit();
            }}
            autoFocus
          />
          {emailError && <div className="prejoin__field-error">{emailError}</div>}
        </div>
        <button type="button" className="prejoin__join" disabled={!email.trim() || checking} onClick={() => void handleEmailSubmit()}>
          {checking ? "Checking…" : "Continue"}
        </button>
      </div>
    );
  }

  return (
    <div className="prejoin__fields">
      <div className="prejoin__name">
        <label htmlFor="gate-email-locked">Work email</label>
        <input id="gate-email-locked" type="email" value={email} disabled />
        <button type="button" className="prejoin__change-email" onClick={handleChangeEmail}>
          Not you? Change email
        </button>
      </div>

      {step === "new" && (
        <>
          <div className="prejoin__name">
            <label htmlFor="gate-name">Your name</label>
            <input
              id="gate-name"
              type="text"
              placeholder="Your name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleFinalSubmit();
              }}
              autoFocus
            />
          </div>
          <div className="prejoin__name">
            <label htmlFor="gate-company">Company</label>
            <input
              id="gate-company"
              type="text"
              placeholder="Your company"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleFinalSubmit();
              }}
            />
          </div>
        </>
      )}

      {step === "known" && (
        <div className="prejoin__name">
          <label>Name &amp; company</label>
          <div className="prejoin__known-identity">
            {name} · {company}
          </div>
        </div>
      )}

      <button
        type="button"
        className="prejoin__join"
        disabled={submitting || (step === "new" && (!name.trim() || !company.trim()))}
        onClick={() => void handleFinalSubmit()}
      >
        {submitting ? submittingLabel || "Checking…" : submitLabel}
      </button>
    </div>
  );
}
