import { useState } from "react";
import { PERSONAS } from "../lib/personas";
import { getVisitorId, getVisitorProfile } from "../lib/session";
import type { VisitorProfile } from "../lib/session";
import type { PacePrior } from "../lib/api";
import MeetIcon from "./MeetIcons";
import ShowcaseMedal from "./ShowcaseMedal";
import ExampleGalleryPanel from "./ExampleGalleryPanel";
import VisitorGateForm from "./VisitorGateForm";
import PreCallCalibrationScreen from "./PreCallCalibrationScreen";
import swishxLightLogo from "../assets/swishx-lockup-light.svg";

interface PreJoinScreenProps {
  // Returns false when someone else is already on the call (see
  // server.py's _active_call) — this screen shows the busy message instead
  // of assuming the join succeeded.
  onJoin: (name: string, company: string, email: string, pacePrior?: PacePrior) => Promise<boolean>;
}

// Only personas with a real agent behind them render here — right now
// that's just Fiona (see personas.ts). The other 7 exist as locked
// "Coming soon" placeholders for later, but showing them on this screen
// implied a choice that doesn't actually exist yet; hidden until more than
// one persona is real, at which point this goes back to a picker.
const AVAILABLE_PERSONAS = PERSONAS.filter((p) => p.available);

// Meeting Mode's first screen — before the join countdown, not instead of
// it. Identity capture (email → name/company, or straight through for a
// returning email) is delegated to VisitorGateForm, shared with the
// dashboard gate — this component just supplies the chrome around it and
// what happens once someone's actually gated (claim the voice lock, or
// show the busy screen).
//
// Centered layout, page scrolls: the hero (badge/heading/join form) sits in
// roughly the first viewport, and the SwishX guided widget lives in a
// second section right below it, deliberately tall enough that only its top
// edge shows without scrolling — the same "there's more, keep going"
// invitation a product screenshot peeking up from the fold gives on other
// SaaS landing pages. The persona's own big looping video card is gone
// (see the live badge below instead) — a whole side-by-side column doesn't
// fit a centered composition, and the widget itself is now the thing that
// makes the page feel alive.

// The seconds-ticking clock that used to live here is gone. It was meant as
// proof that "now" was real, but a running counter beside a face reads as a
// stopwatch on the visitor rather than as an open line — the opposite of
// relaxed and available. The pulsing LIVE dot on the badge carries the same
// claim without implying anyone is being timed.

export default function PreJoinScreen({ onJoin }: PreJoinScreenProps) {
  const persona = AVAILABLE_PERSONAS[0];
  const [busy, setBusy] = useState(false);
  // Held between the visitor gating successfully and them answering the
  // calibration question below — non-null means "show the calibration
  // screen instead of anything else." onJoin itself doesn't fire until
  // that answer comes back, so a real connection never starts one beat
  // ahead of the question it's supposed to be calibrated by.
  const [pendingProfile, setPendingProfile] = useState<VisitorProfile | null>(null);
  // The same showcase the agent opens mid-call. Someone weighing up whether
  // to start a live call is exactly the person who wants to see output first,
  // and until now that proof only existed on the far side of the thing they
  // were hesitating about.
  const [galleryOpen, setGalleryOpen] = useState(false);

  function handleGated(profile: VisitorProfile) {
    setPendingProfile(profile);
  }

  async function handleCalibrationChoice(pacePrior: PacePrior | undefined) {
    if (!pendingProfile) return;
    const ok = await onJoin(pendingProfile.name, pendingProfile.company, pendingProfile.email, pacePrior);
    setPendingProfile(null);
    if (!ok) setBusy(true);
    // On success the parent unmounts this screen, nothing left to reset here.
  }

  if (pendingProfile) {
    return <PreCallCalibrationScreen onChoose={handleCalibrationChoice} />;
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
        <a href="https://www.swishx.com/" target="_blank" rel="noopener noreferrer" aria-label="SwishX — swishx.com">
          <img src={swishxLightLogo} alt="SwishX" className="lp__logo" />
        </a>
        {/* Best Content Showcase is the one nav destination left up here —
            "Talk to the team" and "Explore the platform" moved down to the
            footer (see .lp__footer below the widget), so the header stays
            to just the logo and the one link that's actually about this
            exact page (proving the output before asking anyone to commit
            to a live call). */}
        <nav className="lp__nav-links">
          {/* Demoted from a big glowing hero badge to a plain nav pill —
              next to the quiet "Fiona is live now" badge it read as two
              different products' styling stitched together, and it was
              eating hero height the widget section needed. Still opens the
              same gallery, just as a secondary nav destination rather than
              the loudest thing on the page. */}
          <button onClick={() => setGalleryOpen(true)} title="See the best content SwishX has generated">
            <ShowcaseMedal size={14} />
            Best Content Showcase
          </button>
        </nav>
      </header>

      <main className="lp__stage lp__stage--centered">
        <div className="lp__hero">
          {/* Replaces the old full-size looping video card — same "she's
              live right now" claim, at a scale that fits a centered hero
              instead of owning half the page. */}
          <div className="lp__live-badge">
            {persona.photo && <img src={persona.photo} alt="" className="lp__live-badge-photo" />}
            <span className="lp__live-badge-text">
              <span className="lp__dot" aria-hidden="true" />
              {persona.name} is live now
            </span>
          </div>
          {/* "Right now" lands bold on its own line — that's the actual
              claim being made, not just a tagline; a visitor's first
              instinct on seeing "live demo" is to assume it means "book a
              slot," so the payoff line has to say otherwise immediately. */}
          <h1 className="lp__title">
            <span className="lp__title-soft">
              Experience{" "}
              <a href="https://www.swishx.com/" target="_blank" rel="noopener noreferrer" className="lp__title-link">
                SwishX
              </a>{" "}
              Live,
            </span>
            <br />
            Right Now.
          </h1>
          {/* Directly answers the doubt this copy is built to kill: that
              clicking through doesn't actually connect you to a live AI
              agent instantly, any hour — "skip the scheduling cycle" and
              "24/7" say that outright instead of leaving it implied by the
              live badge alone. */}
          <p className="lp__sub">
            Skip the scheduling cycle. Join an instant, 24/7 interactive demo
            with our AI agent to watch pharma-ready content get built in real time.
          </p>

          <div className="lp__join">
            <VisitorGateForm
              visitorId={getVisitorId()}
              path="meet"
              continueLabel="Join Live Demo"
              submitLabel="Join the video call"
              submittingLabel="Connecting…"
              onGated={handleGated}
              initialProfile={getVisitorProfile() ?? undefined}
            />
            <p className="lp__instant">Starts the second you press it. No calendar, no wait.</p>
          </div>

          {/* "Schedule instead" used to sit here, permanently disabled with a
              "Coming soon" title. A dead control earns no space — and with
              the booking link promoted into the nav, the person it was aimed
              at is already served. Bring it back when scheduling is real. */}
        </div>

        {/* The widget section: deliberately positioned so only its top edge
            is visible without scrolling (see .lp__hero's min-height) — the
            same "there's more below" invitation a peeking product
            screenshot gives on other SaaS landing pages, except this one is
            live and interactive rather than a static image. */}
        <div className="lp__widget-section">
          <div className="lp__widget-card">
            {/* 1475, not 1180: the widget's own composition logic never
                upscales past 1.25x its 1180px logical design width (see
                MAX_SCALE in swishx-widget.js) — 1180 was capping it at
                exactly native size with zero room to grow on a big
                monitor. 1475 is the highest value that actually changes
                anything; anything above it hits the same internal ceiling. */}
            <swishx-widget max-width="1475" />
          </div>
        </div>
      </main>

      {/* "Talk to the team" and "Explore the platform" moved down here from
          the header nav — centered under the widget, the natural place to
          land once someone's scrolled all the way through the page rather
          than competing with the logo up top. */}
      <footer className="lp__footer">
        <a
          className="lp__nav-talk"
          href="https://www.swishx.com/calendar"
          target="_blank"
          rel="noopener noreferrer"
        >
          <MeetIcon name="calendar" size={14} />
          Talk to the team
        </a>
        <a href="/demo/dashboard">
          <MeetIcon name="grid" size={14} />
          Explore the platform
        </a>
      </footer>

      {galleryOpen && <ExampleGalleryPanel onClose={() => setGalleryOpen(false)} />}
    </div>
  );
}
