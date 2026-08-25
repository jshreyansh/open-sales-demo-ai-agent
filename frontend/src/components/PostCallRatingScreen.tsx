import { useEffect, useState } from "react";
import { submitCallRating, logCallRatingShown, type CallRatingSentiment } from "../lib/api";

interface PostCallRatingScreenProps {
  visitorId: string;
  callDurationSecs: number;
  disconnectReason: string;
  // Called once the visitor is actually done here (submitted, skipped, or
  // dismissed the thank-you) — the caller (MeetingShell) is what actually
  // reverts to the landing screen; this component only ever asks for that,
  // never does it itself, and never fires it on mount.
  onDone: () => void;
}

type Step = "pick" | "followup" | "thankyou";

// Headline question and quick-reply tags both change with the pick — the
// tags are deliberately not the same four across all three, since "what
// stood out" and "what went wrong" don't share a useful quick-reply
// vocabulary.
const FOLLOWUP_COPY: Record<CallRatingSentiment, { question: string; tags: string[] }> = {
  great: {
    question: "Nice — what stood out?",
    tags: [
      "Felt natural to talk to",
      "Answered my questions clearly",
      "Loved the product walkthrough",
      "Would recommend to a colleague",
    ],
  },
  okay: {
    question: "Thanks — what could've been better?",
    tags: [
      "Felt a bit slow",
      "Some answers were vague",
      "Wanted more specific examples",
      "Conversation felt repetitive",
    ],
  },
  needs_work: {
    question: "Sorry to hear that — what went wrong?",
    tags: [
      "Didn't understand me well",
      "Answers weren't helpful",
      "Felt robotic",
      "Audio/technical issues",
    ],
  },
};

// Deliberately no CTA on okay/needs_work — a rating screen that pushes a
// booking link the moment someone says the call was mediocre or bad reads
// as a sales funnel, not as listening. Only the positive tier gets a link,
// and even that is a plain understated mention, not a button.
const THANK_YOU_COPY: Record<CallRatingSentiment, { text: string; linkHref?: string; linkText?: string }> = {
  great: {
    text: "Really glad to hear that. If you ever want to pick this back up, you know where to find us —",
    linkHref: "https://www.swishx.com/contact",
    linkText: "reach out anytime.",
  },
  okay: {
    text: "Thanks for the honest feedback — genuinely helpful, we'll put it to use.",
  },
  needs_work: {
    text: "Thanks for telling us, and sorry it wasn't a better experience. We've logged this.",
  },
};

const AUTO_RETURN_MS = 3500;

export default function PostCallRatingScreen({
  visitorId,
  callDurationSecs,
  disconnectReason,
  onDone,
}: PostCallRatingScreenProps) {
  const [step, setStep] = useState<Step>("pick");
  const [sentiment, setSentiment] = useState<CallRatingSentiment | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [reason, setReason] = useState("");

  // Fired once, regardless of whether the visitor ever acts on the prompt —
  // this is what makes "shown vs. submitted vs. skipped" funnel drop-off
  // answerable at all (see gate_log.call_rating_events).
  useEffect(() => {
    void logCallRatingShown(visitorId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (step !== "thankyou") return;
    const timer = setTimeout(onDone, AUTO_RETURN_MS);
    return () => clearTimeout(timer);
  }, [step, onDone]);

  function pick(value: CallRatingSentiment) {
    setSentiment(value);
    setStep("followup");
  }

  function toggleTag(tag: string) {
    setSelectedTags((prev) => (prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]));
  }

  function handleSkip() {
    void submitCallRating(visitorId, { skipped: true, callDurationSecs, disconnectReason });
    onDone();
  }

  function handleSubmit() {
    if (!sentiment) return;
    void submitCallRating(visitorId, {
      sentiment,
      reason: reason.trim() || undefined,
      tags: selectedTags.length ? selectedTags : undefined,
      callDurationSecs,
      disconnectReason,
    });
    setStep("thankyou");
  }

  if (step === "pick") {
    return (
      <div className="postcall">
        <div className="postcall__card">
          <h1 className="postcall__title">How did the demo go?</h1>
          <div className="postcall__choices">
            <button type="button" className="postcall__choice" onClick={() => pick("great")}>
              Great
            </button>
            <button type="button" className="postcall__choice" onClick={() => pick("okay")}>
              Okay
            </button>
            <button type="button" className="postcall__choice" onClick={() => pick("needs_work")}>
              Needs work
            </button>
          </div>
          <button type="button" className="postcall__skip" onClick={handleSkip}>
            Skip
          </button>
        </div>
      </div>
    );
  }

  if (step === "followup" && sentiment) {
    const { question, tags } = FOLLOWUP_COPY[sentiment];
    return (
      <div className="postcall">
        <div className="postcall__card">
          <h1 className="postcall__title">{question}</h1>
          <div className="postcall__tags">
            {tags.map((tag) => (
              <button
                key={tag}
                type="button"
                className={"postcall__tag" + (selectedTags.includes(tag) ? " postcall__tag--selected" : "")}
                onClick={() => toggleTag(tag)}
              >
                {tag}
              </button>
            ))}
          </div>
          <textarea
            className="postcall__textarea"
            placeholder="What's the single biggest reason for your rating? (optional)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
          />
          <div className="postcall__actions">
            <button type="button" className="postcall__back" onClick={() => setStep("pick")}>
              Back
            </button>
            <button type="button" className="postcall__submit" onClick={handleSubmit}>
              Submit
            </button>
          </div>
        </div>
      </div>
    );
  }

  const copy = sentiment ? THANK_YOU_COPY[sentiment] : THANK_YOU_COPY.okay;
  return (
    <div className="postcall">
      <div className="postcall__card">
        <p className="postcall__thankyou">
          {copy.text}{" "}
          {copy.linkHref && (
            <a href={copy.linkHref} target="_blank" rel="noopener noreferrer" className="postcall__link">
              {copy.linkText}
            </a>
          )}
        </p>
        <button type="button" className="postcall__done" onClick={onDone}>
          Done
        </button>
      </div>
    </div>
  );
}
