# AI Sales Demo — Global Plan

## 1. The Concept

Not a chatbot bolted onto a demo site. A **Presentation OS**: an agent that drives a
fake-but-real-looking replica of the product during a sales call, using semantic
component APIs instead of DOM automation, backed by a knowledge base, reusable
demo flows, and registries that describe what pages/components exist.

Core insight worth keeping: **decouple the agent from the DOM**. Instead of the
LLM guessing coordinates or CSS selectors, components expose named actions
(`highlight()`, `click()`, `open()`) and the agent calls those. This is the same
pattern as tool-calling schemas / accessibility trees — it's the right call, not
a fallacy.

---

## 2. Logical Fallacies & Inconsistencies in the Original Plan

### 2.1 Contradiction: "no authentication" vs. persistent Agent Memory
Section 1 (React Product Replica) explicitly says **no authentication**. Section 10
(Agent Memory) then describes memory that persists facts about a specific person
across time ("Already showed Avatar," "User is interested in compliance") — that
requires a stable identity, which requires *some* identifier (email, CRM contact
ID). You can't have durable cross-session memory of "this person" with zero identity
model. Either memory is session-only (fine, and needs no identity), or you add a
lightweight identifier (rep types in prospect email/company at meeting start) —
but the doc doesn't reconcile these two claims.

**Fix:** pick one. Recommend: memory defaults to session-scoped; persistent
profile memory is opt-in and keyed off whatever the sales rep enters (no real auth
needed, just a join key).

> **Resolved:** anonymous **device/visitor ID** — a UUID generated on first load
> and stored in `localStorage`. Refresh → same ID → session resumes. Clear
> storage or open on a different device → new ID → new session, by design. This
> is the standard "anonymous ID" pattern used by Intercom, Drift, Segment,
> Amplitude, etc. No login, no real auth, and it fully resolves the contradiction
> — the identifier for memory is the visitor ID, not a login. See §6.

### 2.2 False subdivision: Session Manager vs. Agent Memory
The two sections are pitched as separate subsystems, but their example payloads
overlap almost entirely — "questions asked" vs. "user asked," "current feature" vs.
"already showed Avatar / skipped Analytics." As written this reads like the same
state store split in two for no functional reason.

**Fix:** one **Context Store** with two scopes — `session` (this meeting, always
on, cleared after) and `profile` (cross-meeting, opt-in, keyed by the identifier
from 2.1). Not two subsystems.

### 2.3 False subdivision: Product Registry vs. Component Registry
Same issue. A page registry that lists "components: [create-video, brand-kit]"
and a component registry that lists actions per component is just a two-level
tree. Splitting it into two registries the agent has to query separately adds a
join step for no benefit.

**Fix:** one **UI Registry**, hierarchical: `pages → components → actions`.

> **Resolved:** confirmed — single hierarchical registry. Every page and every
> component must self-register (ID, description, available actions) so the
> agent always has a complete, accurate map of what it can click/highlight/open,
> instead of inferring structure from prompts or screenshots.

### 2.4 Overclaimed causal leap: "no HTML manipulation ⇒ incredibly reliable"
Semantic action APIs remove *one* failure mode (broken selectors), but reliability
also depends on things this section never mentions: race conditions (agent calls
`click()` while a modal is still animating in), latency between agent decision and
UI state, and what happens when an action fails. "Incredibly reliable" is a
conclusion the architecture doesn't yet earn.

**Fix:** every registry action needs a return value / promise the controller
awaits (`ack`, `done`, `failed:reason`), and the runtime needs a retry/backoff
policy. Treat this as a protocol, not a guarantee.

> **Resolved — robustness tiers:** on an action failure, the runtime should
> degrade gracefully rather than break the call: (1) retry once, (2) if it still
> fails, fall back to narrating verbally instead of clicking ("let me tell you
> about this instead of showing it"), (3) log the failure to the session for
> post-call review, never surface a raw error to the prospect. Different demos
> can use different fallback chains, but every action needs one.

### 2.5 False dilemma: "Not Playwright. Not browser automation. Build your own."
Presents "custom command protocol" and "browser automation" as the only two
options. Nobody proposed driving a *real* browser with Playwright for a product
you already own the source of — the actual alternative being dismissed is DOM
selectors / data-testid automation, not Playwright specifically. Doesn't change
the conclusion (custom command API is correct here) but the framing is a straw man.

### 2.6 Minimization: "Voice layer — nothing complicated"
STT → agent → TTS is simple in isolation. It's not simple when the same agent is
*also* driving UI actions and needs to handle barge-in (the doc's own Agent
Memory example mentions "interrupted twice"). Turn-taking, interrupting a
TTS-in-progress, and pausing/resuming a UI action mid-flow because the user
spoke over it, is one of the harder integration points in this whole system.
Calling it "nothing complicated" understates real latency/UX work.

> **Resolved — this is core, not a nice-to-have:** the target experience is a
> real-time, interruptible agent that talks, shows, and reacts like an actual
> sales rep on a call — not a script that plays to completion. That means
> barge-in (user can interrupt agent speech or an in-progress UI action at any
> time), graceful pause/resume of the current flow step, and low enough latency
> that turn-taking feels natural. This raises the priority of interrupt handling
> — it should be designed into the Flow Engine's step model from Phase 1 (steps
> need pause/resume state), not bolted on when voice arrives in Phase 3.

### 2.7 Premature generalization (YAGNI): 12 subsystems justified by a hypothetical
The "Why this becomes extensible" section justifies building all 12 pieces now by
imagining a redesign *six months from now*. That's optimizing for a future that's
conditional on the product surviving initial validation. Nothing in the doc
proposes a sequence — all subsystems are presented as day-one, equal-priority
work. For a demo tool, the thing to validate first is "does an AI-driven demo
actually work well enough to show a prospect," not the registry abstraction layer.

**Fix:** phase it (see §4). Registries and flow engine are still the right
long-term shape — build them, but build the smallest version that unblocks a
working demo first, then generalize once the concept is proven.

---

## 3. What's Right — Keep As-Is

- **Semantic component APIs instead of DOM automation** — correct, just needs a
  proper ack/error protocol (2.4).
- **Dummy backend, fake data, no real auth for the product replica** — correct,
  keeps the demo safe and fast to reset.
- **Reusable Flow Engine instead of letting the agent improvise every demo** —
  correct; scripted flows with branch points are far more reliable than
  freeform agent planning for a sales-critical moment.
- **Knowledge base / RAG for anything outside the scripted flow** — correct
  fallback for off-script questions.
- **Two presentation modes (Meeting / Product)** sharing one backend — correct;
  avoids building two products.
- **Agent Runtime as an explicit orchestrator (LangGraph-style), not a bare LLM
  call** — correct given the multi-tool, multi-step nature of a driven demo.

---

## 4. Simplified Architecture

```text
                    Presentation Shell
              (Meeting Mode / Product Mode)
                         │
        ┌────────────────┼────────────────┐
        │                │                 │
  React Product     Agent Runtime      Context Store
    Replica          (orchestrator)   (session + profile scope)
        │                │                 │
        └────────────────┼─────────────────┘
                         │
      ┌──────────────────┼───────────────────┐
      │                  │                   │
  UI Registry       Flow Engine        Knowledge Base
 (pages→components   (scripted demo       (RAG over
      →actions)        journeys)         docs/decks)
      │                  │                   │
      └──────────────────┴───────────────────┘
                         │
                  UI Controller (MCP-style)
                         │
                React Component Action APIs
                         │
                   Dummy Backend APIs
                         │
                    Voice Layer (STT/TTS,
                   with interrupt handling)
```

Changes from the original: Session Manager + Agent Memory → **Context Store**
(2.2). Product Registry + Component Registry → **UI Registry** (2.3). Everything
else kept.

**Context Store identity model:** on first load, the client generates a UUID
(`visitor_id`) and stores it in `localStorage`. Every request to the Agent
Runtime carries it.
- `session` scope: keyed by `visitor_id`, holds current page/flow/step,
  transcript, buttons clicked — cleared or archived when the call ends.
- `profile` scope: also keyed by the same `visitor_id`, persists across return
  visits on the same browser/device (what's been shown, stated interests). A
  cleared `localStorage` or a different device is a new `visitor_id` — that's
  the correct behavior, not a bug, since there's no login to reconcile identity
  across devices.

---

## 5. Phased Build Plan

The goal is an MVP that validates the concept fast, built on foundations that
don't need to be thrown away when this scales to thousands of concurrent demos
(§7) — small in feature scope, not small in the sense of "storage layer we'll
rip out later."

**Phase 0 — Prove the core loop (1 hardcoded flow, minimal infra)**
- One React page, 3–4 components with hand-written action methods.
- `visitor_id` generation + `localStorage` persistence wired up from day one —
  trivial to build, expensive to retrofit once sessions matter elsewhere.
- Agent hardcoded to run one scripted flow end to end via text chat only.
- No registry, no knowledge base, no voice yet. Goal: prove "agent narrates +
  drives UI reliably" is viable before investing in abstractions.

**Phase 1 — Generalize driving the UI**
- Build the real UI Registry + UI Controller with the ack/error/fallback
  protocol (2.4).
- Convert Phase 0's flow into data (Flow Engine v1). Steps carry explicit
  pause/resume state from the start, even before voice exists — this is the
  hook interrupt handling will plug into in Phase 3, so it isn't retrofitted.
- Still text chat only.

**Phase 2 — Make it answer, not just narrate**
- Knowledge Base + RAG for off-script questions.
- Context Store `session` scope live (keyed by `visitor_id`).
- 2–3 flows covering the main product surfaces.

**Phase 3 — Make it feel like a live rep**
- Presentation Shell: Meeting Mode + Product Mode.
- Voice layer (STT/TTS) with barge-in: user can interrupt agent speech or an
  in-progress UI action at any point; the flow pauses on its already-built
  resume state (Phase 1) and picks back up, or abandons the step if the
  conversation moved on.

**Phase 4 — Make it remember**
- Context Store `profile` scope: same `visitor_id`, persisted across return
  visits (what's been shown, stated interests, skip repeats).
- Personalization + flow authoring tooling as scale demands (§6).

---

## 6. Decisions & Defaults

**Resolved:**
- **Identity** — anonymous `visitor_id` in `localStorage`, no login. See §2.1, §4.
- **Interaction model** — real-time, interruptible, feels like a live sales rep
  on a call, not a script that plays to completion. See §2.6.
- **Registry** — one hierarchical UI Registry (`pages → components → actions`).
  See §2.3.
- **Action robustness** — tiered fallback: retry → narrate instead of click →
  log silently. See §2.4.
- **Build philosophy** — MVP first to validate the concept, but the storage and
  runtime choices are made to scale from day one rather than as a rewrite
  later. See §7.

**Left as engineering defaults (flagged, not asked, per your "figure out the
best way" on these) — revisit if they turn out wrong:**

- **Personalization** — the dummy backend accepts a `prospect` object (company
  name, logo URL, industry) set at demo start, either by the rep or a URL
  param. Components that render fake data (dashboards, sample docs, sample
  campaigns) interpolate it. Simple string/asset substitution, no new
  subsystem — defer anything smarter until there's a reason to build it.
- **Flow authoring** — flows are version-controlled YAML/JSON files read by the
  Flow Engine, not a custom builder UI. A visual builder is real work and only
  pays off once flow volume/authorship (non-engineers writing flows) justifies
  it — likely a Phase 4+ problem, once you're actually running enough demos to
  feel the pain of hand-editing config.

---

## 7. Building the MVP So It Scales to Thousands of Demos

"MVP" here means smallest *feature* set, not smallest *architecture* — the
storage and runtime choices below are cheap to do right from Phase 0 and
expensive to redo once real usage exists on top of them.

- **Context Store backing store**: use a real store from day one, not an
  in-memory dict — `session` scope in something fast/ephemeral (Redis-style),
  `profile` scope in a real DB (Postgres-style). In-memory state doesn't
  survive a restart or a second server instance, and "thousands of demos" means
  multiple concurrent server instances eventually.
- **Agent Runtime is stateless**: it reads/writes all state through the Context
  Store keyed by `visitor_id`, never holds state in process memory. This is
  what makes "add more instances" the actual scaling strategy later, instead
  of a rewrite.
- **UI Registry and Flow definitions are static config**: cheap to serve, cache
  aggressively, version them like code (git). Thousands of concurrent demos
  reading the same registry is a non-problem if it's just cached JSON/YAML.
- **Everything else — voice, personalization, a flow builder UI — stays
  deferred**: those are features, not foundations. Adding them later doesn't
  require touching the identity model, the storage layer, or the runtime
  shape, which is the whole point of getting §4 and this section right early.
