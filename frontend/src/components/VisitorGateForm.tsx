import { useEffect, useState } from "react";
import { validateWorkEmail } from "../lib/email";
import { lookupVisitor, reportGateAttempt, sendVisitorOtp, verifyVisitorOtp } from "../lib/api";
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

// "code" sits between "email" and the two identity steps: the visitor proves
// the address is theirs before we say anything at all about whether we know
// it. Everything from "known"/"new" onward is exactly what it was before
// verification existed.

// OTP verification is OFF.
//
// It is built, tested and working — Postmark accepts every send with
// ErrorCode 0 — but nothing is arriving. The sending identity is
// noreply@swishclub.in while the audience is @swishx.com, two domains that
// between them already carry ~200 hard bounces on this Postmark server, so
// mail is being accepted and then silently dropped. Gating entry on an email
// that never lands would lock every visitor out, and from tomorrow that
// includes the whole company.
//
// So the gate degrades to what it was before: we still collect and validate
// the address, we simply don't prove ownership of it. Everything behind this
// flag stays wired — the endpoints, the code screen, the resend countdown,
// the rate limits — so switching it back on is one env var once the new
// sending domain and Postmark key are in place, not a rebuild.
//
//   VITE_OTP_ENABLED=true
//
// Off unless explicitly enabled, so a missing env var can never lock people
// out by accident. That asymmetry is deliberate: the failure mode of "off
// when it should be on" is a weaker gate, and the failure mode of "on when
// it should be off" is nobody gets in at all.
const OTP_ENABLED = import.meta.env.VITE_OTP_ENABLED === "true";

type Step = "email" | "code" | "known" | "new";

const CODE_LENGTH = 6;

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
  const [code, setCode] = useState("");
  const [codeError, setCodeError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  // Seconds left on the resend cooldown. The backend enforces the real 30s
  // limit (see server.py's "cooldown" error) — this only mirrors it so the
  // button explains itself instead of failing when pressed.
  const [resendIn, setResendIn] = useState(0);

  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = window.setInterval(() => setResendIn((s) => (s <= 1 ? 0 : s - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [resendIn > 0]);

  // The lookup/known/new half of the flow, unchanged — just no longer reached
  // straight from the email field. Only a verified address gets here, which
  // is the whole point: until then nothing has revealed whether we know it.
  async function continueAfterVerification(verifiedEmail: string) {
    setChecking(true);
    const result = await lookupVisitor(verifiedEmail);
    setChecking(false);
    if (result.known && result.name && result.company) {
      setName(result.name);
      setCompany(result.company);
      setStep("known");
    } else {
      setStep("new");
    }
  }

  async function handleEmailSubmit() {
    if (checking) return;
    const error = validateWorkEmail(email);
    if (error) {
      setEmailError(error);
      void reportGateAttempt(visitorId, email.trim(), path, "blocked_personal_email");
      return;
    }
    setEmailError(null);

    if (!OTP_ENABLED) {
      // Straight to the existing lookup, exactly as this form behaved before
      // verification existed.
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
      return;
    }

    setChecking(true);
    const sent = await sendVisitorOtp(email.trim());
    setChecking(false);
    if (sent.ok) {
      setCode("");
      setCodeError(null);
      setResendIn(30);
      setStep("code");
      return;
    }
    // A cooldown reply means a code went out moments ago and is still valid —
    // so this is a double-submit, not a failure, and the right place for the
    // visitor is the code screen with the countdown already running.
    if (sent.code === "cooldown") {
      setCodeError(sent.message);
      setResendIn(sent.retryAfter ?? 30);
      setStep("code");
      return;
    }
    setEmailError(sent.message);
  }

  // Takes the code as an argument rather than reading it off state. The
  // auto-submit below fires from inside the same onChange that calls
  // setCode, and at that point `code` still holds the PREVIOUS render's value
  // — so a state read here sees five digits on the keystroke that completes
  // the sixth, and the length guard silently swallows the submit. Caught by
  // driving the real form in a browser, where typing the last digit did
  // nothing at all.
  async function handleVerify(submitted: string = code) {
    if (verifying || submitted.length !== CODE_LENGTH) return;
    setVerifying(true);
    const result = await verifyVisitorOtp(email.trim(), submitted);
    setVerifying(false);
    if (result.ok) {
      setCodeError(null);
      await continueAfterVerification(email.trim());
      return;
    }
    setCode("");
    setCodeError(result.message);
    // These three all mean the current code is dead, so the only useful next
    // action is a new one — drop the cooldown rather than making them wait
    // out a timer for a code that can no longer work.
    if (result.code === "expired" || result.code === "too_many_attempts" || result.code === "no_code") {
      setResendIn(0);
    }
  }

  async function handleResend() {
    if (resendIn > 0 || checking) return;
    setChecking(true);
    const sent = await sendVisitorOtp(email.trim());
    setChecking(false);
    setCode("");
    if (sent.ok) {
      setCodeError(null);
      setResendIn(30);
      return;
    }
    setCodeError(sent.message);
    if (sent.retryAfter) setResendIn(sent.retryAfter);
  }

  function handleChangeEmail() {
    setStep("email");
    setName("");
    setCompany("");
    // A different address is a different identity — whatever was verified for
    // the old one must not carry over.
    setCode("");
    setCodeError(null);
    setResendIn(0);
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
          {checking ? "Sending code…" : "Continue"}
        </button>
      </div>
    );
  }

  if (step === "code") {
    return (
      <div className="prejoin__fields">
        <div className="prejoin__name">
          <label htmlFor="gate-code">Enter the 6-digit code</label>
          <input
            id="gate-code"
            className="prejoin__code-input"
            type="text"
            // Not type="number": it brings a spinner, allows "e"/"-", and
            // strips leading zeros — all wrong for a fixed-length code.
            // inputMode drives the numeric keypad on mobile without any of that.
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={CODE_LENGTH}
            placeholder="000000"
            value={code}
            onChange={(e) => {
              const digits = e.target.value.replace(/\D/g, "").slice(0, CODE_LENGTH);
              setCode(digits);
              if (codeError) setCodeError(null);
              // Submitting on the sixth digit saves a click on the one screen
              // where the visitor has nothing else to decide. Passed
              // explicitly — see handleVerify on why reading state here
              // doesn't work.
              if (digits.length === CODE_LENGTH) void handleVerify(digits);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleVerify();
            }}
            autoFocus
          />
          <div className="prejoin__code-sent">Sent to {email.trim()}</div>
          {codeError && <div className="prejoin__field-error">{codeError}</div>}
          <button type="button" className="prejoin__change-email" onClick={handleChangeEmail}>
            Use a different email
          </button>
        </div>

        <button
          type="button"
          className="prejoin__join"
          disabled={code.length !== CODE_LENGTH || verifying || checking}
          onClick={() => void handleVerify()}
        >
          {verifying ? "Verifying…" : checking ? "Checking…" : "Verify"}
        </button>

        <button
          type="button"
          className="prejoin__resend"
          disabled={resendIn > 0 || checking}
          onClick={() => void handleResend()}
        >
          {resendIn > 0 ? `Resend code in ${resendIn}s` : "Resend code"}
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
