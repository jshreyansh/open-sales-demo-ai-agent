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
# Beat 1 fires no action: the prospect is already on the dashboard (session's
# default current_page) when the call starts, so the overview just talks —
# it's not a deliberate visit. The dashboard only gets one deliberate,
# explicit visit, as the final wrap-up (beat 10), not bookending the tour.
#
# Every action below already exists in registry.py's UI_REGISTRY — this
# feature needed no new registry actions and no frontend changes.
WALKTHROUGH_STEPS: List[WalkthroughStep] = [
    WalkthroughStep(
        index=1,
        title="Overview",
        action=None,
        guidance=(
            "Give a short, own-words 2-3 sentence overview of what ContentIQ does — pull from "
            "the product overview above, don't recite it verbatim. No navigation needed for "
            "this step, you're already on the dashboard — but don't frame that as a deliberate "
            "stop either (no \"let's start on the dashboard\" or \"I'll walk you through the "
            "dashboard first\") since nothing here actually gets toured or explained beyond this "
            "overview; the dashboard's own explicit, deliberate visit is step 10's wrap-up, not "
            "this one. Just give the overview and move straight into the tour."
        ),
    ),
    WalkthroughStep(
        index=2,
        title="Content Studio",
        action={"page": "content-studio", "component": "video-tab", "method": "click"},
        guidance=(
            "Land on Content Studio generally and mention it covers 30 formats across 5 Magic "
            "Engines — Video, Aid, Mail, Canvas, Doc. Don't click through every engine tab "
            "individually, just land here and describe it."
        ),
    ),
    WalkthroughStep(
        index=3,
        title="MagicReel pop-up",
        action={"page": "content-studio", "component": "magicreel", "method": "open"},
        guidance=(
            "Open a quick pop-up preview of MagicReel (short-form video) with a short beat of "
            "narration — don't linger, this is a glance, not the deep dive (that's beat 6)."
        ),
    ),
    WalkthroughStep(
        index=4,
        title="MagicAvatar pop-up",
        action={"page": "content-studio", "component": "magicavatar", "method": "open"},
        guidance=(
            "Open a quick pop-up preview of MagicAvatar (the digital-twin presenter video) with "
            "a short beat of narration — again, a glance, not the deep dive (that's beat 7)."
        ),
    ),
    WalkthroughStep(
        index=5,
        title="Infographic pop-up",
        action={"page": "content-studio", "component": "magicchart", "method": "open"},
        guidance=(
            "Open a quick pop-up preview of the Infographic format (component \"magicchart\") as "
            "your Magic Canvas example — a short beat of narration, then move on."
        ),
    ),
    WalkthroughStep(
        index=6,
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
            "after; a content preview here just gets said twice. Generate is a "
            "real, separate stage, not just something to mention while "
            "wrapping up — when you get there, actually fire component \"wizard\" action "
            "\"start-generation\" as this turn's action (after \"step-generate\" got you onto that "
            "stage), and let your reply narrate what's about to render, e.g. \"let's generate this\" "
            "— don't just talk about generating and jump straight to step 7 in the same breath, "
            "that skips the step entirely and the prospect never sees it render. The render itself "
            "takes several seconds — a short beat of narration bridging that wait is fine, or use "
            "the next turn once it's ready. Only once the result has actually been shown (the "
            "rendered reel, not just the button press) is this outer step done — move into step 7 "
            "on the turn AFTER that, not the same one."
        ),
    ),
    WalkthroughStep(
        index=7,
        title="MagicAvatar flow",
        action={"page": "magicavatar-studio", "component": "launchpad", "method": "open"},
        guidance=(
            "Open the MagicAvatar Launchpad, then start the Master wizard (create-master) and "
            "walk it end-to-end the same way as MagicReel — Brief, Scenes, Options, Generate — "
            "one stage at a time, same continuous active-walkthrough pacing as step 6. Generate is "
            "a real, separate stage here too — when you get there, actually fire component "
            "\"wizard\" action \"start-generation\" as this turn's action (after \"step-generate\"), "
            "narrating what's about to render — don't just mention generating and jump straight to "
            "step 8 in the same breath. The render takes several seconds; bridge it with a beat of "
            "narration or use the next turn. Only once the result has actually been shown is this "
            "outer step done — move into step 8 on the turn AFTER that, not the same one."
        ),
    ),
    WalkthroughStep(
        index=8,
        title="MLR tab",
        action={"page": "mlr-review", "component": "queue", "method": "highlight"},
        guidance=(
            "Show the MLR approvals queue and connect it back to what they just saw: content "
            "built in Content Studio arrives here already MLR-ready, so it moves through Brand, "
            "Medical, Legal, and Compliance review faster and with fewer bounce-backs."
        ),
    ),
    WalkthroughStep(
        index=9,
        title="Analytics tab",
        action={"page": "analytics", "component": "funnel", "method": "highlight"},
        guidance=(
            "Show the engagement funnel — Sent, Viewed, Played, Completed, Shared — how they'd "
            "track performance once content is live."
        ),
    ),
    WalkthroughStep(
        index=10,
        title="Dashboard wrap-up",
        action={"page": "dashboard", "component": "insights", "method": "highlight"},
        guidance=(
            "This is the only dashboard stop in the tour — cover both the insight cards and the "
            "active campaigns list here as the closing 'this is home base' moment. Wrap up the "
            "tour, ask if they have any other questions, and if question 5 (connecting with a "
            "rep for next steps) still hasn't come up, this is a natural moment to ask it. Set "
            "\"end_walkthrough\" once you've wrapped up."
        ),
    ),
]

WALKTHROUGH_STEPS_BY_INDEX = {s.index: s for s in WALKTHROUGH_STEPS}
