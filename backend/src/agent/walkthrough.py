from dataclasses import dataclass
from typing import List, Optional, TypedDict


class WalkthroughAction(TypedDict):
    page: str
    component: str
    method: str


@dataclass
class WalkthroughStep:
    index: int
    title: str
    action: Optional[WalkthroughAction]
    guidance: str
    # Spoken-length budget for THIS beat, in words, surfaced to the model as a
    # number for this beat specifically rather than as a global plea.
    #
    # A global "be brief" instruction demonstrably does not work: the tool
    # schema has said "one or two short sentences by default" since the
    # beginning, and a real production call (visitor 35ad314a, 73 agent
    # turns) came back with a median of 39 words, p90 of 72, and a single
    # reply of 171 — roughly 68 seconds of uninterrupted speech. Prose about
    # length competes with all the other prose and loses whenever the content
    # feels rich.
    #
    # A per-beat number is different in kind: it is specific, it is attached
    # to the thing being narrated, and _finalize_turn logs every overshoot so
    # drift shows up in a query instead of in a demo.
    max_words: int = 40


@dataclass
class SubBeat:
    """One sub-stage inside the MagicReel/MagicAvatar studio flows.

    Steps 8 and 9 each cover a whole wizard (13 and 6 sub-actions), and their
    step.guidance used to be a single 434-word / 192-word block describing
    ALL of them — re-sent to the model on EVERY turn of that step. Having the
    entire flow in front of it on turn one is why it narrated the entire flow
    on turn one; the model was doing what it was shown, not misbehaving.

    Splitting the prose per sub-action lets _walkthrough_note surface only
    the beat actually being performed. The sub-action ORDER and the state
    machine around it are unchanged — this is purely about how much of the
    script is visible at a time.
    """
    guidance: str
    max_words: int = 32


# The scripted platform tour's fixed sequence and target actions, hardcoded
# here rather than left to the model to decide turn-by-turn — the same
# reasoning as CONTENT_STUDIO_FORMATS in registry.py and the qualification
# system's SessionState fields: letting the model freely reconstruct its own
# position/order from prose alone is exactly what caused drift (skipped or
# reordered steps) earlier in this project.
#
# Load-bearing design rule, learned the hard way from real testing: ONE STATE
# INDEX = ONE ATOMIC ACTION, ALWAYS. An earlier version of this file had a
# single "Format pop-ups" step whose guidance prose asked the model to fire
# THREE different actions (MagicReel, MagicAvatar, MagicChart opens) across
# several turns while tracking "which have I already shown" purely by
# rereading its own conversation history — real testing (both DeepSeek and
# Claude) showed this is exactly the kind of multi-item bookkeeping LLMs get
# wrong under real conversational pressure: wrong item picked, an item
# skipped outright, or the step stalling with no progress at all. Splitting
# that one step into three separate single-action beats removes the memory
# burden entirely — each beat's note ever asks for exactly one deterministic
# action, never "the next one in a mental list." See runtime.py's
# _walkthrough_note for how a beat gets surfaced to the model each turn.
#
# The two studio-flow beats (MagicReel, MagicAvatar) are the one deliberate
# exception: they each stay on their own single index for many turns while
# the ALREADY-existing, already-verified-reliable wizard step-by-step pacing
# (system prompt instruction 2c) handles the internal sub-navigation. That
# mechanism doesn't share this bug because it doesn't ask the model to track
# a set of interchangeable items — it's a strictly ordered, one-directional
# progression (Source -> Brief -> Script -> Scenes -> Generate) with an
# explicit go-ahead gate at each hop, a different and already-proven pattern
# left untouched here.
#
# Beat 1 fires no action: the prospect is already on Home (session's
# default current_page) when the call starts, so the overview just talks —
# it's not a deliberate visit. Home only gets one deliberate,
# explicit visit, as the final wrap-up (beat 13), not bookending the tour.
#
# Every action below already exists in registry.py's UI_REGISTRY — this
# feature needed no new registry actions and no frontend changes.
WALKTHROUGH_STEPS: List[WalkthroughStep] = [
    WalkthroughStep(
        index=1,
        title="Overview",
        action=None,
        guidance=(
            "Give a short, own-words 2-3 sentence overview of what SwishX does — pull from "
            "the product overview above, don't recite it verbatim. No navigation needed for "
            "this step, you're already on Home — but don't frame that as a deliberate "
            "stop either (no \"let's start on the home page\" or \"I'll walk you through the "
            "home page first\") since nothing here actually gets toured or explained beyond this "
            "overview; Home's own explicit, deliberate visit is step 13's wrap-up, not "
            "this one. If you preview where the tour is headed, the real next stop is Brand "
            "Dossiers (step 2), NOT Content Studio — Content Studio is real but it's step 4, "
            "several stops later; don't say \"I'll start with Content Studio\" or similar, "
            "that's the OLD tour order and is wrong now. Safest is to not name a specific "
            "destination at all here and just move straight into the tour."
        ),
    ),
    WalkthroughStep(
        index=2,
        title="Brand Dossiers",
        action={"page": "brand-dossiers", "component": "grid", "method": "highlight"},
        guidance=(
            "A quick beat only — land on the Brand Dossiers grid and say this is the brand's "
            "master knowledge base, the single source of truth every generation pulls from. Do "
            "NOT catalogue individual dossier cards, categories, or how many exist — that's not "
            "the point of this beat. Move straight into opening one; the real payoff is next step."
        ),
        max_words=24,
    ),
    WalkthroughStep(
        index=3,
        title="Brand Dossier detail",
        action={"page": "brand-dossier-detail", "component": "checks", "method": "highlight"},
        guidance=(
            "This is the MLR moat made concrete — spend real time here, this is one of the two or "
            "three beats in the whole tour that actually earns its length. Open the dossier's "
            "actual document. Mention where it stands briefly (percent complete, how many sections "
            "are fully sourced vs. still needing data) — that's scene-setting, not the point. The "
            "point is the MLR Reviewer banner and the Checks panel: every claim in this document "
            "gets checked against an approved source AT GENERATION TIME, not fixed up afterward in "
            "review — most pass automatically, but here a handful didn't and are flagged right on "
            "the document as 'unverified — not source-backed,' waiting for a human to accept or "
            "keep unverified before export. Tie this explicitly back to the core claim: MLR-ready "
            "in minutes, not weeks, because the checking already happened, so review starts from an "
            "already-vetted document instead of a blank one."
        ),
        max_words=70,
    ),
    WalkthroughStep(
        index=4,
        title="Content Studio",
        action={"page": "content-studio", "component": "video-tab", "method": "click"},
        guidance=(
            "Land on Content Studio generally and mention it covers 30 formats across 5 Magic "
            "Engines — Video, Aid, Mail, Canvas, Doc. Don't click through every engine tab "
            "individually, just land here and describe it."
        ),
    ),
    WalkthroughStep(
        index=5,
        title="MagicReel pop-up",
        action={"page": "content-studio", "component": "magicreel", "method": "open"},
        guidance=(
            "Open a quick pop-up preview of MagicReel (short-form video) with a short beat of "
            "narration — don't linger, this is a glance, not the deep dive (that's beat 8)."
        ),
    ),
    WalkthroughStep(
        index=6,
        title="MagicAvatar pop-up",
        action={"page": "content-studio", "component": "magicavatar", "method": "open"},
        guidance=(
            "Open a quick pop-up preview of MagicAvatar (the digital-twin presenter video) with "
            "a short beat of narration — again, a glance, not the deep dive (that's beat 9)."
        ),
    ),
    WalkthroughStep(
        index=7,
        title="Infographic pop-up",
        action={"page": "content-studio", "component": "magicchart", "method": "open"},
        guidance=(
            "Open a quick pop-up preview of the Infographic format (component \"magicchart\") as "
            "your Magic Canvas example — a short beat of narration, then move on."
        ),
    ),
    WalkthroughStep(
        index=8,
        title="MagicReel flow",
        action={"page": "magicreel-studio", "component": "wizard", "method": "step-source"},
        guidance=(
            "Enter the MagicReel studio at the Source step and walk it end-to-end — Source, "
            "Brief, Script, Scenes, Generate — one stage at a time, narrating each before moving "
            "on (see instruction 2c's active-walkthrough pacing: keep advancing stage to stage on "
            "your own, only actually pausing for a genuine question, not a per-stage go-ahead "
            "check). Source and Brief each have real sub-options underneath them — don't just "
            "describe all of a stage's sub-options in one breath while sitting on only one of "
            "them; actually click through each as you mention it, one per turn, same continuous "
            "pacing as the outer stages. For Source: a turn each for \"select-source-dossier\", "
            "\"select-source-news\", \"select-source-custom\" as you describe brand dossier, news "
            "article, and custom brief in turn (land back on whichever you're actually using — "
            "usually dossier — before moving to Brief). For Brief: a turn each for "
            "\"brief-audience\", \"brief-voice-language\", \"brief-brand-product\" as you cover "
            "audience configuration, voice/language, and brand/product in turn. Because each of "
            "these sub-options gets its own real explanation a turn or two later, the turn that "
            "first lands on Source or Brief (\"step-source\"/\"step-brief\") should be a brief, "
            "one-sentence transition only — name the stage and that it has a few parts, don't "
            "summarize what those parts do, since you're about to explain each one properly right "
            "after; a content preview here just gets said twice. Script has its own required "
            "button press too, same reasoning as Generate below: once you land on \"step-script\", "
            "the very next turn must actually fire \"generate-script\" as its own dedicated action "
            "— narrate that you're generating the draft (e.g. \"let's generate that script\"), don't "
            "just mention hitting generate and jump straight into Scenes in the same breath, that "
            "skips the button press entirely and the prospect never sees the script actually get "
            "drafted. Generate is a "
            "real, separate stage, not just something to mention while "
            "wrapping up — when you get there, actually fire component \"wizard\" action "
            "\"start-generation\" as this turn's action (after \"step-generate\" got you onto that "
            "stage), and let your reply narrate what's about to render, e.g. \"let's generate this\" "
            "— don't just talk about generating and jump straight to step 9 in the same breath, "
            "that skips the step entirely and the prospect never sees it render. The render itself "
            "takes several seconds — a short beat of narration bridging that wait is fine, or use "
            "the next turn once it's ready. Only once the result has actually been shown (the "
            "rendered reel, not just the button press) is this outer step done — move into step 9 "
            "on the turn AFTER that, not the same one."
        ),
    ),
    WalkthroughStep(
        index=9,
        title="MagicAvatar flow",
        action={"page": "magicavatar-studio", "component": "launchpad", "method": "open"},
        guidance=(
            "Open the MagicAvatar Launchpad, then start the Master wizard (create-master) and "
            "walk it end-to-end the same way as MagicReel — Brief, Scenes, Options, Generate — "
            "one stage at a time, same continuous active-walkthrough pacing as step 8. Brief has "
            "its own required button press before Scenes, same reasoning as Generate below: once "
            "you land on \"step-brief\" here, the very next turn must actually fire "
            "\"generate-breakdown\" as its own dedicated action — narrate that you're turning the "
            "brief into a scene breakdown, don't just mention that button and jump straight into "
            "Scenes in the same breath, that skips the button press entirely. Generate is "
            "a real, separate stage here too — when you get there, actually fire component "
            "\"wizard\" action \"start-generation\" as this turn's action (after \"step-generate\"), "
            "narrating what's about to render — don't just mention generating and jump straight to "
            "step 10 in the same breath. The render takes several seconds; bridge it with a beat of "
            "narration or use the next turn. Only once the result has actually been shown is this "
            "outer step done — move into step 10 on the turn AFTER that, not the same one."
        ),
    ),
    WalkthroughStep(
        index=10,
        title="MLR tab",
        action={"page": "mlr-review", "component": "queue", "method": "highlight"},
        guidance=(
            "Show the MLR approvals queue and connect it back to what they just saw: content "
            "built in Content Studio arrives here already MLR-ready, so it moves through Brand, "
            "Medical, Legal, and Compliance review faster and with fewer bounce-backs. Just the "
            "queue — don't open a specific submission's detail panel here, that's an ask-only "
            "action, not part of this beat."
        ),
    ),
    WalkthroughStep(
        index=11,
        title="Content Library",
        action={"page": "content-library", "component": "grid", "method": "highlight"},
        guidance=(
            "A quick beat — land on the Content Library and say this is every video generated on "
            "the platform so far. Just the grid — don't open the preview modal on an item here, "
            "that's an ask-only action ('want to see one play?'), not part of this beat."
        ),
        max_words=24,
    ),
    WalkthroughStep(
        index=12,
        title="Settings — Integrations",
        action={"page": "settings-integrations", "component": "integrations", "method": "highlight"},
        guidance=(
            "A quick beat — land on Settings > Integrations and mention it connects into what "
            "they're already running (Veeva Vault PromoMats for MLR routing, Indegene Cortex for "
            "content supply chain). Just this one tab — don't tour Account, Billing, or Plans here; "
            "if pricing comes up they can ask and you'll pull up Plans separately."
        ),
        max_words=28,
    ),
    WalkthroughStep(
        index=13,
        title="Home wrap-up",
        action={"page": "home", "component": "insights", "method": "highlight"},
        guidance=(
            "This is the only Home stop in the tour — cover both the insight cards and the "
            "brand dossiers list here as the closing 'this is home base' moment. Wrap up the "
            "tour, ask if they have any other questions, and if question 5 (connecting with a "
            "rep for next steps) still hasn't come up, this is a natural moment to ask it. Set "
            "\"end_walkthrough\" once you've wrapped up."
        ),
    ),
]

WALKTHROUGH_STEPS_BY_INDEX = {s.index: s for s in WALKTHROUGH_STEPS}

# The canonical, ordered sub-action sequence for step 8/9's own internal
# wizard sub-navigation — mirrors the prose in each step's guidance above,
# but as real structured data runtime.py's _walkthrough_note can walk
# through to tell the model the exact next sub-action, rather than just
# listing what's already covered and trusting it to work out the complement
# itself. Real testing showed that inference step is exactly where this
# still went wrong even after already-covered ground truth was added: the
# model fired "step-brief" a second time (the wrong, already-done value)
# instead of "brief-brand-product" (the correct next one), specifically at
# the last Brief sub-part, twice in the same call. Giving the exact next
# value directly removes that inference step entirely — same "give ground
# truth, don't make it infer" fix as everywhere else in this file.
STEP_SUB_ACTIONS = {
    8: [
        "step-source",
        "select-source-dossier",
        "select-source-news",
        "select-source-custom",
        "step-brief",
        "brief-audience",
        "brief-voice-language",
        "brief-brand-product",
        "step-script",
        "generate-script",
        "step-scenes",
        "step-generate",
        "start-generation",
    ],
    9: [
        "step-brief",
        "generate-breakdown",
        "step-scenes",
        "step-options",
        "step-generate",
        "start-generation",
    ],
}

# The (page, component) every sub-action in STEP_SUB_ACTIONS actually lives
# on — NOT the same as WALKTHROUGH_STEPS_BY_INDEX[step].action, which is
# only the step's own LANDING action (step 9's is
# {"page": "magicavatar-studio", "component": "launchpad", ...}; its
# sub-actions target component "wizard" instead, same page). Read by
# runtime.py's _enforce_step_order so a corrected sub-action always lands on
# the right page too, not just the right method — see that function's own
# comment for the real call this was missing on (session 66da2724): the
# model proposed a MagicAvatar (step 9) sub-action while still naming
# "magicreel-studio" as the page, and the correction only fixed the method,
# producing a page+method combination that pointed at nothing real.
WIZARD_PAGE_BY_STEP: dict[int, tuple[str, str]] = {
    8: ("magicreel-studio", "wizard"),
    9: ("magicavatar-studio", "wizard"),
}


# Per-sub-beat narration for the two studio flows, replacing the single
# all-at-once block that used to live in steps 8 and 9's `guidance`.
#
# Keyed by the sub-action name already tracked in STEP_SUB_ACTIONS and
# already resolved to "the next one" by _walkthrough_note, so this needs no
# new state — it only changes how much of the script is visible per turn.
#
# Every constraint that mattered in the old prose is preserved, just attached
# to the beat it governs instead of being restated in a wall of text:
#   - the "step-source"/"step-brief" landing turns stay one-sentence
#     transitions, because their sub-parts each get explained a turn later
#     and a preview here just gets said twice
#   - "generate-script" and "start-generation" keep their own dedicated turn,
#     so the prospect actually sees the button press and the render
SUB_BEATS: dict[str, SubBeat] = {
    # ---- MagicReel (step 8) ----
    "step-source": SubBeat(
        "Landing on Source. One sentence only: name the stage and say it has a few options. "
        "Do NOT list or describe them — each gets its own turn next.",
        max_words=22,
    ),
    "select-source-dossier": SubBeat(
        "The brand dossier option: pulls the approved label, references and claims library. "
        "Say it's the usual starting point.",
    ),
    "select-source-news": SubBeat(
        "The news-article option: drop in a recent readout or approval and it builds from that angle.",
    ),
    "select-source-custom": SubBeat(
        "The custom-brief option: type your own angle. Then land back on the dossier, since that's "
        "what the rest of the flow uses.",
    ),
    "step-brief": SubBeat(
        "Landing on Brief. One sentence only: name the stage and say it has three parts. "
        "Do NOT describe them — each gets its own turn next.",
        max_words=22,
    ),
    "brief-audience": SubBeat(
        "Audience configuration: HCP or patient, and the journey stage. Say it tunes tone and reading level.",
    ),
    "brief-voice-language": SubBeat(
        "Voice and language: the voiceover, plus the 13 supported languages with subtitles and audio.",
    ),
    "brief-brand-product": SubBeat(
        "Brand and product: locks to the Brand Kit so claims, colours and logo stay on-brand automatically.",
    ),
    "step-script": SubBeat(
        "Landing on Script. One sentence: this is where structure and length get set, and the draft "
        "gets generated. Do not generate yet — that's the next turn.",
        max_words=26,
    ),
    "generate-script": SubBeat(
        "Fire the generate button as this turn's own action and narrate it briefly, e.g. "
        "'let's draft that script'. This turn exists so the press is actually seen.",
        max_words=24,
    ),
    "step-scenes": SubBeat(
        "The scene breakdown: narration and visual direction per scene, editable before rendering.",
    ),
    "step-generate": SubBeat(
        "Landing on Generate: pick the render tier. Do not fire the render yet — that's the next turn.",
        max_words=24,
    ),
    "start-generation": SubBeat(
        "Fire the render as this turn's own action and narrate what's coming, e.g. 'let's render it'. "
        "Only once the finished result is actually on screen is this step done.",
        max_words=26,
    ),
    # ---- MagicAvatar (step 9) ----
    "generate-breakdown": SubBeat(
        "Fire the breakdown generation as this turn's own action and narrate it briefly. "
        "This turn exists so the press is actually seen.",
        max_words=24,
    ),
    "step-options": SubBeat(
        "Options: render tier and background music for the piece.",
    ),
}


def sub_beat_for(action_name: Optional[str]) -> Optional[SubBeat]:
    """The narration for one sub-stage, or None if it has no scripted beat.

    Falls back to None rather than raising: a sub-action present in
    STEP_SUB_ACTIONS but missing here should degrade to the outer step's own
    guidance, not break the tour.
    """
    if not action_name:
        return None
    return SUB_BEATS.get(action_name)
