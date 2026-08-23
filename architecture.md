# Architecture — open-sales-demo-ai-agent (SwishX)

Project-level, high-level architecture — how the whole system fits together and why it's shaped this way. Not an engineering reference: for backend internals see `backend/ARCHITECTURE.md` (also useful for the "not yet built" list, though it's stale as of this writing — see v0.2 below) and `backend/handover/handover23Augustupdatebackend.md` for current detail; for frontend, `frontend/ARCHITECTURE.md` and `frontend/handover/handover23Augustupdatefrontend.md`. Root `globalplan.md` has the original deep technical/product reasoning from inception. This file, like `vision.md`, gets appended to at each real milestone — nothing here gets overwritten.

---

## v0.1 — Original architecture (2026-08-05, project inception)

**The shape:** two independent services, a hard contract between them, no shared code.

```
frontend (React + Vite + TypeScript)
   — renders a pixel-accurate replica of the real product
   — every driveable component self-registers into a UI Registry
   — reports state, executes named actions, never decides anything

        ↕  REST (/chat, /api/*)  +  WebSocket (voice)

backend (Python + FastAPI)
   — the Agent Runtime: one LLM tool-use call per turn, narrates + picks
     an action, validated against a UI Registry so it can never
     hallucinate a page/component that doesn't exist
   — a Context Store keyed by visitor_id (session-scoped, no auth)
   — a separate voice process (Pipecat) sharing the same Agent Runtime
     brain as the text-chat path
```

**Decisions made at inception, and why:**
- **Backend is Python, not the original Node/TypeScript scaffold** — decided same-day, specifically *ahead of* adding voice, because Pipecat (the voice/turn-taking framework) is Python-core; running the Agent Runtime in the same language avoids a cross-language bridge service. The Anthropic SDK's TS and Python shapes are close enough that the agent logic ported over almost 1:1.
- **Two-repo, no shared code, on purpose** — the registry contract between them is the only interface, kept honest by a script that diffs frontend's live registrations against backend's manifest.
- **A UI Registry, not browser automation.** The agent calls a named action (`highlight("create-video")`), never simulates a click at a coordinate — a deliberate rejection of a "just drive a real browser" approach considered and discussed at inception (documented in `globalplan.md` §2.5).

---

## v0.2 — Milestone 1: what the system actually looks like now

**Date:** 2026-08-23 · **Time:** 00:41 UTC · **Added by:** Claude Code

The two-service shape from v0.1 is unchanged and has held for the whole project. What's different is what runs inside it, and how it's deployed.

### The full picture

```
                    ┌─────────────────────────────────┐
                    │   frontend (React/Vite/TS)       │
                    │   — pixel-accurate SwishX replica│
                    │   — Meeting Mode (Presentation   │
                    │     Shell) or Product Mode        │
                    │   — every action self-registers   │
                    │     into uiRegistry.ts             │
                    └─────────────┬─────────────────────┘
                                  │
              REST (:8787)        │        WebSocket voice (:7860)
                    │             │             │
        ┌───────────▼──────┐      │      ┌──────▼─────────────┐
        │  server.py         │◄────┴─────►│  bot.py               │
        │  (FastAPI, REST)   │  visitor_id │  (Pipecat pipeline)   │
        │  separate process  │  travels via│  separate process     │
        └───────────┬────────┘  URL params └──────┬────────────────┘
                    │  (NOT shared memory —         │
                    │   this has bitten the          │
                    │   project before)               │
                    └──────────────┬───────────────────┘
                                   │
                    ┌──────────────▼───────────────────┐
                    │  Agent Runtime (agent/runtime.py) │
                    │  run_turn() / run_turn_stream()   │
                    │  — one brain, both processes call │
                    │    into it identically            │
                    │  — UI Registry-validated action    │
                    │    selection                        │
                    │  — walkthrough state machine         │
                    │  — qualification tracking             │
                    └──────────────┬─────────────────────┘
                                   │
                    ┌──────────────▼─────────────────────┐
                    │  voice/agent_processor.py            │
                    │  the turn-taking layer, voice-only:  │
                    │  VAD → Smart Turn (semantic          │
                    │  completeness) → confidence-driven    │
                    │  adaptive settle window → merge-aware │
                    │  interruption/fragment buffers →      │
                    │  continuation-aware reply generation  │
                    └────────────────────────────────────────┘
```

### Deployment

Production runs on a single EC2 box behind an AWS ALB, in a private subnet with no direct inbound path except what the ALB forwards. Two consequences that shaped real architectural decisions:

- **Voice transport is WebSocket, not WebRTC.** WebRTC's raw UDP media cannot cross the ALB at all (confirmed via a live test, not assumed) — this was discovered and fixed on day 4 of the project, described in its own commit as "a swap at the two transport endpoints, not a pipeline rewrite," since the VAD/STT/agent/TTS pipeline in between operates on the same Frame objects regardless of transport.
- **Deploys run via a self-hosted GitHub Actions runner installed directly on the box**, not a GitHub-hosted runner — required because a GitHub-hosted runner has no network route into the private subnet. Push to `main` deploys straight to production, no approval gate — a deliberate choice, which means `main` on this repo is a live branch, not a staging branch.

### The turn-taking layer, specifically

This deserves its own callout because it's where the majority of engineering investment has gone since inception, and it's the part most likely to keep evolving. It is not one mechanism — it's several layered, independently-reasoned-about signals working together:

1. **Acoustic VAD** (Silero) — is someone making sound.
2. **Smart Turn** (semantic completeness classifier) — does this sound like a finished thought, with a continuous confidence score underneath the binary verdict.
3. **A confidence-driven adaptive settle window** — how long to wait before answering, scaled by that confidence rather than a flat timer, with a fragmentation-aware floor for speakers who've already shown they ramble.
4. **Merge-aware interruption/fragment buffers** — content that interrupts the agent's own reply, and content that's still forming as an incomplete thought, are two separate buffers that used to drain independently (a real bug, since fixed) and now check each other before releasing.
5. **A continuation-awareness signal** — whether the current input likely continues something the agent just said, independent of whether it literally overlapped the agent's speech, so the reply can tie back explicitly instead of reading as disconnected.

Each layer was added because a real test call surfaced a real failure the prior layers didn't cover — this is not a designed-up-front system, it's an accreted one, built in response to evidence each time. That pattern is likely to continue; treat it as the expected way this part of the system grows, not a sign of instability.

### What v0.1's "not yet built" list looked like at inception, resolved

`backend/ARCHITECTURE.md` (written day one) listed a Flow Engine, a Knowledge Base/RAG layer, an embedded voice UI kit, and an action ack/error/fallback protocol as not-yet-built. As of this milestone: the scripted walkthrough system *is* the flow engine that emerged (config-driven scripted journeys with branch/pause/resume, not the more general system originally imagined, but serving the same need); a `knowledge/*.md` directory serves grounded non-interactive facts (pricing, security posture, integrations) without inventing anything; voice is fully embedded in the real frontend, not just Pipecat's standalone test page; and actions do report back success/failure rather than queuing indefinitely. None of this was a rewrite of the original plan — each piece arrived as the feature that needed it got built.

### Where the fuller history and reasoning lives

`handover/handover23Augustupdate.md` has the day-by-day account of how each of these pieces actually got built, including the real pivots, the bugs that forced them, and the architectural lessons that came out of each one. This file is the durable summary of *what's true now*; that one is the chronicle of *how it got that way*.
