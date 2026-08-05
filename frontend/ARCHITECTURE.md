# Architecture — frontend (Phase 0 → Phase 1 only)

This covers **setup through Phase 1**, not the full end-state system. Full
system architecture and later-phase design lives in root
[`globalplan.md`](../globalplan.md) §4–§5. Extend this file as later phases
actually land — don't design them here in advance.

## Stack (default, revisit if it's wrong)

- React + Vite + TypeScript. No SSR framework needed — this is an internal
  demo tool, not a public site; Vite keeps the loop fast.
- Plain CSS/whatever styling is fastest to move in — not a design system
  concern yet.

## Phase 0 — prove the core loop

Goal: one hardcoded flow, agent narrates + drives the UI reliably, no
abstractions yet.

- One page, 3–4 components with **hand-written** action methods
  (`highlight()`, `click()`, `focus()`, `open()`) — not registry-driven yet,
  just called directly.
- `visitor_id`: generate a UUID on first load if `localStorage` doesn't have
  one; persist it; send it on every request to `../backend`.
- Text chat only. No voice, no Presentation Shell modes, no registry.

Suggested shape:

```
frontend/
  src/
    pages/           # the one demo page for now
    components/       # 3-4 hardcoded, hand-written actions
    lib/
      session.ts       # visitor_id generation + localStorage
      api.ts            # talks to ../backend
```

## Phase 1 — generalize driving the UI

- **UI Registry**: each component self-registers on mount — id, description,
  available actions — into a single hierarchical registry
  (`pages → components → actions`). The contract this registers against will
  be formalized in a root-level `REGISTRY.md` once backend and frontend agree
  on the shape; don't invent it unilaterally here.
- **UI Controller**: the receiving side that takes a command from the backend
  (e.g. `{ component: "create-video", action: "click" }`) and invokes the
  matching registered action, then reports back `ack | done | failed:reason`.
- Flow steps gain explicit pause/resume state on the frontend side too (so
  Phase 3 interrupt handling isn't a rewrite) — but no voice/interrupt UX yet.

## Explicitly out of scope for now

Voice, Presentation Shell (Meeting Mode / multi-mode), personalization,
multi-flow branching, profile-scoped memory. See root `globalplan.md` §5 for
when these land.
