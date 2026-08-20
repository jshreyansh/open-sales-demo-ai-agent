import { useEffect, useRef, useState } from "react";
import { PERSONAS } from "../lib/personas";
import { getVisitorId, getVisitorProfile } from "../lib/session";
import type { VisitorProfile } from "../lib/session";
import MeetIcon from "./MeetIcons";
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
export default function PreJoinScreen({ onJoin }: PreJoinScreenProps) {
  const persona = AVAILABLE_PERSONAS[0];
  const [busy, setBusy] = useState(false);
  const reducedMotion = usePrefersReducedMotion();
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
    <div className="prejoin">
      <div className="prejoin__inner">
        <div className="prejoin__header">
          <div className="prejoin__kicker">SwishX · Live Demo</div>
          <h1 className="prejoin__title">AI Marketing and design agency at your fingertips</h1>
        </div>

        <div className="prejoin__layout">
          <div className="persona-card persona-card--hero">
            {/* The card fill, in descending order of liveliness: the silent
                loop, her still, then a gradient. `poster` is that same still,
                so the first paint is identical either way — no black frame
                while the video decodes, and no layout shift, since the card's
                box is fixed by CSS rather than by the media's intrinsic size.
                aria-hidden + no controls: it's a backdrop, not something to
                watch or operate. */}
            {showLoop ? (
              <video
                ref={loopRef}
                src={persona.video}
                poster={persona.photo}
                className="persona-card__loop"
                autoPlay
                loop
                muted
                playsInline
                preload="auto"
                aria-hidden="true"
              />
            ) : persona.photo ? (
              <img src={persona.photo} alt="" className="persona-card__photo" />
            ) : (
              <div className="persona-card__placeholder" />
            )}
            <span className="persona-card__status persona-card__status--available">Available now</span>
            <div className="persona-card__overlay">
              <div className="persona-card__row">
                {/* Her still, kept on the card as a thumbnail now that the loop
                    has taken over the full bleed. It's the same image the
                    meeting tile and chat launcher use, so the face that
                    introduces her here is the one that follows her through the
                    rest of the session — and it's still visible on the card
                    when the video is playing over the top of the poster. */}
                {persona.photo && showLoop ? (
                  <img src={persona.photo} alt="" className="persona-card__thumb" />
                ) : null}
                <span className="persona-card__name">
                  {persona.name}
                  <span className="persona-card__verified" title="Verified">
                    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                      <circle cx="12" cy="12" r="12" fill="#22c55e" />
                      <path
                        d="M8.2 12.4l2.4 2.4 5.2-5.6"
                        stroke="#fff"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        fill="none"
                      />
                    </svg>
                  </span>
                </span>
              </div>
              <div className="persona-card__position">{persona.position}</div>
              <div className="persona-card__location">
                <MeetIcon name="location" size={14} />
                {persona.location}
              </div>
            </div>
          </div>

          <div className="prejoin__form">
            <VisitorGateForm
              visitorId={getVisitorId()}
              path="meet"
              submitLabel="Join Product Demo"
              submittingLabel="Checking…"
              onGated={handleGated}
              initialProfile={getVisitorProfile() ?? undefined}
            />

            <div className="prejoin__actions">
              <button type="button" className="prejoin__schedule" disabled title="Coming soon">
                Schedule for later
              </button>
            </div>

            {/* The other two ways into the product. These used to live on a
                separate chooser page at "/" whose only job was routing —
                it put a page and a click between arriving and joining a
                call, which is the single thing this product exists to do.
                That page is gone; these come with it, sitting below the
                join flow so the hierarchy still reads primary-then-side-door.

                Plain <a> rather than navigate(): /docs and /demo/dashboard
                are separate destinations a visitor may well want to open in
                a new tab, and an anchor gets middle-click, cmd-click and
                "copy link" for free. */}
            <div className="prejoin__alt">
              <a className="prejoin__alt-btn" href="/demo/dashboard">
                Try &amp; Use Demo Platform
              </a>
              <a className="prejoin__alt-btn" href="/docs">
                Platform Documentation
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
