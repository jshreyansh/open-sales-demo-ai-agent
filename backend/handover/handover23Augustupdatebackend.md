# Backend Handover — 2026-08-23

**For:** whoever (human or agent) picks up backend work on this next.
**Covers:** the last ~4 days, 2026-08-20 through 2026-08-23 (37 commits) — the period where voice turn-taking correctness became the dominant focus.
**Written by:** Claude Code, closing out this stretch of work.

If you haven't read `backend/VISION.md` and `backend/ARCHITECTURE.md` yet, read those first — they're the Aug 5 inception docs and still correct on the *why*, just stale on *what's built* (they predate voice being embedded in the real frontend, the walkthrough system, and basically everything below). This doc is the "what's actually true now" supplement for backend specifically. The root-level `handover/handover23Augustupdate.md` covers the whole project's history since Aug 5; this one is a close-up on just the last few days.

---

## The big picture: what phase this project is in

The core product loop (agent narrates + drives a pixel-accurate replica of SwishX's real product, voice or chat, deployed to production) has worked since Aug 8. The last two weeks — and especially this last stretch — have been about a different, harder problem: **making the voice conversation feel like talking to a person, not a script with a stopwatch.** That's turn-taking: when to answer, how long to wait, what to do when the prospect talks over the agent or the agent talks over the prospect, and — the newest thread — whether a reply *feels* connected to what was just said or reads as a disconnected non-sequitur.

The method for all of it has been consistent: **real test calls surface real bugs, root-cause against actual logs/transcripts (never assume), fix the mechanism not the symptom, write a regression test that would have caught it, then verify against a live re-test call before considering it done.** That discipline is the most important thing to carry forward — several of the bugs below only became findable because of this, and several near-misses (see "Mistakes worth knowing about" below) happened specifically when a step got skipped.

## Architecture as it stands

```
backend/
  src/
    server.py              # FastAPI REST — /chat, /health, /api/*, runs on :8787
    context/store.py       # SessionState (in-memory, keyed by visitor_id)
    agent/
      registry.py            # UI_REGISTRY — every page/component/action the agent can drive
      runtime.py              # run_turn() / run_turn_stream() — the LLM call + tool-use, ~2900 lines
      walkthrough.py          # the scripted platform-tour step definitions
      knowledge/*.md           # non-interactive facts (pricing, security, integrations)
    voice/
      bot.py                  # Pipecat entrypoint, its own process, :7860
      agent_processor.py       # the turn-taking state machine — VAD, Smart Turn, buffers, ~3400 lines
      turn_telemetry.py        # per-turn latency instrumentation (added this stretch)
    data/                    # dummy backend data (dashboard, analytics, brand kit, email)
```

`server.py` and `bot.py` are **separate OS processes** with separate in-memory session state — this has bitten the project before (a visitor's name not reaching the voice pipeline because it only traveled via the REST call, not the WebSocket URL param) and is worth remembering any time you add a new piece of per-visitor state.

Voice transport is WebSocket, not WebRTC — the production box sits in a private subnet behind an AWS ALB that can't carry WebRTC's raw UDP; this was a deliberate pivot early in the project (Aug 8) and is unlikely to change.

Deploy is push-to-`main`-deploys-straight-to-prod, no approval gate, via a self-hosted GitHub Actions runner installed directly on the box (required because the private subnet has no inbound route for a GitHub-hosted runner). Treat `main` as a live branch.

## What actually happened, day by day

### Aug 20 — turn-taking overhaul begins, rebrand

The stretch opens with a large combined commit: a voice turn-taking overhaul, the SwishX rebrand (this had been ContentIQ-branded before), and meeting-UI fixes. Same day: the scripted walkthrough was found talking over voice input that was still sitting in the settle window (a genuine "the tour doesn't know the room isn't actually quiet yet" bug), and a "serve requests instead of assuming them" fix — the agent was defaulting to opening a generic gallery instead of actually listening for what the prospect asked to see.

### Aug 21 — the big day (28 commits): latency measurement, then a cascade of real-call fixes, then a critical crash

This was the highest-volume day of the whole project. Roughly in order:

- **Turn-taking hardening**: stopped the model from being able to elect its own walkthrough state transitions (a state-correctness principle that recurs constantly — see "Architectural principles" below), made STOP an absolute signal, scoped walkthrough narration per beat instead of letting it bleed across beats, dropped a needless idle check-in.
- **Frontend/UX pass**: landing page redesign (made the live demo the actual front door instead of a generic marketing page), logo/lockup work (drawn from the real supplied asset, not recolored by eye), sidebar cut to three groups, dashboard hierarchy pass, pause actually stopping the agent's speech, bridge phrases varied so silence-filling doesn't sound robotic.
- **Telemetry built from scratch**: `turn_telemetry.py` — before this, the only turn-level timing in production logs was `heard` → `replying`, and `replying` fires after the *whole* response finishes streaming, so the one number available (median 9.9s) was measuring completion, not responsiveness. New per-stage marks let you separately attribute: our own turn-commit latency, the LLM's time-to-first-token, our own text-to-TTS-enqueue overhead, and Cartesia's own synthesis latency. This is what made every subsequent latency decision in this stretch measurable instead of guessed. Three real bugs in the instrumentation itself got found and fixed the same day (two marks sharing one timestamp field, a mark getting overwritten by a later VAD stop, non-turn auto-continue records polluting the dataset) — worth knowing this measurement layer had its own bring-up cost, same as any new subsystem.
- **The adaptive commit window was built and shipped disabled** (`FAST_COMMIT_ENABLED = False`) — an A/B test against the stress harness found it introduces a real correctness regression (a self-correction like "they're very tech savvy — actually, very *less* savvy" gets answered twice instead of once, because the fast path commits before the correction lands). This flag is **still off** as of Aug 23. Don't flip it without first fixing that specific regression — see `test_correction` in the stress harness.
- **Real-call-driven fixes**: three issues found via a colleague's keyboard/headphone test (mic noise suppression, contextual "yes" recognition, honest chat-vs-voice telemetry separation), wizard step-order enforcement, a VAD-duration bug that could permanently kill a reply, a second email transport (Gmail SMTP alongside Postmark, for the current testing/POC phase — see `data/email.py`'s `_send()` dispatcher).
- **The walkthrough-restart bug (session `be5a8774`)** — the day's most significant *design* fix, not just a patch. A farewell reply mentioning "a human rep will walk you through it" was being read by a contradiction-detection guard as *permission to auto-start a tour*, silently restarting the whole platform walkthrough right after the prospect said goodbye. Root cause and fix (worked out with the user's engineering-background collaborator, explicitly discussed and agreed before implementing): **walkthrough state must come from user intent, never be inferred from the assistant's own words.** The guard that used to auto-start a tour from assistant narration now only detects and logs a divergence — it no longer mutates state. This is now a standing principle, not just a one-off fix (see below).
- **CRITICAL bug, found and fixed same day**: a `TypeError` crashing `_advance_after_turn` on *every single real turn* in production. Root cause: a batched editing script's assertion failure silently discarded a signature change (a parameter was added at the call site but not the function definition) while a separate follow-up edit fixed only the call site. It was masked for hours because the fragment-watchdog's own per-pass exception guard (built to stop one bad tick from killing the whole watchdog) silently swallowed the crash instead of surfacing it. Fixed in `8f4be76`, with a new structural test (`inspect.signature()`/`sig.bind()`) specifically designed to catch this exact class of mismatch without needing a live call to surface it. **Lesson that generalizes**: when a batched script changes a function signature and its call site together, verify both landed — don't assume a script that "ran without erroring" actually applied every edit.
- **Repo-wide sweep**: after the be5a8774 fix, the user explicitly asked for a full sweep of the repo for the *same bug class* rather than treating it as one-off. Found two more: two separate "deterministic backstop" mechanisms (`pending_walkthrough_request`, `_promised_to_continue`) that could override an explicit model decision the model had already made that turn — same root cause as be5a8774 (checking "is this state field empty" as a proxy for "did the model miss this," when the field being empty is *also* true when the model considered it and explicitly chose something else). Both fixed with a real "did the model already act" check instead of the empty-field proxy.

### Aug 22 — the two-buffer bug, and the industry-researched settle-window rewrite

Prompted by the user doing a very deliberate stress test on a live call and reporting precisely what they experienced (not what they assumed was happening — they were explicit about this and it mattered): interrupting the agent repeatedly, then noticing the conversation "became messy" — an answer to something *older* arriving after an answer to something newer.

Root-caused via a full millisecond-level reconstruction of the real call (`ed370d2d`) against raw logs: **not** a case of TTS failing to stop (every interruption cut audio within 2-9ms, confirmed) — it was two independently-timed buffers (`_pending_interruption_text`, holding speech that barged in mid-reply, and `_pending_fragment_text`, holding a Smart-Turn-INCOMPLETE accumulator) draining on separate timers with no coordination, so the older buffer could answer *after* the newer one had already started filling. Confirmed independently via telemetry's own internal consistency artifact (a structurally-impossible negative duration on the affected turn) — this is worth reading as a case study in not trusting a single line of evidence.

Fix: at the two drain points where either buffer could fire blind to the other, check the other buffer first and merge oldest-first into one turn when both hold content. Verified via a new stress-harness scenario replaying the exact real fragment sequence, plus the full existing regression suite.

Same day, separately: the **confidence-driven settle window**. The prospect explaining something long, in installments, kept getting answered mid-explanation instead of once — the existing settle-window formula only ever looked at a *discrete step count* of fragments, never at how confident Smart Turn actually was that a given segment was finished. Before touching anything, this was researched against real published industry practice (OpenAI's Realtime API semantic-VAD docs, LiveKit's turn-detector — both use a *continuous* confidence-to-delay mapping, not a stepped timer) — and it turned out pipecat's own Smart Turn model *already computes* a continuous probability internally before thresholding it into the binary verdict we were consuming; we were just discarding it (`state, _ = await self._smart_turn.analyze_end_of_turn()`). New formula interpolates the wait time between a fast floor (confident) and a patient ceiling (uncertain), with the old stepped formula kept as a floor once real fragmentation is already evident — so it can only add patience there, never remove it. Full stress suite: zero regressions, and the terse-speaker case measurably improved (was full-implosion, now separates most of the time) without touching the still-disabled fast-commit flag.

### Aug 23 (early hours) — the reply-coherence fix

A separate, related-but-distinct problem, found on yet another real call (`afe71838`): even when the buffer-merge and settle-window fixes worked correctly, a reply could still *feel* disconnected — a substantive answer, immediately followed by a hollow "Makes sense —" plus a new pivot question, because the model had no signal telling it "the input you're about to answer probably continues what you just said." The model already had full conversation history every turn — this was never a missing-information problem, it was a missing-instruction problem.

Fix: `SessionState.low_confidence_continuation`, mirroring `was_interrupted`'s existing set/read/reset shape exactly, but on a broader trigger — fires when a turn was released with low confidence it was truly the whole point (a forced/stall-backstop or merged-interrupt release, computed explicitly at all 6 `_handle_real_turn` call sites, not read from telemetry — two of those six sites were found to leave telemetry's own `released_by` field silently `None`) **and** it arrived within `CONTINUATION_WINDOW_SECS` of the agent's own last real reply — a new dedicated timestamp, since the existing `_last_activity` clock gets bumped by the current turn's own transcript-commit before any recency check could run, so it couldn't be reused. A new `CONTINUATION_NOTE` (own constant, own prompt-template slot) tells the model to tie back explicitly when this fires, while `INTERRUPTION_NOTE` — a different, pre-existing note protecting a real "still fire actions after an interruption" guarantee — is left completely untouched, by construction, not just by care.

Verified live the same night on the hardest real-world stress test yet (`a0ef497f`, a 51-minute call, ~135 of 163 turns going through a forced/low-confidence path) — no repeat of the disconnected-reply pattern found anywhere in that call.

## Architectural principles established this stretch (don't relitigate these)

- **Walkthrough/session state must come from explicit user intent, never inferred from the assistant's own words.** (be5a8774). Guards that used to *mutate* state on a detected pattern now only detect-and-log; only real user-intent signals mutate state.
- **A deterministic backstop that exists to catch a genuine model miss must check "did the model already act," not just "is the state field still empty."** An empty field is also true when the model considered the situation and explicitly chose something else — the backstop must not override that.
- **When two buffers/timers can both release the same kind of content, neither may fire blind to the other.** Always check the sibling buffer before draining; merge oldest-first if both are holding.
- **Prefer a continuous confidence signal over a discrete step count when one is already available** — and check what the library you're already using computes before building something new (Smart Turn's probability was sitting right there).
- **A signal used to decide *how* to answer must be computed at every place that can produce that release path, not read from a side-channel field that isn't guaranteed to be set everywhere** — the `released_by`-telemetry gap above is the second time this exact category of bug has been found (the first was `_advance_after_turn`'s crashed parameter).
- **Prompt-behavior fixes (as opposed to pure control-flow fixes) can't be proven by unit test alone.** They need a live-call replay or a real re-test call before being called "confirmed" — the settle-window and continuation-note fixes were both stress-tested mechanically *and* verified against real production calls before being considered done.

## Mistakes worth knowing about, so you don't repeat them

- **A batched script that changes a function signature and its call site together can silently apply only half the change.** This produced the critical `_advance_after_turn` crash. If you ever write a script that edits two coupled locations, verify both landed independently afterward.
- **A watchdog's own defensive per-pass exception guard can mask a real bug for hours** if it just logs and continues instead of surfacing. The fix wasn't to remove the guard (it's genuinely needed — one bad tick shouldn't kill the whole watchdog) but to make sure crashes are still loud enough to notice quickly.
- **A stress-test harness constant that isn't scaled the same way as the system it's testing will silently test something that doesn't exist.** Happened twice this stretch (`SETTLE_MIN_SECS`/`SETTLE_MAX_SECS`, then `CONTINUATION_WINDOW_SECS`) — the harness has a self-check for this now (`_EXEMPT`/`_SCALED` exhaustive ledger in the stress runner), but the check only catches "did you forget this constant entirely," not "did you add the scaling *assignment* line too" — that part still has to be done by hand each time.
- **Timestamps in a raw production log are not the same as true acoustic silence gaps** — they're inflated by STT + Smart Turn processing latency. A replay built from log-line timestamps directly produced an extra, wrong split that never happened on the real call. `turn_telemetry.py` deliberately emits only derived durations, not raw timestamps, so there currently isn't a way to build a millisecond-faithful replay of a historical call — flagged, not yet resolved.

## What's live in production right now (as of `3adc289`, 2026-08-23 01:51 UTC)

Confidence-gated continuation note, confidence-driven settle window, the buffer-merge fix, the be5a8774 walkthrough-intent fix and the two backstop-precedence fixes, the crash fix, SMTP as a second email transport, mic noise suppression, contextual "yes" recognition. `FAST_COMMIT_ENABLED` is off. The stall-backstop's grace period (`PENDING_FRAGMENT_STALL_GRACE_SECS`) is still a flat 4.0s, not confidence-adaptive — see "Open items" below.

## Open items — where to pick up

1. **The stall-backstop grace period is still flat, not adaptive.** Confirmed as the single most-repeated piece of direct user feedback on the `a0ef497f` call (turns 193-202, 309-320) — the user independently specified the fix shape themselves: start with a short timeout, stretch it once the system senses someone building toward something long, with a hard ceiling so the agent doesn't overcorrect into rambling. This is the natural next fix, and it already has a clear spec from a real call.
2. **A UI-action-claim overclaim bug in the MLR Review queue**: the agent claims "opening a submission" via an action that's actually just a generic queue-highlight — there's no real per-submission-open capability. Same shape as an earlier-session dossier-selection narration bug. Found on `a0ef497f`, turns 174-192.
3. **`FAST_COMMIT_ENABLED` stays off** pending a fix to the self-correction "answer explosion" regression found in its own A/B test. Don't enable without fixing that first.
4. **No millisecond-faithful historical-call replay is currently possible** — `turn_telemetry.py` strips raw timestamps by design. If real-call regression testing against exact historical timing becomes a priority, that needs either raw VAD-timestamp logging added going forward, or an accepted-imprecision replay method.

## Testing

No formal test suite lives in the repo yet — all tests from this stretch live in the session scratchpad (`/private/tmp/claude-502/.../scratchpad/`, session-specific, not persisted in git). The most load-bearing ones, if you want to reconstruct a permanent suite: `stress.py`/`stress_run.py` (the adversarial turn-taking harness, 12 scenarios), `test_turntaking.py`, `test_bargein.py`, `test_floor.py`, `test_gap.py`, `test_consolidation.py`, `test_pause.py`, `test_buffer_merge.py`, `test_confidence_settle.py`, `test_continuation_note.py`. Worth promoting into the actual repo as a real `tests/` directory — flagged, not done, since nothing this stretch touched test infrastructure itself.
