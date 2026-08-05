# Vision — frontend

One-liner: **the body the agent controls** — not a chatbot widget bolted onto a
demo site, but a product replica that an AI agent can drive live, the way a
human sales rep drives their own screen.

## Why this exists

A prospect should forget they're watching an AI. That only works if the UI
reacts instantly and correctly to what the agent decides — no lag, no broken
selectors, no "the demo glitched." The frontend's whole job is to make that
reliable.

## Principles to hold onto (don't relitigate these later)

- **No login, no real auth.** Identity is an anonymous `visitor_id` generated
  once and stored in `localStorage`. Refresh persists it; a cleared browser or
  a new device is correctly a new session, not a bug.
- **Every component exposes actions, never DOM.** The agent calls
  `highlight("create-video")`, not "click at x=391,y=123." If a component
  can't be driven by a named action, it isn't demo-ready.
- **Components self-register.** A page/component that exists but hasn't
  registered itself is invisible to the agent — that's intentional. It forces
  the registry to always be an accurate map (see root `globalplan.md` §2.3).
- **Looks real, is safe.** Fake data, fake backend, no real customer data or
  real destructive actions ever — see `../backend`'s Dummy Backend.
- **Every action acks or fails explicitly.** Silent failure is not allowed —
  the agent needs to know if a click didn't land so it can fall back to
  narrating instead (root `globalplan.md` §2.4).

## Not this repo's job

Deciding what to say, what flow to run, retrieving knowledge, or holding
conversation state. That's all `../backend`. This repo reports state and
executes actions — it doesn't decide anything.
