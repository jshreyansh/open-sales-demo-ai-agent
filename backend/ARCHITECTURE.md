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
    voice/
      bot.py                 # Pipecat entrypoint — separate process/port
      agent_processor.py       # bridges Pipecat's pipeline to run_turn()
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
- **Voice** (`voice/bot.py`, `voice/agent_processor.py`): Pipecat pipeline —
  Groq (STT) → `AgentRuntimeProcessor` → Cartesia (TTS). Runs as its **own
  process on its own port** (Pipecat's dev runner defaults to :7860), not
  merged into `server.py` — Pipecat's runner owns its own FastAPI/uvicorn
  server, so this stays a separate service by design.
  `AgentRuntimeProcessor` doesn't reimplement anything: it calls the exact
  same `run_turn()` the text chat calls (same registry, same session store,
  same Claude tool-use + keyword fallback), so voice and text share one
  brain. When a turn produces a UI action, the voice process reports it to
  the REST API via `POST /internal/voice-action` (main process, :8787),
  which the frontend polls via `GET /api/voice-action/{visitor_id}` — kept
  as a simple polling handoff rather than reaching into Pipecat's own
  client-message wire protocol, so this doesn't get coupled to Pipecat
  internals that change across versions.
  Run it with `python -m src.voice.bot` — prints a URL (default
  `http://localhost:7860/client/`) serving Pipecat's own prebuilt WebRTC
  test page, useful for verifying the voice loop before wiring it into the
  actual product frontend.

## Not yet built

- **Flow Engine**: multi-step scripted demo journeys with branch points —
  today the agent picks one action per message, no sense of a longer arc.
- **Knowledge Base / RAG**: off-script questions (pricing, compliance, etc.)
  fall back to a generic reply instead of being grounded in real product docs.
- **Voice UI Kit in the actual frontend**: today voice only works via
  Pipecat's own standalone test page. Embedding `@pipecat-ai/voice-ui-kit`
  (ConnectButton, VoiceVisualizer, UserAudioControl) into the real React
  frontend, and passing the real `visitor_id` through the `/start` request's
  `body`, is the next step once the standalone loop is confirmed working.
- **Ack/error/fallback protocol** for UI actions (retry → narrate-only → log)
  per root `globalplan.md` §2.4 — a failed action currently just queues
  indefinitely rather than degrading gracefully.
