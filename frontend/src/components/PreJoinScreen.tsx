import { useState } from "react";
import { PERSONAS } from "../lib/personas";

interface PreJoinScreenProps {
  // Returns false when someone else is already on the call (see
  // server.py's _active_call) — this screen shows the busy message instead
  // of assuming the join succeeded.
  onJoin: (name: string) => Promise<boolean>;
}

// Only personas with a real agent behind them render here — right now
// that's just Fiona (see personas.ts). The other 7 exist as locked
// "Coming soon" placeholders for later, but showing them on this screen
// implied a choice that doesn't actually exist yet; hidden until more than
// one persona is real, at which point this goes back to a picker.
const AVAILABLE_PERSONAS = PERSONAS.filter((p) => p.available);

// Meeting Mode's first screen — before the join countdown, not instead of
// it. Capturing the visitor's name here — instead of waiting for them to
// volunteer it mid-call — lets the opening greeting address them by name
// from the very first word, which reads as a much more "real" call.
//
// Side-by-side layout (persona card left, name/join right) rather than the
// earlier stacked one: with a single persona to show, a whole horizontal
// scroll lane above the form was doing a lot of layout work for one card.
// Still designed to fit one viewport with no page scroll.
export default function PreJoinScreen({ onJoin }: PreJoinScreenProps) {
  const persona = AVAILABLE_PERSONAS[0];
  const [name, setName] = useState("");
  const [joining, setJoining] = useState(false);
  const [busy, setBusy] = useState(false);

  const canJoin = name.trim().length > 0 && !joining;

  async function handleJoin() {
    if (!canJoin) return;
    setJoining(true);
    const ok = await onJoin(name.trim());
    if (!ok) {
      setBusy(true);
      setJoining(false);
    }
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
            {persona.photo ? (
              <img src={persona.photo} alt="" className="persona-card__photo" />
            ) : (
              <div className="persona-card__placeholder" />
            )}
            <span className="persona-card__status persona-card__status--available">Available now</span>
            <div className="persona-card__overlay">
              <div className="persona-card__row">
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
              <div className="persona-card__about">{persona.about}</div>
              <div className="persona-card__nationality">
                <span className="persona-card__flag">{persona.flag}</span>
                {persona.nationality}
              </div>
            </div>
          </div>

          <div className="prejoin__form">
            <div className="prejoin__name">
              <label htmlFor="prejoin-name">Your name</label>
              <input
                id="prejoin-name"
                type="text"
                placeholder="e.g. Alex"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleJoin();
                }}
                autoFocus
              />
            </div>

            <div className="prejoin__actions">
              <button type="button" className="prejoin__join" disabled={!canJoin} onClick={handleJoin}>
                {joining ? "Checking…" : "Join now"}
              </button>
              <button type="button" className="prejoin__schedule" disabled title="Coming soon">
                Schedule for later
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
