# Architecture — backend (Phase 0 → Phase 1 only)

This covers **setup through Phase 1**, not the full end-state system. Full
system architecture and later-phase design lives in root
[`globalplan.md`](../globalplan.md) §4–§5. Extend this file as later phases
actually land — don't design them here in advance.

## Stack (default, revisit if it's wrong)

- Node.js + TypeScript (Fastify or Express) — one language across the whole
  monorepo, minimal tooling, matches `../frontend`. No agent framework
  (LangGraph etc.) yet — Phase 0 doesn't need one.

## Phase 0 — prove the core loop

Goal: one hardcoded flow, agent narrates + drives the UI reliably, no
abstractions yet.

- One endpoint that takes a chat message + `visitor_id`, calls an LLM, and
  returns both a text reply and a hardcoded next UI action for `../frontend`
  to execute directly (no registry lookup yet — the one flow's steps are
  known in advance).
- `visitor_id` → session state: a simple key-value store is fine to start
  (in-memory map), but keep it behind a small interface (`get/set` by
  `visitor_id`) so swapping in a real store (Redis-style for session,
  Postgres-style for profile — root `globalplan.md` §7) is a one-file change,
  not a rewrite.
- No Flow Engine, no Knowledge Base/RAG, no voice yet — the one flow is
  hardcoded in code.

Suggested shape:

```
backend/
  src/
    server.ts          # one endpoint, Phase 0
    context/
      store.ts           # visitor_id -> state, swappable backend
    agent/
      runtime.ts          # calls the LLM, returns reply + next action
```

## Phase 1 — generalize driving the UI

- **Flow Engine v1**: convert the Phase 0 flow into data (steps + branch
  points), each step carrying pause/resume state (so Phase 3 interrupt
  handling plugs in later instead of being retrofitted).
- **Registry client**: read `../frontend`'s UI Registry (pages → components →
  actions) instead of hardcoding what exists. Contract formalized in a
  root-level `REGISTRY.md` once both sides agree on the shape.
- Send actions with the ack/error/fallback protocol and handle `failed:reason`
  per the retry → narrate → log tiers.

## Explicitly out of scope for now

Voice (STT/TTS), Knowledge Base/RAG, Dummy Backend beyond whatever the one
Phase 0 flow needs, profile-scoped memory, personalization. See root
`globalplan.md` §5 for when these land.
