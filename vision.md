# Vision — open-sales-demo-ai-agent (SwishX)

This is the project-level vision. It supersedes nothing — `backend/VISION.md` and `frontend/VISION.md` (written 2026-08-05, at inception) are still correct on the *why* for each half of the system and are left untouched, per standing instruction. This file is where the **whole-project** picture lives, and where it gets a dated, versioned update each time a real milestone closes — new sections get appended below, nothing here gets overwritten.

---

## v0.1 — Original vision (2026-08-05, project inception)

**One-liner:** a "Presentation Operating System" — an AI agent (voice + text) drives a pixel-accurate replica of SwishX's real product, live, on a sales call, the way a human rep drives their own screen. Not a chatbot bolted onto a marketing site; the demo *is* the product experience.

**Why this exists:** anyone can wire a chatbot to an LLM. The hard part — and the actual product — is an agent that stays grounded in real product facts, follows a reliable script but can be interrupted and come back to it, never leaves the frontend hanging on a broken action, and reacts to the prospect's actual words instead of playing a script to completion.

**The two-repo split, and why it's a hard boundary:**
- **Backend is the brain.** It decides what to say and what to do next — the orchestrator, not just an LLM call. It never renders anything itself.
- **Frontend is the body the agent controls.** It reacts instantly and correctly to what the agent decides, exposes every driveable thing as a named action (never raw DOM), and never decides anything on its own — it reports state and executes.

**Principles stated at inception, still true:**
- Stateless runtime — session state lives in a store keyed by `visitor_id`, not in process memory, so it can scale by adding instances later.
- Flows are meant to become data, not hardcoded prompts, once past the earliest phase.
- Never invent facts — anything outside what the agent actually knows should be grounded in real product knowledge, not guessed.
- Every action to the frontend needs a fallback path (retry → narrate instead of clicking → log silently) — a failed click must never surface as a visibly broken demo.
- No login, no real auth — identity is an anonymous `visitor_id`; a cleared browser or new device is correctly a new session, not a bug.
- Looks real, is safe — fake data, fake backend, never real customer data or real destructive actions.

The deeper technical reasoning behind these — including a documented critique of an earlier, more over-engineered original plan — lives in root `globalplan.md`, written the same day. That document is the detailed technical/product plan this vision summarizes; it's still worth reading for the *why* behind the phasing, not just the *what*.

---

## v0.2 — Milestone 1: the voice product is real, deployed, and battle-tested

**Date:** 2026-08-23
**Time:** 00:41 UTC
**Added by:** Claude Code
**Status:** everything below is shipped, committed, and live in production — not a roadmap.

### What's true now that wasn't true at inception

The v0.1 vision was written the same day as an empty project scaffold. Eighteen days and 96 commits later, the core thesis has held — the agent really does drive a live replica of the real product, and the two-repo split really has stayed a hard boundary — but the system underneath it is substantially more real:

- **Voice is not a bolt-on anymore.** It's the primary interaction mode, running as its own Pipecat pipeline (own process, own port) sharing one brain (`run_turn`/`run_turn_stream`) with the text-chat path, deployed over WebSocket (not WebRTC — the production box's network topology forced that decision early and it's stuck) to a real production box behind an AWS ALB, with auto-deploy on every push to `main`.
- **The agent has a name, a face, and a persona now — Fiona** — not a generic assistant. Only one persona is real; several more exist as visible-but-locked placeholders, an intentional signal that this is a multi-persona product in the making, not a single-bot toy.
- **A scripted platform walkthrough exists** — a real guided tour through the product, with its own state machine, pause/resume, and (after real trial and error) a hard architectural rule: walkthrough state comes only from explicit user intent, never inferred from the assistant's own words. This rule exists because inferring it the other way once caused the agent to silently restart a whole tour after a prospect had already said goodbye — found on a real call, fixed as a principle, not a patch.
- **A qualification system exists**, steering every real call toward five specific pieces of information a real client (Dushyant Sapre) required the agent to actively gather, persisted per-call with an AI-generated call summary available to an admin dashboard.
- **Turn-taking — when to answer, how long to wait, what to do when someone talks over the agent or vice versa — has become the single most invested-in problem in the project**, and is now handled by a layered system: acoustic VAD, a semantic completion classifier (Smart Turn), a confidence-driven adaptive wait window (researched against how OpenAI's Realtime API and LiveKit's production turn-detector actually work, not guessed), a merge-aware buffer system so an interruption and a still-forming thought can't answer out of order, and — the newest layer — a signal that lets a reply explicitly tie back to what the agent itself just said instead of reading as disconnected. Every one of these was built in direct response to a real test call, root-caused against real logs, and re-verified against a live call before being called done.
- **The product itself has been demoed and pressure-tested extensively**, including calls where the founder used the agent as a live brainstorming partner for its own roadmap — treating the agent not just as a thing being tested, but as a participant in deciding what it should become next.

### What hasn't changed

The core architectural bet from v0.1 — a brain/body split, a registry the agent can't hallucinate outside of, real product facts instead of invented ones, and a demo that has to survive real live-call pressure rather than just a script — has held for the whole 18 days and is not up for relitigation. Everything in v0.2 is an evolution of that bet, not a departure from it.

### Where the fuller history lives

The day-by-day, decision-by-decision account of how the project got from v0.1 to v0.2 — every real pivot, every bug, every architectural lesson — lives in `handover/handover23Augustupdate.md`, written the same day as this update. That document is the detailed chronicle; this one is the durable summary.
