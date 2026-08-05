# Vision — backend

One-liner: **the brain, not just an LLM call** — an orchestrator that decides
what to say and what to do next, the way a live sales rep reads the room and
adapts, not a script that plays to completion.

## Why this exists

Anyone can wire a chatbot to an LLM. The hard part — and the actual product —
is an agent that stays grounded in real product facts, follows a reliable
script but can be interrupted and come back to it, and never leaves the
frontend hanging on a broken action. That orchestration logic lives here.

## Principles to hold onto (don't relitigate these later)

- **Stateless runtime.** All state — session, profile, transcript — lives in
  the Context Store keyed by `visitor_id`, not in process memory. This is what
  lets this scale to many concurrent demos later by just adding instances
  (root `globalplan.md` §7).
- **Flows are data, not hardcoded prompts.** Once past Phase 0, demo journeys
  are scripted config the Flow Engine reads, not the agent improvising every
  time (root `globalplan.md` §3, §6).
- **Never invent facts.** Anything outside the current flow gets answered from
  the Knowledge Base (RAG), not from the model's own guess.
- **Every action to the frontend has a fallback.** Retry → narrate instead of
  clicking → log silently. A failed click must never surface as a broken demo
  (root `globalplan.md` §2.4).
- **Identity is the same `visitor_id` the frontend generates.** No separate
  backend auth model — see `../frontend/VISION.md`.

## Not this repo's job

Rendering UI, owning component state, or deciding pixel-level presentation.
That's all `../frontend`. This repo decides and instructs; it doesn't display
anything itself.
