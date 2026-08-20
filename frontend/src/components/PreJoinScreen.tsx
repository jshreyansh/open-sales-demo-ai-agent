import { useEffect, useRef, useState } from "react";
import { PERSONAS } from "../lib/personas";
import { getVisitorId, getVisitorProfile } from "../lib/session";
import type { VisitorProfile } from "../lib/session";
import SwishXMark from "./docs/SwishXMark";
import SwishXWordmark from "./SwishXWordmark";
import VisitorGateForm from "./VisitorGateForm";

interface PreJoinScreenProps {
  // Returns false when someone else is already on the call (see
  // server.py's _active_call) — this screen shows the busy message instead
  // of assuming the join succeeded.
  onJoin: (name: string, company: string, email: string) => Promise<boolean>;
}

// Only personas with a real agent behind them render here — right now
// that's just Fiona (see personas.ts). The other 7 exist as locked
// "Coming soon" placeholders for later, but showing them on this screen
// implied a choice that doesn't actually exist yet; hidden until more than
// one persona is real, at which point this goes back to a picker.
const AVAILABLE_PERSONAS = PERSONAS.filter((p) => p.available);

// The hero card's looping clip is decoration — it exists to make a static
// waiting screen feel like a person is on the other end of it, and it carries
// no information the still doesn't. So for anyone who's told the OS they don't
// want motion, we don't play it at all (not "play it slower"): they get the
// same photo the card showed before, which is a complete fallback rather than a
// degraded one. Read live via a listener because macOS/iOS let this flip
// mid-session from Settings, and a card frozen on the old answer looks broken.
function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(query.matches);
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  return reduced;
}

// Meeting Mode's first screen — before the join countdown, not instead of
// it. Identity capture (email → name/company, or straight through for a
// returning email) is delegated to VisitorGateForm, shared with the
// dashboard gate — this component just supplies the video-call chrome
// around it and what happens once someone's actually gated (claim the
// voice lock, or show the busy screen).
//
// Side-by-side layout (persona card left, form right) rather than an
// earlier stacked one: with a single persona to show, a whole horizontal
// scroll lane above the form was doing a lot of layout work for one card.
// Still designed to fit one viewport with no page scroll.

// Her local time, ticking.
//
// "Available now" is a claim; a clock whose seconds visibly move is evidence.
// This page's whole job is to make someone believe a real conversation is one
// click away — no calendar, no waiting on a rep — and nothing argues that as
// cheaply as a number that changes while you read it.
function useLiveClock(timeZone: string) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
    timeZone,
  }).format(now);
}

export default function PreJoinScreen({ onJoin }: PreJoinScreenProps) {
  const persona = AVAILABLE_PERSONAS[0];
  const [busy, setBusy] = useState(false);
  const reducedMotion = usePrefersReducedMotion();
  const localTime = useLiveClock("America/New_York");
  const loopRef = useRef<HTMLVideoElement>(null);
  const showLoop = Boolean(persona.video) && !reducedMotion;

  // The `autoPlay` attribute alone isn't enough to trust. Safari and iOS only
  // honour it when the element is *already* muted and inline at the moment they
  // evaluate it, and React assigns `muted` as a DOM property after the element
  // is created — so we re-assert it here and start playback ourselves. If the
  // browser still says no (some do, in a background tab or under stricter
  // autoplay settings), the rejected promise is swallowed on purpose: the
  // poster is her photo, so refusing to play leaves exactly the static card
  // that shipped before this, with nothing to report and nothing to retry.
  useEffect(() => {
    const video = loopRef.current;
    if (!video) return;
    video.muted = true;
    void video.play().catch(() => {});
  }, [showLoop]);

  async function handleGated(profile: VisitorProfile) {
    const ok = await onJoin(profile.name, profile.company, profile.email);
    if (!ok) setBusy(true);
    // On success the parent unmounts this screen, nothing left to reset here.
  }

  // The voicebot handles one real call at a time (see server.py's
  // _active_call) — this is what tells a second visitor that plainly,
  // instead of letting them join a call that's already silently degrading
  // for someone else.
  if (busy) {
    return (
      <div className="prejoin">
        <div className="prejoin__busy">
          <div className="prejoin__kicker">SwishX · Live Demo</div>
          <h1 className="prejoin__title">{persona.name} is already on a call</h1>
          <p className="prejoin__busy-text">Come back in a few minutes and try again.</p>
          <button type="button" className="prejoin__join" onClick={() => setBusy(false)}>
            Try again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="lp">
      {/* Ambient warmth behind the composition. One soft accent bloom, off to
          the right where nothing sits on top of it — atmosphere, not decoration. */}
      <div className="lp__glow" aria-hidden="true" />

      <header className="lp__nav">
        <div className="lp__brand">
          <SwishXMark size={26} />
          <SwishXWordmark height={17} />
        </div>
        {/* The two other ways into the product. Demoted to nav on purpose:
            they are real destinations, but this page has one job. */}
        <nav className="lp__nav-links">
          <a href="/demo/dashboard">Explore the platform</a>
          <a href="/docs">Docs</a>
        </nav>
      </header>

      <main className="lp__stage">
        <figure className="lp__figure">
          {showLoop ? (
            <video
              ref={loopRef}
              src={persona.video}
              poster={persona.photo}
              className="lp__video"
              autoPlay
              loop
              muted
              playsInline
              preload="auto"
              aria-hidden="true"
            />
          ) : persona.photo ? (
            <img src={persona.photo} alt="" className="lp__video" />
          ) : null}

          {/* Broadcast lower-third. Borrowed deliberately from live TV, which
              is the one visual language everybody already reads as "this is
              happening right now, not a recording." */}
          <div className="lp__onair">
            <span className="lp__dot" aria-hidden="true" />
            <span className="lp__onair-label">Live</span>
            <span className="lp__onair-time">{localTime}</span>
            <span className="lp__onair-place">· {persona.location.split(",")[0]}</span>
          </div>

          <figcaption className="lp__plate">
            <span className="lp__plate-name">{persona.name}</span>
            <span className="lp__plate-role">{persona.position}</span>
          </figcaption>
        </figure>

        <div className="lp__copy">
          {/* The eyebrow states the one fact that makes this page worth
              acting on: she is available this second, not on a calendar. */}
          <div className="lp__eyebrow">
            <span className="lp__dot" aria-hidden="true" />
            Live now — no scheduling
          </div>
          <h1 className="lp__title">
            A demo you can<br />
            <em>interrupt.</em>
          </h1>
          <p className="lp__sub">
            {persona.name} runs SwishX live on this screen — brand dossier to MLR-ready
            asset. Talk over her whenever.
          </p>

          {/* The join row is the signature: it starts inside her frame and
              reaches out to you, so the one thing between arriving and
              talking to her is physically connected to her. */}
          <div className="lp__join">
            <VisitorGateForm
              visitorId={getVisitorId()}
              path="meet"
              submitLabel="Join the call"
              submittingLabel="Connecting…"
              onGated={handleGated}
              initialProfile={getVisitorProfile() ?? undefined}
            />
            <p className="lp__instant">Starts the second you press it. No calendar, no wait.</p>
          </div>

          <button type="button" className="lp__schedule" disabled title="Coming soon">
            Schedule instead
          </button>
        </div>
      </main>

      <footer className="lp__meta">
        <span>10 minutes</span>
        <span>No slides</span>
        <span>No sales engineer</span>
      </footer>
    </div>
  );
}
