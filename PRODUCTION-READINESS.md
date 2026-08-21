# What's left before this is genuinely production

Written 2026-08-21, after the overnight session. Deployed commit: `8c01ffb`.

Confidence labels are honest. **Verified** means I watched it work. **Tested** means
automated tests cover it but no human has heard/seen it. **Unverified** means the code
is written and reasoned about but nothing has exercised it. **Untested** means nobody
has ever tried this path at all.

---

## 1. Hard blockers — these will bite during a real demo

### 1.1 Only ONE call can happen at a time on this box
**Verified — this is by design and currently enforced.**

`server.py:373` `/api/voice-lock/claim` holds a single global `_active_call`. A second
visitor clicking Talk gets `{"ok": false}` and a busy message. The lock TTL is
**30 minutes** (`_CALL_LOCK_TTL_SECS`).

Why it matters now: several SwishX people are meant to use this in the next few days.
If two of them try simultaneously, one is simply refused. And if a call dies without a
clean release (browser crash, laptop sleep, network drop mid-call), the lock can sit
held for up to 30 minutes and nobody else can get in.

Mitigations, cheapest first:
- Drop the TTL to ~3 minutes and have the frontend heartbeat the lock while connected.
  A dead call then frees itself in minutes instead of half an hour.
- Add an admin "force release" button (one endpoint, already have the admin panel).
- Real fix: allow N concurrent calls. Sessions are already keyed by `visitor_id`
  (`context/store.py:208`), so the state layer is fine. The question is whether one
  voicebot process can carry multiple pipelines — needs a real load check, not a guess.

### 1.2 Postmark is not configured in production at all
**Verified.** Prod `backend/.env` contains: `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`,
`PORT`, `GROQ_API_KEY`, `CARTESIA_API_KEY`, `CARTESIA_VOICE_ID`, `LLM_PROVIDER`,
`DEEPGRAM_API_KEY`. No `POSTMARK_API_KEY`, no `POSTMARK_EMAIL`.

So: **no post-session summary email has ever gone out from prod, and none will.**
`email.py:109` raises `EmailSendError` when either var is missing. It fails safely (the
summary still saves to the DB before the send is attempted, and the exception is caught
in `bot.py:112`), so nothing crashes and the admin panel still shows summaries. But the
feature is dark.

Also blocks re-enabling OTP, since that uses the same provider.

The underlying deliverability problem is still unsolved: Postmark accepts every send
(`ErrorCode: 0`, real MessageIDs) and nothing arrives. 1007 hard-bounce suppressions on
the account, top domains gmail.com (157), swishclub.in (108), swishx.com (85). Your
address is not suppressed and no bounce was recorded for it. My read is that
`noreply@swishclub.in` sending to `@swishx.com` has a domain-alignment problem, and it
needs a **verified `@swishx.com` sender signature** with DKIM/SPF. I could not check
sender signatures — that needs the Postmark Account token and I only have the Server
token.

### 1.3 The Deepgram key needs rotating
`DEEPGRAM_API_KEY=b8323...` was pasted into our chat and is now in the session
transcript. Working fine in prod. Rotate it after the demo push.

---

## 2. Known bugs — diagnosed, root-caused, NOT fixed

These are all real, all seen in production transcripts. None is fixed.

### 2.1 She narrates screen state that isn't real
Says things like "I've got the Nikotex dossier selected here" when the screen still
shows Oflox OZ. Root cause: most selectable fields (dossier, audience, topics, goal,
voice, language, logo position, script structure, target length, music) have **no
per-option action** — the handler only jumps the wizard step, and the value stays on
its hardcoded default. Only tier selection is genuinely wired.

There is a narration rule in the prompt telling her to acknowledge the request and
connect it to the pre-loaded default without claiming a switch happened. Prompt rules
are not guarantees. This is the most credibility-damaging failure mode we have, because
a prospect can see the screen disagreeing with her.

### 2.2 Apology loop
Six apologies in 41 turns on one call. She apologises for silences, for
misunderstandings, and then apologises for apologising. Reads as nervous, not
competent.

### 2.3 She invents explanations for her own silences
When there's been dead air she'll explain it with something that didn't happen
("I was just pulling that up"). It's plausible-sounding and false. Related to 2.1 —
she narrates system state she has no access to.

### 2.4 Two buffers still hold the prospect's words
`_pending_fragment_text` and `_pending_interruption_text` are separate paths that can
each hold speech. The interruption one now has a 6-second deadline
(`PENDING_INTERRUPTION_MAX_HOLD_SECS`) so it can't strand words forever, and the
watchdog is now crash-proof per pass. But the two buffers were never unified — that's
~38 call sites and I did not attempt it at 4am. Low probability of biting, non-trivial
blast radius if it does.

### 2.5 Walkthrough step 9 points at the Analytics page, which no longer fits
**Verified.** Step 9 is "Analytics tab" and highlights `analytics/funnel`. The page is
still rendered (`useProductPages.tsx:93` keeps it reachable by voice even with no
sidebar entry), so the tour won't break — but:
- The page content is **campaign/channel metrics** ("By Campaigns", "Channel",
  "Specialty") which is exactly the story you had me strip out of the sidebar and the
  dashboard. A prospect on the full tour will be shown a screen about campaigns.
- With no sidebar entry there's nothing for the sidebar highlight to ring on that step.
  **Unverified** what that looks like — worth one run.

### 2.6 Small content mismatches
- `TopBar.tsx:9` search placeholder still reads "Search campaigns, content, HCPs…"
- 8 of 10 walkthrough steps have no sub-beats (only steps 6 and 7 do), so pacing and
  brevity are uneven across the tour — steps 1–5 and 8–10 are one long beat each.

---

## 3. Shipped tonight, thinly tested — the "on radar" list

This is the section you asked for. All of this is deployed and none of it has been
heard or seen by a human on a real call.

### 3.1 The pause fix — **tested, not verified** ⚠️ highest risk
7/7 unit tests pass and I traced the logic. **Nobody has pressed the button since the
fix.** Specific paths I did NOT exercise:
- Resume actually continuing from `_paused_remainder` rather than repeating or dropping
  the rest of the reply.
- Pause **mid-walkthrough-step**, then resume — does the tour pick up the same step, or
  re-fire the action?
- Pause while a filler word is playing (a 1-second utterance; the guard may land after
  it finished).
- Pause, then hang up without resuming — does the lock release, does the summary save?
- Double-press / press-during-resume race, now that the poll is 2.5x faster.

If it misbehaves, the signature to look for in the log is `_paused_remainder` being
`None` when it shouldn't be.

### 3.2 The new filler words — **unverified** ⚠️ highest exposure
On every single turn, so any problem is immediately obvious to a prospect. Two specific
risks:
- **Does Cartesia say "Hmmm" and "Ummm" as sounds, or spell them out?** I never
  confirmed this. If it spells them, every turn opens with a robot reading letters.
  This is the single cheapest thing to check — one call, first turn.
- "Great question" is gated to actual questions now, but the gate is a heuristic on the
  prospect's text. Watch for it firing on a navigation command.

### 3.3 The fragment-watchdog per-pass guard — **tested, not verified**
Brand-new code in the hot path of every call. Exercised only by tests. It should be
strictly safer than what it replaced. But if it's swallowing an exception that used to
be visible, the symptom would be a silent stall with `fragment watchdog pass failed`
appearing repeatedly in the log. Worth one grep after your first call:
`journalctl -u contentiq-voicebot | grep "watchdog pass failed"`.

### 3.4 The dashboard redesign — **verified at 1500px only**
Checked in a real browser on prod at 1500x1000. Not checked at:
- 1280px or 1440px (a normal laptop) — the `.dash-split` and `.insight-grid` collapse
  to one column below 1100px, so 1100–1300 is the untested band.
- Mobile.
- **The walkthrough spotlight on the new grid.** Step 10 highlights
  `insights:highlight`, and the target geometry changed from one 1080px-tall card to a
  474px 2x2 grid. The registry parity check passes (the `data-hl` is intact) but the
  dim-backdrop and ring geometry over the new shape is **unverified**. Same for
  `brand-dossiers:highlight`, which is now a two-column grid inside the card.

### 3.5 The opening discovery questions — verified ONCE
One live run captured all three fields (pain, urgency, budget). One run. Untested:
someone who deflects, someone who answers two at once, someone who asks a question back
instead of answering.

### 3.6 The landing page — verified at a few widths
The badge flip animation, the hover fix, and the form's three states were checked on
desktop. Not checked on a real phone or on Safari.

### 3.7 The personal-email exception
`jshreyansh34@gmail.com` is allowed in `frontend/src/lib/email.ts:19`. The gate is
enforced **client-side only** — the backend `/api/visitor/gate` records the attempt but
doesn't re-validate the domain. Fine for a demo, worth knowing. Whether the gate
actually lets that address through end to end is **unverified** (you asked, I shipped
it, you never confirmed it worked).

---

## 4. Never tested at all

### 4.1 Two humans on the same call ⚠️
You described the real scenario yourself: two people join, greet each other, socialise,
then talk to the agent. **Nothing about this has been tested.** Everything — VAD, Smart
Turn, the consolidation window, the interruption logic — was built and tuned for one
speaker. Two people talking to each other will look to the pipeline like one person
producing overlapping fragments. My honest expectation is that this degrades badly:
she'll answer things said between the two humans.

This is arguably a bigger risk than anything in section 3, because it's your stated
primary use case.

### 4.2 Bad network / mobile / Safari
The whole thing is a WebSocket audio pipeline. Never tested on a flaky connection, on
cellular, on a phone, or in Safari. No reconnect logic has been exercised.

### 4.3 A long call
Never run past ~15 minutes. Unknown: history growth, token cost per turn as the
transcript accumulates, whether the 10-minute pacing instruction does anything
sensible at minute 25.

### 4.4 Provider failure mid-call
If DeepSeek times out or errors mid-turn, there's a fallback path but it has never
fired in anger. Same for Cartesia and Deepgram. Deepgram at least has a verified
import-level fallback to Groq (that's the one I broke and fixed).

### 4.5 The database has no backup and lives inside the deploy directory
`backend/src/data/app.db`, 278KB, holds every visitor, transcript, qualification field
and call summary. No cron, no backup, no snapshot. It survives the current deploy
(which is a `git pull`), but any operation that cleans the working tree loses all of
it. Cheapest fix: a nightly `cp` to `/opt/backups` plus a weekly copy off-box.

---

## 5. Product gaps (not bugs, just unbuilt)

- Stub pages with no real content: Campaigns, Audience, Content Library, Templates,
  Brand Dossiers, Claims Library, Re-engage. Some of these are correctly "Soon" in the
  real product; some aren't and would look thin if a prospect asks to see them.
- Module-scoped tours ("just show me MagicReel") — you deferred this to the morning.
- Walkthrough brevity on the 8 steps without sub-beats.
- Analytics page content rewrite (see 2.5).

---

## Suggested order when you wake up

1. **One 5-minute call.** Listen for: does she say "Hmmm" or spell it; press pause
   twice mid-sentence and once mid-walkthrough; then grep for
   `watchdog pass failed`. That covers the three riskiest things I shipped tonight in
   one pass.
2. **Decide on concurrency** (1.1). If several people are using it this week, the TTL
   drop plus a heartbeat is maybe an hour of work and prevents the most embarrassing
   possible failure: a colleague being told the demo is busy.
3. **Postmark sender signature** (1.2) — this is blocked on Postmark account access,
   not on code.
4. **Two-people-on-a-call** (4.1) — at minimum, know how bad it is before a real
   prospect meeting. Grab a colleague and try it.
5. Then the narration lie (2.1) and the apology loop (2.2), which are the two things a
   prospect would actually notice and remember.
