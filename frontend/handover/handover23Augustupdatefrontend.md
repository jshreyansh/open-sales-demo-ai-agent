# Frontend Handover — 2026-08-23

**For:** whoever (human or agent) picks up frontend work on this next.
**Covers:** the last ~4 days, 2026-08-20 through 2026-08-23 (17 frontend-touching commits) — mostly a brand/positioning pass plus a run of voice-call UX polish driven by real test calls.
**Written by:** Claude Code, closing out this stretch of work.

Read `frontend/VISION.md` and `frontend/ARCHITECTURE.md` first if you haven't — they're Aug 5 inception docs, explicitly scoped to "Phase 0 → Phase 1 only," and predate voice, Meeting Mode, and basically everything below. This doc is the current-state supplement. The root-level `handover/handover23Augustupdate.md` covers the whole project since inception; this one is a close-up on the last few days.

---

## The big picture

This stretch was two things running in parallel: (1) a rebrand and landing-page pass — the product had been ContentIQ-branded, this window moved it to **SwishX** properly (real logo assets, real lockup, a front door that's actually the live demo rather than generic marketing copy), and (2) a series of voice-call UX fixes that only surfaced because real people were testing real calls and reporting exactly what felt wrong. Almost nothing here was speculative polish — each change traces to either a specific visual mismatch against the real reference product, or a specific moment in a real call transcript.

## Architecture as it stands

```
frontend/
  src/
    pages/                    # Dashboard, Analytics, Content Studio, Brand Kit, MLR Review, /docs
    components/
      MeetingShell.tsx          # the Google-Meet-style Presentation Shell wrapper
      MeetingChatPanel.tsx      # in-call typed chat (interrupts/answers voice exactly like a mic barge-in)
      PreJoinScreen.tsx         # persona pick + pre-join gate, before the join countdown
      studio/                   # MagicReel / MagicAvatar wizard components
    lib/
      uiRegistry.ts              # components self-register their actions here — the frontend half of
                                  # the registry contract backend/src/agent/registry.py mirrors
      persona.ts                 # AGENT_NAME/AGENT_PHOTO/AGENT_VIDEO — the ONE place to rename/re-asset the agent
      personas.ts                 # the pre-join persona picker's catalog (only Fiona is real; rest are locked placeholders)
      pipecatClient.ts             # voice transport wiring
      highlightBridge.ts            # unified `data-hl="component:method"` highlight/cursor-flourish system
    assets/                    # fiona-loop.mp4, fiona.png, etc. — see persona.ts
```

`?mode=meeting|product` still selects the two framings of the same underlying product (Meeting Mode's Presentation Shell vs. a plain chat-widget-on-product Product Mode) — this split goes back to day one and hasn't changed shape, just gotten more polished.

Every actionable component **must** self-register into `uiRegistry.ts` — if it doesn't, it's invisible to the agent, by design (forces the registry to stay an accurate map rather than drifting). `scripts/check-highlight-registry.py` (backend-side) catches drift between backend's `registry.py` and frontend's actual registrations — run it if you add a new actionable component and things don't seem to be firing.

## What actually happened, day by day

### Aug 20 — turn ownership, Fiona's card loops

Part of the same combined commit as the backend's turn-taking overhaul: "give turn ownership to the backend, and loop Fiona's card" — the pre-join/meeting persona card got a genuinely looping video instead of a static frame, and some turn-taking UI state that used to be inferred client-side moved to just reflecting what the backend already decided.

### Aug 21 — the rebrand + landing page + polish day

This was the single busiest frontend day of the stretch, in roughly this order:

- **"Make the live demo the front door"** — the landing page redesign's core thesis: don't lead with marketing copy, lead with the actual product experience. Two follow-up passes refined the composition ("redesign the front door around the one thing that makes it worth clicking," then "point the front door at SwishX, and make 'live' read at a glance").
- **Real logo work, in stages**: first got the real lockup reproduced from the supplied asset instead of rebuilt by eye, then swapped in the real dark-surface logo variant instead of programmatically recoloring the light one (a recolored logo reads subtly wrong — worth remembering if a dark-mode asset is ever missing again: ask for the real dark variant rather than recoloring).
- **Navigation simplified**: sidebar cut down to three groups, the header's redundant second layer dropped.
- **Pre-join gate polish**: designed for its fullest visual state (previously only really tuned for the empty/default state), the "live" badge moved out of the way of other content.
- **A real product-honesty catch**: the landing page's subheadline was overclaiming — something like "an AI rep builds it live on this screen," which isn't what happens (the agent shows around an existing pixel-accurate replica, it doesn't generate anything live). The user caught this directly and asked for a "24/7, always available to show you around" framing instead. Worth remembering as a standing bar: **marketing copy on this landing page has to be literally true about what the demo does**, not just directionally true.
- **Gating fix**: "stop gating on mail that never arrives" — the pre-join flow no longer blocks on an email step, opens straight into the conversation, and the visitor can stop it themselves rather than being forced through a funnel.
- **Dashboard hierarchy pass**: "always bridge the silence, and stop the dashboard advertising what we deleted" — a visual-hierarchy cleanup plus removing dashboard elements that referenced features/tiles that had already been cut elsewhere (a good instance of the general lesson: when you remove a feature, grep for anything that still advertises it).
- **Voice UX**: pause now actually stops the agent's speech (previously it may have just suppressed new speech while letting an in-flight sentence finish), and the "bridging" filler phrases used to cover thinking-latency were varied so they don't read as a single robotic tic repeated every turn.
- **Real test-call fixes**: mic noise suppression added client-side (a genuine `applyConstraints()` call on the live mic track, since `WebSocketTransport` has no constraints hook of its own — confirmed by reading its dist directly, not assumed) plus honest chat-vs-voice telemetry separation, both driven by a colleague's real keyboard/headphone test.

### Aug 22 — pre-join video swap

The pre-join hero video (the looping persona clip introduced Aug 20) got swapped for a new supplied clip. Two real issues found and fixed before it shipped, not after:
- The new source video had a visible AI-generation-tool watermark burned into every frame (bottom-right corner) — cropped out with a precise bottom-band crop, verified clean across first/middle/last frame, with enough margin that hands/gesture framing wasn't clipped.
- The new clip's native aspect ratio didn't match the old one, and the card's CSS (`.lp__figure`) had the old ratio hardcoded to an exact pixel match. Rather than force-crop the new footage to fit the old shape (would have cut into the gesture pose), the CSS was updated to match the new video's real dimensions instead — `object-fit: cover` then has nothing left to crop or distort.
- Audio track stripped at encode time (the slot is meant to be a silent loop) on top of the existing `muted` attribute already enforced both declaratively and in JS for Safari/iOS reliability — belt and suspenders, not redundant paranoia, since Safari/iOS autoplay policy is genuinely picky about exactly when `muted` gets set.

## Standing conventions worth knowing

- **Agent name/photo/video is centralized** in `persona.ts` (frontend) / `persona.py` (backend) — the name has changed more than once this project (an early placeholder → Rachel → the current **Fiona**). Always check these files directly rather than trusting a name from memory, a doc, or task history.
- **Only one persona (Fiona) is actually wired to a real agent.** The pre-join picker (`personas.ts`) shows 7 other locked "Coming soon" placeholders — no photos exist for them yet, deferred pending a higher-res free source. Don't assume picking one of them does anything.
- **Visitor identity crosses a real process boundary.** `server.py` (REST, :8787) and `bot.py` (voice, :7860) are separate processes with separate in-memory session stores — anything that needs to reach the voice pipeline (a visitor's name, a session flag) has to travel via the WebSocket URL query param, the same way `visitorId` already does, not just the REST call. This has caused a real bug before; don't reintroduce the assumption that one REST call is enough.
- **Copy on the landing page has to be literally accurate**, not just aspirational — see the "builds it live" catch above.
- **When a feature gets cut, grep for anything that still references or advertises it** before calling the removal done — this bit the dashboard once this stretch.

## Open items — where to pick up

Nothing frontend-specific is currently mid-flight as of this handover. The active open items are backend-side (adaptive stall-backstop pacing, an MLR-queue overclaim bug) — see `backend/handover/handover23Augustupdatebackend.md`. If either of those end up needing frontend changes (e.g. a visible "still listening" affordance if pacing becomes adaptive, or fixing the MLR queue to actually support opening a real submission), they'll land here next.
