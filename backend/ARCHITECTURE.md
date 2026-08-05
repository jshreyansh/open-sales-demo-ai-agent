# Architecture — backend

Full system architecture and phase plan lives in root
[`globalplan.md`](../globalplan.md) §4–§5. This file tracks what's actually
built here and the near-term shape.

## Stack

Python + FastAPI + Uvicorn. Originally scaffolded in Node/TypeScript for
Phase 0–1; migrated to Python once voice entered the picture — Pipecat (the
STT/TTS/turn-taking framework, see root `globalplan.md`) is Python-core, and
running the Agent Runtime in the same language/process avoids a second
service just to bridge them. The Anthropic Python SDK mirrors the TS SDK
closely, so the agent logic ported over almost 1:1.

## Current shape

```
backend/
  src/
    server.py           # FastAPI app — /chat, /health, /api/dashboard,
                         # /api/analytics/overview, /api/brand-kit
    context/
      store.py            # visitor_id -> SessionState (history, current_page)
    agent/
      registry.py           # UI_REGISTRY manifest: pages -> components -> actions
      runtime.py             # run_turn(): Claude tool-use (registry-constrained)
                              # with a keyword-matcher fallback when no API key
    data/
      dashboard.py, analytics.py, brand_kit.py   # dummy backend data
```

## What's built (past Phase 0/1)

- **UI Registry** (`agent/registry.py`): the single source of truth for what
  the agent can point at and do. Extend this file whenever `../frontend`
  registers a new actionable component (see `../frontend/src/lib/uiRegistry.ts`).
- **Agent Runtime** (`agent/runtime.py`): one Claude tool-use call both
  narrates and picks an action, validated against the registry so it can't
  hallucinate a page/component that doesn't exist. Falls back to a
  dependency-free keyword matcher when no `ANTHROPIC_API_KEY` is set.
- **Context Store** (`context/store.py`): session-scoped only so far (history,
  current page) — no profile/cross-visit memory yet (root `globalplan.md` §6
  Phase 4).
- **Dummy Backend** (`data/*.py`): static demo data for Dashboard, Analytics,
  Brand Kit, served as plain JSON.

## Not yet built

- **Flow Engine**: multi-step scripted demo journeys with branch points —
  today the agent picks one action per message, no sense of a longer arc.
- **Knowledge Base / RAG**: off-script questions (pricing, compliance, etc.)
  fall back to a generic reply instead of being grounded in real product docs.
- **Voice** (Pipecat): STT/TTS/turn-taking layer in front of `run_turn()`.
  `run_turn(message, session) -> {reply, action?}` is already the exact seam
  a voice layer needs — it doesn't require changing the Agent Runtime, just
  wrapping it.
- **Ack/error/fallback protocol** for UI actions (retry → narrate-only → log)
  per root `globalplan.md` §2.4 — a failed action currently just queues
  indefinitely rather than degrading gracefully.
