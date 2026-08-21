# Getting to world-class conversational voice: diagnosis and plan

2026-08-21. Grounded against production session `7d0018d3` (commit `8c01ffb`), the
current code, and published numbers from the teams who have solved this.

---

## 1. What "world-class" actually is, numerically

The bar you named (ChatGPT voice) is not a vibe. It's a measured latency budget, and
the industry has converged on it:

| Metric | World-class target | Fleet reality (p50/p95) |
|---|---|---|
| User stops speaking → agent starts speaking | **500–800 ms** | 680 ms / 1,180 ms |
| Streaming STT (Deepgram Nova-3) | 60–350 ms | |
| LLM time-to-first-token | 100–375 ms | |
| TTS first chunk (Cartesia Sonic) | 40–100 ms | |
| VAD + turn-taking decision | 150–300 ms | |

The load-bearing insight from that research, which contradicts where we've been
spending our effort:

> **STT and TTS are not where latency hides. It hides in turn-taking and LLM
> time-to-first-token.**

We have been tuning filler vocabulary. The two things that actually decide whether this
feels world-class are the two things we haven't touched.

---

## 2. Where we actually are

From the production call, before she makes any sound at all:

| Stage | Ours | Target |
|---|---|---|
| Turn commit (user stops → we accept the turn) | **1,500–2,600 ms**, backstop 4,000 ms | 150–300 ms |
| Turn commit via the 4s stall backstop | 3 of 15 turns | ~never |
| LLM: single call doing reply + UI action + walkthrough state + qualification | ~10 s to complete | TTFT 100–375 ms |
| TTFA (time to first audio) | **unmeasurable — no log line exists** | 500–800 ms |

So on turn commit alone we are **5–15× off the bar**, and that cost is paid on *every
single turn* before any model is even consulted.

For scale: LiveKit's own guidance notes that an 800 ms silence timeout "adds nearly a
full second to every single response." Ours is 1,500–2,600 ms.

---

## 3. The root cause, and it's my bug

This is the deepest finding, and it isn't about fillers at all.

**We run a semantic turn detector, get its answer in ~65 ms, and then throw it away.**

`agent_processor.py:1047` runs Smart Turn v3 and stores its verdict. Smart Turn exists
for exactly one purpose: to decide *"has this person finished their thought?"* using
prosody and semantics rather than a stopwatch. It answers in about 65 ms. Model-based
turn detection's entire latency advantage is that **it can fire before the trailing
silence even happens.**

And then, at `agent_processor.py:1092–1109`, when Smart Turn says COMPLETE, we... start a
1.5–2.6 second silence timer anyway.

We are paying the full latency cost of a timer-based system *while also* running the
model that was supposed to replace the timer.

### Why I did that

To fix a real bug: six sentences with breaths between them came back as six separate
answers. I built the consolidation window, and it worked.

### Why it was the wrong fix

I checked the harness that drove that decision. `stress_run.py:61`:

```python
async def s_slow_then_fast(h):
    for i in range(6):
        await h.say(f"so the thing is number {i}", dur=1.1, incomplete=(i % 2 == 0))
```

and `s_long_ramble`, line 67, calls `h.say(...)` with **no `incomplete` argument at
all** — which defaults to `False`, i.e. **COMPLETE**. So my harness declares all twelve
clauses of "a long explanation with natural breaths" to be finished thoughts.

That is not what Smart Turn v3 would say about that audio. A clause delivered
mid-thought with flat or rising intonation is precisely what the model is trained to
call INCOMPLETE. My harness is text-driven — it has no audio, so it **fakes the verdict**,
and it faked it wrong in the direction that made the model look useless.

So: I tested the turn detector by lying to it, concluded it couldn't be trusted, and
replaced it with a stopwatch. **The 1.5–2.6 second window is compensating for a defect
in my test harness, not for a defect in Smart Turn.**

That single mistake is, I believe, the largest cause of "the conversation isn't
world-class."

---

## 4. How the field actually solves this

Three named techniques, all of which apply to us.

### 4.1 Trust the semantic detector; use the timer only as a backstop

Model-based endpointing fires on semantic completeness, not silence duration. The
correct hierarchy is: Smart Turn decides, VAD silence is the fallback for when the
model is uncertain. We have this exactly inverted.

### 4.2 Preemptive (speculative) generation

> "Preemptive generation speculatively starts an LLM response before the user's end of
> turn is confirmed." and "feeds stable partial transcriptions into the LLM and revises
> if the final transcript differs — a form of speculative execution that **hides the
> endpointing delay behind LLM prompt processing**."

This is the big one for us. Right now our 1.5–4 s endpointing delay is *pure dead time* —
the LLM isn't even running. If we start generating on the stable partial transcript, that
window costs nothing, because the model is already working through it.

**Pipecat ships this as a `preemptive_generation` parameter.** Our installed 1.7.0 does
not have it (verified: `"preemptive" in PipelineParams source → False`), so this needs
either a framework upgrade or a hand-rolled equivalent.

### 4.3 Talker–Reasoner ("conversational infill")

This is the published version of the fast-lane/slow-lane split, and it has numbers.
*Thinking While Speaking* (arXiv 2511.07397): a small local **Talker** owns the
conversation and produces *contextually grounded* speech while a frontier **Reasoner**
works asynchronously, streaming semantically complete phrases the Talker weaves in as
they arrive.

- Time-to-first-response: **542 ms** (direct), **976 ms** (RAG) vs **2,947–7,242 ms** for
  the frontier model alone
- **7.4×–19.1×** speedup, accuracy within **6.3%** of the frontier model
- User study (n=18): rated equivalent on most metrics, **significantly better perceived
  responsiveness**
- And explicitly: it "substantially outperforms generic static fillers like *I'm
  thinking*."

That last line is the empirical answer to the whole filler-words argument. The fix isn't
better filler words. It's a small model that has actually read what the person said.

---

## 5. The plan, specific to our architecture

Ordered so that each phase is shippable and the risky ones come after we can measure.

### Phase 0 — Stop the bleeding (2–3 h, safe, ship immediately)

Nothing architectural. Fixes what ruined last night's call.

1. **One backchannel per user turn, cancellable.** Move the counter off the per-fragment
   re-arm (5 sites) onto a real turn boundary; cancel any pending nod when the semantic
   response arrives. Kills the `Right / Mm / Mm-hm / Sure` clusters.
2. **Cap auto-continue at 2 consecutive beats** without user input, and hard-stop on an
   explicit floor-yield. This is what produced the 8-beat monologue that ended the call.
3. **Confirm Cartesia renders "Hmmm" as a sound, not letters.** One call. Still unverified
   and it's sitting in production.

### Phase 1 — Instrumentation (2–3 h, do before touching timing)

Structured per-turn JSON events. Non-negotiable field: **TTFA**. I could not answer "how
long before she made a sound" from last night's logs, and every decision below depends
on that number. Report TTFA and TTFC separately — a 10 s turn that starts talking at
700 ms is fine; a 3 s turn that starts at 2.9 s is not.

### Phase 2 — Fix the harness, then un-neuter Smart Turn (1 day) ⚠️ the big win

**2a. Fix the harness first.** Replay real call audio, or at minimum drive the scenarios
with the verdicts Smart Turn actually returns rather than hardcoded defaults. Until this
is done, the harness will keep voting for the stopwatch.

**2b. Invert the hierarchy.** Smart Turn COMPLETE + no fragmentation this turn →
**commit at ~200–300 ms**. Fragmentation seen → current consolidation. INCOMPLETE →
hold, unchanged (this is the case the window was actually built for and it stays).

Expected: turn commit goes from 1,500–2,600 ms to ~300 ms on the common case. That alone
is most of the gap to world-class.

**Risk is real** — this is the exact axis where I previously traded correctness for
latency and lost. Mitigation is 2a: a harness that isn't lying.

### Phase 3 — Preemptive generation (1 day)

Start the turn on the stable partial transcript; discard and re-run if the final
transcript materially differs. Turns the remaining endpointing window into free time.
Decide first whether to upgrade Pipecat (gets it natively, but a framework upgrade on a
live demo box needs its own risk assessment) or hand-roll it in our processor.

### Phase 4 — Talker/Reasoner split (1–2 days)

Our current single DeepSeek call decides reply + action + walkthrough + qualification in
one schema, which is why it takes ~10 s. Split it: a fast lane that has read the
utterance and holds the floor with something *correct*, and the existing call as the
Reasoner. This is what replaces fillers entirely.

### Phase 5 — Speech scheduler + walkthrough state machine (1–2 days)

`_speak()` is already the single choke point (I made it one for the pause fix), so this
is extending it with queue/priority/cancel rather than building it. Then the walkthrough
becomes an explicit state machine — fixing both the monologue and the out-of-order beats
(she described Source option 1 at 02:08:50, then introduced the Source section at
02:09:00).

Worth noting: we have now hit the *same bug shape three times* — walkthrough stop-latch,
pause button, backchannel. Every one was "authoritative state existed, one output path
didn't consult it." Phase 5 is how that class of bug stops recurring.

---

## 6. The honest ceiling

Phases 0–4 should get us to roughly **600–900 ms** perceived response, no nod clusters,
no monologues. That is a genuinely good voice agent and I think it clears your
"distribute it anywhere" bar.

It will still not *be* ChatGPT Advanced Voice, because that is a different class of
system: audio in, audio out, one model, no text boundary, and now full-duplex — it
listens while it speaks and makes interaction decisions many times per second. Our
cascade destroys prosody at the STT boundary and can never recover it.

If matching that specific feel is the real goal, the honest path is evaluating a
speech-to-speech realtime model as the conversational layer, with our current stack
demoted to tool-execution. That's a strategic decision, not a sprint, and it would change
what the LLM/tool layer is for. **It should not block Phases 0–2, which are worth doing
under any architecture.**

---

## 7. What I'd want from you before Phase 2

Three questions where your judgment beats mine:

1. **Risk appetite on turn commit.** Faster commit means occasionally cutting someone
   off mid-thought. For a sales demo, is being interrupted-once worse than being
   waited-on-every-turn? I lean fast; you've watched real prospects.
2. **Pipecat upgrade.** Preemptive generation comes free with a newer framework, but
   that's a dependency bump on a box running live demos this week. Upgrade, or hand-roll?
3. **Do we have call audio recorded anywhere?** Phase 2a is much stronger with real audio
   than with reconstructed scenarios. If not, worth capturing a few calls first.

---

**Sources**

- [Under One Second: Structuring Latency Budgets for Voice AI](https://agxntsix.ai/blog/voice-ai-latency-budgets-enterprise)
- [Voice AI Latency: Sub-250ms Architecture Guide — Prodinit](https://prodinit.com/blog/production-voice-ai-agents-latency-architecture)
- [Turn Detection for Voice Agents: VAD, Endpointing, and Model-Based Detection — LiveKit](https://livekit.com/blog/turn-detection-voice-agents-vad-endpointing-model-based-detection)
- [Smart Turn Overview — Pipecat docs](https://docs.pipecat.ai/api-reference/server/utilities/turn-detection/smart-turn-overview)
- [Preemptive speech generation — Pipecat issue #3321](https://github.com/pipecat-ai/pipecat/issues/3321)
- [Thinking While Speaking: Inference-Time Knowledge Transfer (ConvFill) — arXiv 2511.07397](https://arxiv.org/html/2511.07397v3)
- [Voice agent latency optimization — ElevenLabs](https://elevenlabs.io/blog/voice-agent-latency-optimization)
- [Introducing GPT-Live — OpenAI](https://openai.com/index/introducing-gpt-live/)
- [ChatGPT Live and the New Architecture of Voice AI — RisingStack](https://blog.risingstack.com/chatgpt-live-new-architecture-of-voice-ai/)
