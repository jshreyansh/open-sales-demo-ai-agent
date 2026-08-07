import { useState } from "react";
import { PERSONAS } from "../lib/personas";
import MeetIcon from "./MeetIcons";

interface PreJoinScreenProps {
  onJoin: (name: string) => void;
}

// Meeting Mode's first screen — before the join countdown, not instead of
// it. Picking a rep here is mostly the illusion of choice (only one persona
// is actually wired to a working agent, see personas.ts), but capturing the
// visitor's name here — instead of waiting for them to volunteer it
// mid-call — lets the opening greeting address them by name from the very
// first word, which reads as a much more "real" call.
//
// Whole screen is designed to fit one viewport with no page scroll: the
// persona picker is a single-row horizontal lane (its own internal scroll,
// faded at the right edge) rather than a multi-row grid, which is what
// keeps the name input and Join button — the two things that actually
// matter — reliably on-screen without the visitor having to scroll to find
// them.
export default function PreJoinScreen({ onJoin }: PreJoinScreenProps) {
  const [selectedId, setSelectedId] = useState(() => PERSONAS.find((p) => p.available)?.id ?? PERSONAS[0].id);
  const [name, setName] = useState("");

  const canJoin = name.trim().length > 0;

  function handleJoin() {
    if (!canJoin) return;
    onJoin(name.trim());
  }

  return (
    <div className="prejoin">
      <div className="prejoin__inner">
        <div className="prejoin__header">
          <div className="prejoin__kicker">SwishX · Live Demo</div>
          <h1 className="prejoin__title">Choose who you'd like to meet</h1>
          <p className="prejoin__subtitle">Pick a rep for your demo call — they'll greet you by name.</p>
        </div>

        <div className="prejoin__lane">
          {PERSONAS.map((persona) => {
            const selected = selectedId === persona.id;
            return (
              <button
                key={persona.id}
                type="button"
                className={`persona-card ${selected ? "persona-card--selected" : ""} ${
                  !persona.available ? "persona-card--locked" : ""
                }`}
                onClick={() => persona.available && setSelectedId(persona.id)}
                disabled={!persona.available}
              >
                {persona.photo ? (
                  <img src={persona.photo} alt="" className="persona-card__photo" />
                ) : (
                  <div className="persona-card__placeholder">
                    <MeetIcon name="account" size={40} />
                  </div>
                )}
                <span className={`persona-card__status ${persona.available ? "persona-card__status--available" : ""}`}>
                  {persona.available ? "Available now" : "Coming soon"}
                </span>
                <div className="persona-card__overlay">
                  <div className="persona-card__row">
                    <span className="persona-card__name">{persona.name}</span>
                    <span
                      className={`persona-card__radio ${selected ? "persona-card__radio--checked" : ""} ${
                        !persona.available ? "persona-card__radio--disabled" : ""
                      }`}
                    />
                  </div>
                  <div className="persona-card__position">{persona.position}</div>
                  <div className="persona-card__about">{persona.about}</div>
                  <div className="persona-card__nationality">
                    <span className="persona-card__flag">{persona.flag}</span>
                    {persona.nationality}
                  </div>
                </div>
              </button>
            );
          })}
        </div>

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
            Join now
          </button>
          <button type="button" className="prejoin__schedule" disabled title="Coming soon">
            Schedule for later
          </button>
        </div>
      </div>
    </div>
  );
}
