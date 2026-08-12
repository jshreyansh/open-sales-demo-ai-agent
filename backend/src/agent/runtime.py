import glob
import json
import os
import time
from datetime import datetime
from typing import AsyncIterator, Optional, TypedDict
from zoneinfo import ZoneInfo

import anthropic
from loguru import logger

from ..context.store import SessionState, HistoryEntry
from ..data import gate_log
from ..persona import AGENT_LOCATION, AGENT_NAME, AGENT_TIMEZONE
from .registry import PRODUCT_OVERVIEW, UI_REGISTRY, flatten_registry, FlatAction


def _load_knowledge() -> str:
    """Non-interactive knowledge (pricing, security, integrations, ...) — things
    the agent should know and reason with but that have no UI action behind
    them. Lives in markdown files under agent/knowledge/ so non-engineers can
    edit real content directly without touching this file. Loaded once at
    import time; add a new .md file there and it's picked up automatically,
    no code change needed."""
    knowledge_dir = os.path.join(os.path.dirname(__file__), "knowledge")
    parts = []
    for path in sorted(glob.glob(os.path.join(knowledge_dir, "*.md"))):
        with open(path, encoding="utf-8") as f:
            parts.append(f.read().strip())
    return "\n\n---\n\n".join(parts)


KNOWLEDGE = _load_knowledge()

_anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
_deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
_llm_provider = os.environ.get("LLM_PROVIDER", "").strip().lower()


def _pick_provider() -> Optional[str]:
    """LLM_PROVIDER ("anthropic" or "deepseek") forces a specific provider —
    for comparing Sonnet vs. DeepSeek head-to-head without having to blank
    out whichever key you're not testing. Left unset, this falls back to the
    original auto-detect: prefer Anthropic if that key exists, else
    DeepSeek. Naming a provider whose key isn't actually set falls back to
    auto-detect too rather than silently killing the LLM entirely — a
    forgotten key shouldn't take the whole agent down."""
    if _llm_provider == "anthropic" and _anthropic_key:
        return "anthropic"
    if _llm_provider == "deepseek" and _deepseek_key:
        return "deepseek"
    if _llm_provider in ("anthropic", "deepseek"):
        logger.warning(f"LLM_PROVIDER={_llm_provider!r} set but its API key is missing — falling back to auto-detect")
    if _anthropic_key:
        return "anthropic"
    if _deepseek_key:
        return "deepseek"
    return None


_provider = _pick_provider()

if _provider == "anthropic":
    _client = anthropic.Anthropic(api_key=_anthropic_key)
    _async_client = anthropic.AsyncAnthropic(api_key=_anthropic_key)
    _model = "claude-sonnet-5"
elif _provider == "deepseek":
    # DeepSeek's Anthropic-compatible endpoint — same SDK, same tool_use
    # protocol, just a different base_url/model/key. Falls back to the
    # keyword matcher below if this isn't set either.
    #
    # deepseek-v4-flash, not -pro: -pro defaults to "thinking mode", which
    # rejects a forced tool_choice ("Thinking mode does not support this
    # tool_choice") — confirmed by the actual 400 response, not guessed.
    _client = anthropic.Anthropic(api_key=_deepseek_key, base_url="https://api.deepseek.com/anthropic")
    _async_client = anthropic.AsyncAnthropic(api_key=_deepseek_key, base_url="https://api.deepseek.com/anthropic")
    _model = "deepseek-v4-flash"
else:
    _client = None
    _async_client = None
    _model = None

logger.info(f"agent runtime LLM: {_model or 'none (keyword-matcher fallback only — no API key found)'} (provider={_provider or 'auto/none'})")

FLAT_ACTIONS = flatten_registry(UI_REGISTRY)
TOOL_NAME = "demo_action"


class AgentAction(TypedDict):
    page: str
    component: str
    method: str


class AgentResult(TypedDict, total=False):
    reply: str
    action: AgentAction
    # Short transition spoken/shown right before the action fires (e.g. "Let
    # me pull that up") — present only when "action" is. See DEFAULT_LEAD_IN
    # and _select_with_claude for how this gets guaranteed non-empty.
    lead_in: str
    # Present only on the turn where the prospect just introduced themselves.
    # run_turn() consumes this to persist onto SessionState.prospect_name and
    # pops it before returning — internal bookkeeping, not part of the
    # response contract the frontend/voice side-channels see.
    prospect_name: str
    # Same pattern as prospect_name, one per MEDDIC field (see _MEDDIC_LABELS
    # below) — present only on the turn a given field is first captured,
    # popped and persisted onto SessionState by run_turn().
    meddic_metrics: str
    meddic_economic_buyer: str
    meddic_decision_criteria: str
    meddic_decision_process: str
    meddic_pain: str
    meddic_champion: str
    # Same pattern, one per qual_* field (see _QUAL_LABELS) — the 4 new
    # fields behind the 5-question qualification KPI beyond meddic_pain
    # (question 1) above.
    qual_current_solution: str
    qual_daily_users: str
    qual_past_attempts: str
    qual_next_step_response: str


DEFAULT_LEAD_IN = "Let me pull that up."


def _keyword_match(message: str) -> Optional[FlatAction]:
    import re

    tokens = [t for t in re.split(r"[^a-z0-9]+", message.lower()) if t]
    best: Optional[FlatAction] = None
    best_score = 0
    for action in FLAT_ACTIONS:
        score = sum(1 for t in tokens if t in action.keywords)
        if score > best_score:
            best_score = score
            best = action
    return best if best_score > 0 else None


def _fallback_reply(action: Optional[FlatAction]) -> AgentResult:
    if not action:
        return {
            "reply": "Ask me to show you something — the dashboard, content studio, or brand kit — and I'll walk you through it."
        }
    return {
        "reply": f"This is the {action.component_label}.",
        "action": {"page": action.page, "component": action.component, "method": action.method},
        "lead_in": DEFAULT_LEAD_IN,
    }


def _registry_prompt() -> str:
    lines = []
    for page in UI_REGISTRY:
        lines.append(f'Page "{page.id}" ({page.label}):')
        for c in page.components:
            actions = ", ".join(a.id for a in c.actions)
            lines.append(f'  - component "{c.id}" ({c.label}): {c.description} — actions: {actions}')
    return "\n".join(lines)


def _is_valid_action(action: AgentAction) -> bool:
    return any(
        a.page == action["page"] and a.component == action["component"] and a.method == action["method"]
        for a in FLAT_ACTIONS
    )


def _tool_schema() -> dict:
    """The single tool_use schema both _select_with_claude (blocking) and
    _stream_with_claude (streaming, see run_turn_stream) send — identical
    either way, so there's exactly one schema to keep in sync, not two.

    "action" and "lead_in" are defined BEFORE "reply", even though the
    conversation-facing docs/comments elsewhere describe reply first — this
    is deliberate and load-bearing for streaming, not arbitrary. Property
    order in a JSON Schema has no effect on validation (data.get() calls
    read fields by name regardless of order), but it does empirically
    influence the order a model fills fields in when constructing a tool
    call — and this order also matches the ALREADY-existing intended
    reasoning sequence in the system prompt (decide action → lead_in →
    fire it → THEN explain via reply). Putting action/lead_in first means
    that by the time reply's text starts streaming in, whether an action
    precedes it is already known — which is what lets run_turn_stream()
    safely start speaking reply's sentences as they arrive instead of
    waiting for the whole object to close. See _StreamingFieldExtractor
    and _stream_with_claude for how this gets used.
    """
    return {
        "name": TOOL_NAME,
        "description": "Reply to the prospect and, if relevant, trigger a UI action in the demo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "object",
                    "description": "Omit this field entirely if no listed component matches the request, or if you already did this action and the prospect is asking a follow-up question instead.",
                    "properties": {
                        "page": {"type": "string"},
                        "component": {"type": "string"},
                        "method": {"type": "string"},
                    },
                    "required": ["page", "component", "method"],
                },
                "lead_in": {
                    "type": "string",
                    "description": (
                        "Required whenever 'action' is set, omitted otherwise. A short (5-10 word) "
                        "spoken transition said right before the screen changes, e.g. 'Let me pull "
                        "that up' or 'Let's take a look at that.' No content or destination detail — "
                        "just the transition."
                    ),
                },
                "reply": {
                    "type": "string",
                    "description": (
                        f"Spoken as {AGENT_NAME}. One or two short sentences by default; longer only if "
                        "the prospect explicitly asked to elaborate/explain in detail. If 'action' is "
                        "set, this is spoken AFTER the screen has already changed, so it can talk about "
                        "what's now visible instead of what you're about to go look at."
                    ),
                },
                "prospect_name": {
                    "type": "string",
                    "description": (
                        "The prospect's first name — ONLY set this on the turn where they just told "
                        "you it for the first time (e.g. introducing themselves in response to the "
                        "opening question). Omit on every other turn."
                    ),
                },
                "meddic_metrics": {
                    "type": "string",
                    "description": "The concrete result/metric they're trying to move — ONLY set on the turn where this genuinely came up. See instruction 8.",
                },
                "meddic_economic_buyer": {
                    "type": "string",
                    "description": "Who owns budget / signs off on this purchase — ONLY set on the turn where this genuinely came up. See instruction 8.",
                },
                "meddic_decision_criteria": {
                    "type": "string",
                    "description": "What they're evaluating this against (other tools, internal criteria) — ONLY set on the turn where this genuinely came up. See instruction 8.",
                },
                "meddic_decision_process": {
                    "type": "string",
                    "description": "Steps/timeline to an actual decision — ONLY set on the turn where this genuinely came up. See instruction 8.",
                },
                "meddic_pain": {
                    "type": "string",
                    "description": "The real underlying problem driving this evaluation — ONLY set on the turn where this genuinely came up. See instruction 8.",
                },
                "meddic_champion": {
                    "type": "string",
                    "description": "Who internally wants this to happen / would advocate for it — ONLY set on the turn where this genuinely came up. See instruction 8.",
                },
                "qual_current_solution": {
                    "type": "string",
                    "description": (
                        "What they're ACTIVELY using right now to get by — even if informal. Test: "
                        "would they still say this today if asked 'how do you currently handle this'? "
                        "Example: 'We just email PDFs back and forth' -> current_solution. A single "
                        "'we use X' statement with no signal they've moved on from something else is "
                        "ONLY this field — do not also set qual_past_attempts from the same sentence. "
                        "ONLY set on the turn where this genuinely came up. See instruction 8."
                    ),
                },
                "qual_daily_users": {
                    "type": "string",
                    "description": (
                        "Who would actually use this day to day — specific roles or team, e.g. 'brand "
                        "managers and two MLR reviewers'. 'A few people' or 'the team' with no roles "
                        "named is too vague — leave unset and ask who specifically instead of capturing "
                        "a hedge. ONLY set on the turn where this genuinely came up. See instruction 8."
                    ),
                },
                "qual_past_attempts": {
                    "type": "string",
                    "description": (
                        "Something they TRIED, ADOPTED, OR EVALUATED BEFORE and moved away from — only "
                        "counts if they signal it's no longer what they use, or that it failed/was "
                        "rejected. Test: are they describing something in the past that isn't their "
                        "current answer? Example: 'We tried a generic DAM tool last year but dropped "
                        "it' -> past_attempts. Do NOT set this just because qual_current_solution "
                        "sounds inadequate — inadequacy alone isn't a past attempt, it needs an actual "
                        "prior/abandoned thing. ONLY set on the turn where this genuinely came up. See "
                        "instruction 8."
                    ),
                },
                "qual_next_step_response": {
                    "type": "string",
                    "description": (
                        "ONLY set on the turn you ask whether they'd like to connect with a rep for "
                        "next steps AND they give an actual answer — yes, no, or a real detail. A "
                        "deflection like 'maybe later' or 'I'll think about it' with no clear yes/no is "
                        "still worth capturing as-is (it IS their real answer) — just don't invent more "
                        "certainty than they actually gave. See instruction 8."
                    ),
                },
            },
            "required": ["reply"],
        },
    }


def _parse_tool_result(data: dict, stop_reason: Optional[str] = None) -> AgentResult:
    """Shared by both _select_with_claude (blocking) and _stream_with_claude
    (streaming, via its final authoritative parse) — the exact same
    field-validation/recovery logic either way, so there's one place this
    can go wrong, not two independently-maintained copies."""
    action = data.get("action")
    if action and not _is_valid_action(action):
        action = None

    reply = data.get("reply")
    if not reply:
        # Observed in production (DeepSeek): the model sometimes returns a
        # perfectly valid action + lead_in but omits "reply" entirely, even
        # though the schema marks it required. This used to be a hard
        # `data["reply"]` subscript, which raised a KeyError caught by
        # run_turn()'s broad except — silently discarding a CORRECT action in
        # favor of the crude keyword matcher (the actual cause of the
        # MagicReel/MagicAvatar -> MLR Approvals misfire). Recovering here
        # keeps the model's real navigation decision instead of throwing it
        # away.
        logger.warning(f"tool_use missing 'reply' (stop_reason={stop_reason!r}), recovering: {data!r}")
        if action:
            match = next(
                (a for a in FLAT_ACTIONS if a.page == action["page"] and a.component == action["component"]),
                None,
            )
            reply = f"This is the {match.component_label}." if match else "Here it is."
        else:
            reply = "Sorry, could you say that again?"

    # prospect_name, the six MEDDIC fields, and the 4 qual_* fields (question
    # 1 of the 5-question KPI is meddic_pain itself, see _qualification_note)
    # all follow the identical "only set on the turn it was just learned"
    # pattern — collected here in one pass rather than ten near-identical
    # if-blocks.
    captured_fields = {
        key: data[key]
        for key in ("prospect_name", *_MEDDIC_LABELS, *_QUAL_LABELS)
        if data.get(key)
    }

    if not action:
        result: AgentResult = {"reply": reply, **captured_fields}
        return result
    # Guaranteed non-empty even if the model forgets it — the ordering this
    # enables (transition, then action, then explanation) is the whole point;
    # a missing lead_in shouldn't silently fall back to the old "act instantly"
    # behavior.
    result: AgentResult = {
        "reply": reply,
        "action": action,
        "lead_in": data.get("lead_in") or DEFAULT_LEAD_IN,
        **captured_fields,
    }
    return result


SYSTEM_TEMPLATE = """You are {agent_name} — one of the best reps SwishX has, on a live call with someone evaluating ContentIQ, an AI content platform for pharma marketing teams. You sell the way top consultative reps actually sell: genuinely curious about the prospect's world before you pitch anything, confident without being pushy, and every single thing you show or say ties back to what THEY told you they care about — never a generic feature tour. Talk like a sharp, attentive person having a real conversation, not someone reading from a deck.

The prospect is currently on the "{current_page}" page. You work out of {agent_location} — right now, where you are, it's {current_time}. Use these if asked where you're based, or the time, date, or day — don't say you don't know, and don't guess somewhere else.

What the product actually does:

{overview}

Here is everything you're able to point at, click, and explain in the product right now — this is your product knowledge, use the descriptions to actually reason and answer with, not just to decide where to click:

{registry}

Non-interactive knowledge — pricing, security/compliance, integrations. Nothing here has a UI
action behind it, but it's just as real as the registry above — use it confidently, don't treat it
as off-limits:

{knowledge}

How to behave, in priority order:

0. Your opening line already offered a choice — walkthrough, or something specific first — don't repeat that offer, and don't turn the start of the call into a discovery interview by stacking multiple questions at once. If the prospect volunteers their name (or role/company) at any point, set the "prospect_name" field, acknowledge it naturally in a few words, and keep going with whatever they actually asked — don't make it its own detour.

1. If the prospect describes their own business problem, workflow, or use case (rather than asking to see a specific feature), your job is to *reason* about it: think about which of the capabilities above are actually relevant to what they described and explain specifically why — connect their situation to the product, don't just list features. Only trigger an action if showing something concrete would actually help make the point, and say what you're about to show before doing it. If nothing above is genuinely relevant to what they described, say so honestly instead of forcing a connection.
2. Listen for what's actually being asked. A follow-up question ("what kinds of X are there?", "why would I need that?", "how much does that cost?") is not a request to repeat an action you already did — it's a request for you to *explain*, using what you know. Only set "action" when the prospect is asking to see or be taken to something new.
2a. In Content Studio specifically, every one of the 30 formats (component ids like "magicsave", "magicdossier", etc, action "open") is a *more specific* match than its engine tab (component ids ending "-tab", action "click"). If the prospect describes something one specific format actually does — not just a category — you MUST use that format's "open" action, never the tab "click" action. Example: asked about co-pay cards, use {{"page": "content-studio", "component": "magicsave", "method": "open"}}, NOT the canvas-tab click. Only use a "-tab" click when they're asking to browse a whole category ("what video stuff do you have?") rather than one specific thing.
2b. Each Content Studio format's description ends with its real status. If it says "not yet built in this workspace", say so plainly and naturally (e.g. "that one's on the roadmap, not live yet") before or alongside describing it — don't imply something already exists when it's still coming soon.
2c. Only MagicReel and MagicAvatar have a real, walkable studio behind their format modal — the "magicreel-studio" and "magicavatar-studio" pages. Once the prospect wants to actually move past looking at the format's spec into building one ("let's make one", "walk me through it", "show me the actual flow"), use those pages' step actions instead of re-opening the format modal. Go one step at a time, in order (Source → Brief → Script → Scenes → Generate for MagicReel; Launchpad → Brief → Scenes → Options → Generate for MagicAvatar) — narrate what you're about to show before each jump, the same way a person walks someone through a tool rather than teleporting through it. Don't skip steps just to get to the end faster. End each step's explanation with a short, natural prompt inviting them to continue — "Does that sound good? Should I keep going?", "Want me to move to the next part?", "Ready to continue?" — then wait: only advance to the next step once they actually give a go-ahead ("yeah", "let's go", "next", "sounds good"). If their reply is a question or comment about the step you just showed instead, answer that and stay put — don't advance just because they said something. Every other format has no studio to enter yet — for those, the modal is as far as it goes.
2d. Every page has a "scroll" component ("down"/"up") for the page currently on screen. If the prospect asks you to scroll, or to see more of a long page (or less of it), use it — don't just describe what's further down instead of actually moving there.
2e. Whenever you set "action", also set "lead_in" — a short (5-10 word) spoken transition, e.g. "Let me pull that up," "Let's take a look," "One sec, pulling that up." Say it, THEN the screen changes, THEN "reply" — which can now talk about what's actually on screen ("So this is..."), not what you're about to go look at. Never put any actual content or explanation inside lead_in, and never describe the destination inside it either (no "let me show you the co-pay card format" — just "let me pull that up") — that's what tips this into feeling scripted instead of like someone genuinely reaching for the next screen. When there's no action, skip lead_in entirely.
3. Never repeat the exact same action back-to-back. Check the conversation history below — if you already highlighted or navigated to something and the prospect is still on the same topic, respond conversationally instead of re-triggering it. Scrolling is the one exception — repeated "scroll down" requests are expected and each should fire again. This also applies to firing several *different* actions back-to-back with no real go-ahead in between — e.g. clicking through every engine tab one after another just because the prospect said something. A short or ambiguous fragment ("on", "and", ".", "that") is not a go-ahead — it's very likely a stray STT fragment of something they were still saying, not a real instruction. When you're not sure whether they actually asked for the next thing, say so briefly and let them confirm, rather than guessing and moving the screen again.
4. When the prospect raises a doubt or objection — pricing hesitation, "we already use X for this," skepticism about a claim, or just a flatter/slower tone after something you said — don't immediately reassure and move on, and don't deflect to "ask me to show you something" unless you genuinely have nothing relevant to say. First acknowledge what they actually said in your own words so they feel heard, then ask one specific, genuine follow-up question that surfaces what's really behind it — what they're comparing it to, who else needs to sign off, which part of their workflow it actually touches — before you try to resolve it. That follow-up isn't stalling for its own sake: it's how a real rep finds out what to actually say instead of guessing, and it's a normal, expected part of a good sales conversation. Once you understand the real shape of the concern, answer it directly and specifically using what you know above — pricing, security/compliance, and integrations are answered from the knowledge above now, not deflected. Only say "I don't know, let me have someone follow up" for something genuinely outside everything above (e.g. contract terms, a specific SLA number, anything the knowledge itself says isn't certified/built yet) — and even then, be specific about what you don't know rather than a generic brush-off.
5. Vary your phrasing turn to turn. Don't reuse the same sentence template every time — talk the way a person actually talks in a real conversation. Vary lead_in the same way — don't say "let me pull that up" every single time.
6. Keep "reply" short by default — one to two sentences, spoken out loud on a call, not a written paragraph. Right length: "It's mainly built for pharma marketing teams — content that needs medical sign-off before it ships." Too long: stacking three or four features into one answer before pausing for them. Only go longer when the prospect explicitly asks you to elaborate, explain in more depth, or walk them through something step by step — then take the space that actually needs, still spoken naturally rather than as a dense block, and look for a natural place to pause and ask them something rather than monologuing straight through it. Shorter default replies also mean fewer chances for them to want to jump in mid-sentence, and leave more room for the questions in instruction 8.
7. Never invent a page, component, or method that isn't listed above.
8. Every call is scored against 5 required questions — this is a hard requirement, not optional color: (1) what problem brought them here, (2) how they solve it today, (3) who'd actually use this day to day, (4) what they've already tried, (5) whether they want to connect with a rep for next steps. Two priorities, in order — but they're not exclusive within a single reply: extracting something silently does NOT use up your only chance to also gather more. If the prospect's message contains a clean answer to one of these AND leaves a separate, genuine opening toward a different one, take both — capture the first silently, then still bridge to the second. Don't treat one successful silent capture as "enough for this turn" if a real second opening exists.

First, EXTRACT before you ASK — if the prospect's own words already clearly and specifically answer one of these (this happens often, especially question 1, when they explain why they're here at all), just capture it silently. Never spend a question on something they basically already told you. Before setting ANY of these fields, apply this test: could you quote back a specific, complete fact from what they actually said? If you'd have to hedge, fill in a blank, or guess ("a few people," "some tools," "not yet specified") — don't set the field. A vague gesture toward a topic is NOT a clean capture. Instead, treat that exact vagueness as your strongest possible opening: the topic is already live in the conversation, so one specific, natural follow-up right there continues the thread instead of switching topics — prioritize firming up something they've already half-answered over asking cold about something untouched.

Second, when something's genuinely still missing (or only half-answered per above), BRIDGE rather than interview: reflect back one clause of what they just said, then extend it into ONE open question that continues that exact thread — never a cold topic switch, never announced ("let me ask you a quick question"), never two qualifying questions back to back. For example, if they say "our claims review process is really slow, it delays every launch," a good bridge is "That review bottleneck sounds like it's hitting more than one launch — who's actually stuck doing that review day to day?" A cold topic switch ("Got it. Now, what have you tried to fix this?") or skipping the opening entirely to launch into a product pitch are both the failure mode to avoid. Their first substantive answer about their own situation is usually your single best opening for a bridge — look for it there before defaulting into a full walkthrough, not after.

Question 5 in particular must genuinely be asked before the call ends — unlike the other four, it's a question you have to ask, not something they'll volunteer, so watch for it specifically; see the qualification note below for exactly when to raise it. Beyond these 5, build a deeper picture opportunistically using MEDDIC: Metrics (the actual result they're trying to move), Economic Buyer (who owns budget / signs off), Decision Criteria (what they're evaluating this against), Decision Process (steps and timeline to a decision), Champion (who internally wants this to happen) — same extract-first, bridge-don't-interview approach, but these are bonus depth, not required. (Identify Pain isn't tracked separately — question 1 above already covers it.) Check the qualification note below before asking anything — it tracks exactly what's captured, what's missing, and how much runway you've had.
9. When the prospect clearly signals they want to move faster — "yes, show me", "send me the video", "I'm sold, what's next" — honor that immediately instead of continuing your own planned walkthrough. A direct request always overrides the default step-by-step order; this applies even mid-explanation, not just between turns.
10. Don't spread equal weight across every feature you know about. The two or three things worth repeating whenever they're relevant are: MLR-ready cinematic content, medically grounded claims, and content sourced straight from the brand's own dossier. Reach for these specifically when they connect to what the prospect cares about, rather than a flat, everything-gets-equal-airtime tour — deliberate repetition of a few real anchors is what actually sticks, not covering more ground.
11. Pace toward the call-length note below — it's a target for the whole conversation, not a hard cutoff mid-sentence. Running long is a signal to prioritize what they're actually asking over covering everything you could.
{interruption_note}{name_note}{company_note}{qualification_note}{pacing_note}
Full conversation so far:
{history}"""

INTERRUPTION_NOTE = (
    "\nThe prospect just cut you off mid-reply on the last turn — they didn't hear the rest of "
    "what you were saying. Don't assume they caught your full previous explanation; respond to "
    "what they're asking now, and only circle back to the cut-off point if it's still relevant. "
    "This changes nothing about whether to act — if what they're asking for now maps to something "
    "you can show them, set \"action\" (and \"lead_in\") exactly as you normally would. Recovering "
    "the conversation is not a reason to skip navigating.\n"
)


def _current_time_note() -> str:
    """Real wall-clock time in the persona's own timezone (see persona.py's
    AGENT_TIMEZONE) — computed fresh on every call, not cached, since a long
    call should see the clock actually move."""
    now = datetime.now(ZoneInfo(AGENT_TIMEZONE))
    return now.strftime("%A, %B %-d, %Y, %-I:%M %p %Z")


def _name_note(session: SessionState) -> str:
    if session.prospect_name:
        name = session.prospect_name
        return (
            f"\nThe prospect's name is {name} — use it naturally now and then, not every line. A "
            "confident, classic close pattern: after you've proposed something or checked in, end with "
            f"a warm tag question using their name — \"Sound good, {name}?\", \"Make sense, {name}?\", "
            f"\"That work for you, {name}?\" Sprinkle this in every few turns, not constantly — it should "
            "read as genuine rapport, not a verbal tic.\n"
        )
    return (
        "\nYou don't have the prospect's name yet. If they introduce themselves in their next message, "
        "capture it via the \"prospect_name\" field so you can use it going forward — don't force another "
        "ask if they've moved on without giving it.\n"
    )


def _company_note(session: SessionState) -> str:
    """Company/work email are captured once, up front, on Meeting Mode's
    pre-join screen (see server.py's /api/session/start) — this just makes
    that already-known fact visible to the prompt, the same way _name_note
    does for the name, so the agent never asks for it again."""
    if not session.company:
        return ""
    email_part = f", work email {session.work_email}" if session.work_email else ""
    return f"\nThe prospect works at {session.company}{email_part} — already known, don't ask for it again.\n"


_MEDDIC_LABELS = {
    "meddic_metrics": "Metrics",
    "meddic_economic_buyer": "Economic Buyer",
    "meddic_decision_criteria": "Decision Criteria",
    "meddic_decision_process": "Decision Process",
    "meddic_pain": "Identify Pain",
    "meddic_champion": "Champion",
}

# The 4 new fields behind the 5-question qualification KPI (see instruction
# 8) — question 1, "what problem brought them here," has no field of its
# own here; it's meddic_pain above, referenced directly in
# _qualification_note below instead of asking a second, near-identical
# question.
_QUAL_LABELS = {
    "qual_current_solution": "How they solve it today",
    "qual_daily_users": "Who'd use it day to day",
    "qual_past_attempts": "What they've already tried",
    "qual_next_step_response": "Connect with a rep for next steps",
}


def _qualification_note(session: SessionState) -> str:
    """See instruction 8 above — one unified note covering both halves: the
    5 required qualification questions (question 1 is meddic_pain itself)
    and the 4 bonus MEDDIC fields beyond them (pain excluded — question 1
    already covers it). Same "already captured, don't ask again" pattern as
    _name_note/_company_note, split into a required tier and an optional
    bonus tier so the agent can tell which is which.

    Escalation is turn-count-based, not wall-clock — a real call showed
    wall-clock time doesn't distinguish "8 rapid exchanges in 2 minutes"
    from "4 long exchanges over 20 minutes," and a single gate (the
    original design: nudge only past 7 elapsed minutes) meant nothing ever
    nudged the agent in most calls at all. Turn count directly measures how
    many chances the agent has actually had, so a fast short call and a
    slow long call both get pressure proportional to real missed
    openings, not the clock. Only the greeting itself (spoken before any
    real turn happens, via _greet()) is pressure-free — the first real
    reply already carries a soft nudge if nothing's captured yet, since a
    visit might only last a couple of turns and the whole point is
    gathering something even then. Escalates to a firmer nudge only if
    turns keep passing with nothing captured — still never a checklist,
    still one question at a time (matches instruction 0's "don't turn the
    opening into a discovery interview," which is about not stacking
    multiple questions at once, not about staying silent)."""
    required = {
        "1. What problem brought them here": session.meddic_pain,
        "2. How they solve it today": session.qual_current_solution,
        "3. Who'd use it day to day": session.qual_daily_users,
        "4. What they've already tried": session.qual_past_attempts,
        "5. Connect with a rep for next steps": session.qual_next_step_response,
    }
    bonus = {label: getattr(session, attr) for attr, label in _MEDDIC_LABELS.items() if attr != "meddic_pain"}

    req_captured = {k: v for k, v in required.items() if v}
    req_missing = [k for k, v in required.items() if not v]
    bonus_captured = {k: v for k, v in bonus.items() if v}
    bonus_missing = [k for k, v in bonus.items() if not v]

    lines = ["\nQualification profile so far:"]
    if req_captured:
        lines.append("Required questions (captured):")
        lines.extend(f"- {k}: {v}" for k, v in req_captured.items())
    if req_missing:
        lines.append(f"Required questions (still missing — must cover all 5 by call end): {', '.join(req_missing)}.")
    else:
        lines.append("All 5 required questions captured.")
    if bonus_captured:
        lines.append("Bonus MEDDIC (captured):")
        lines.extend(f"- {k}: {v}" for k, v in bonus_captured.items())
    if bonus_missing:
        lines.append(f"Bonus MEDDIC (optional, still missing): {', '.join(bonus_missing)}.")
    lines.append(
        "Don't re-ask anything captured above — and check first whether the prospect's own words "
        "already answer something still missing (see instruction 8's extraction-first rule) before "
        "spending a question on it."
    )

    current_turn = len(session.history) // 2
    turns_since_capture = current_turn - session.last_qual_capture_turn

    if current_turn >= 1:
        if req_missing:
            # Naming ONE specific target, not the whole missing list — a
            # concrete single target is what actually steers the next
            # reply's question; a passive list left the agent free to
            # default to a generic product-fit follow-up instead of one
            # that closes an actual tracked field (confirmed via real
            # testing). First missing item in question order is the
            # target — simple and predictable rather than another
            # judgment call for the model to make.
            target = req_missing[0]
            if turns_since_capture >= 3:
                lines.append(
                    f"Several turns have passed with nothing new captured — your next reply's "
                    f"follow-up should be aimed specifically at {target}: reflect back something "
                    f"they just said, then extend it into one open question toward exactly that "
                    f"(see instruction 8) — don't ask it cold."
                )
            elif turns_since_capture >= 1:
                lines.append(
                    f"Nothing's been captured yet on this thread — if your next reply has a "
                    f"natural opening (even a small one), aim it at {target} specifically rather "
                    f"than a generic follow-up. This applies from the very first reply on — don't "
                    f"wait for the conversation to build up first."
                )

        if not session.qual_next_step_response:
            if current_turn >= 6:
                lines.append(
                    "Question 5 (connecting with a rep for next steps) still hasn't come up and the "
                    "call has had plenty of turns — raise it naturally before the call ends, don't let "
                    "it slip."
                )
            else:
                lines.append(
                    "Question 5 (connecting with a rep) hasn't come up yet — it's fine early on, but if "
                    "the conversation reaches a natural satisfaction or wrap-up moment at ANY point, "
                    "ask it right then rather than waiting for a cue below."
                )

    return "\n".join(lines) + "\n"


def _pacing_note(session: SessionState) -> str:
    elapsed_min = (time.monotonic() - session.started_at) / 60
    return (
        f"\nThis call has been running about {elapsed_min:.0f} minute(s) so far. Ideal target for the "
        "whole conversation is around 10 minutes — not a hard stop, just a sense of how much runway is left.\n"
    )


def _select_with_claude(message: str, session: SessionState) -> AgentResult:
    if _client is None:
        raise RuntimeError("no client")

    # No truncation — session persistence should hold up like a real voice
    # chat's memory does, and each turn is short (spoken utterances in,
    # one-to-two-sentence replies out), so even a long consultative
    # conversation stays small in token terms.
    history = "\n".join(f"{h.role}: {h.text}" for h in session.history) or "(nothing yet — this is the first message)"

    system = SYSTEM_TEMPLATE.format(
        agent_name=AGENT_NAME,
        agent_location=AGENT_LOCATION,
        current_page=session.current_page,
        current_time=_current_time_note(),
        overview=PRODUCT_OVERVIEW,
        registry=_registry_prompt(),
        knowledge=KNOWLEDGE,
        interruption_note=INTERRUPTION_NOTE if session.was_interrupted else "",
        name_note=_name_note(session),
        company_note=_company_note(session),
        qualification_note=_qualification_note(session),
        pacing_note=_pacing_note(session),
        history=history,
    )

    msg = _client.messages.create(
        model=_model,
        # 300 was too tight: instruction 6 explicitly tells the model to write
        # longer replies when the prospect asks to elaborate, but the tool-call
        # JSON (reply + lead_in + action + prospect_name all competing for the
        # same budget) would get cut off mid-generation before "reply" finished
        # — confirmed via production logs, every "tool_use missing 'reply'"
        # recovery observed so far immediately followed the prospect explicitly
        # asking for more detail.
        max_tokens=700,
        system=system,
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": f'Prospect just said: "{message}"'}],
        tools=[_tool_schema()],
        tool_choice={"type": "tool", "name": TOOL_NAME},
    )

    tool_use = next((b for b in msg.content if b.type == "tool_use"), None)
    if tool_use is None:
        raise RuntimeError("no tool use in response")

    return _parse_tool_result(tool_use.input, msg.stop_reason)


def _begin_turn(session: SessionState, message: str) -> None:
    """Shared start-of-turn bookkeeping — logging the prospect's own message
    onto session history/gate_log before any reply is generated. Called
    exactly once per turn by whichever strategy run_turn() ends up using
    (run_turn itself, or run_turn_stream's streaming-with-fallback path) —
    never twice for the same turn, which is why run_turn_stream's own
    fallback-to-non-streaming branch does NOT call this again."""
    session.history.append(HistoryEntry(role="user", text=message))
    if session.visitor_id:
        gate_log.append_transcript_turn(session.visitor_id, "user", message)


def _finalize_turn(session: SessionState, result: AgentResult) -> AgentResult:
    """Shared end-of-turn bookkeeping — persisting anything the model just
    captured (prospect_name, MEDDIC fields, qualification fields) onto the
    session, updating current_page if an action fired, and logging the
    agent's reply. Shared by run_turn() and run_turn_stream() so this only
    exists in one place."""
    # Consumed for this turn's prompt already — clear so it doesn't leak
    # into a later, unrelated turn.
    session.was_interrupted = False

    prospect_name = result.pop("prospect_name", None)
    if prospect_name and not session.prospect_name:
        session.prospect_name = prospect_name

    # MEDDIC + qualification fields (see _MEDDIC_LABELS/_QUAL_LABELS) share
    # the identical "set once, on the turn it's learned" pattern — persisted
    # to gate_log immediately, the same "don't batch, write as you go"
    # approach already used for transcript turns below, so this data
    # survives a process restart or crash mid-call instead of living only in
    # this in-memory SessionState.
    for field_name in (*_MEDDIC_LABELS, *_QUAL_LABELS):
        value = result.pop(field_name, None)
        if value and not getattr(session, field_name):
            setattr(session, field_name, value)
            if session.visitor_id:
                gate_log.save_qualification_field(session.visitor_id, field_name, value)
            # len(history)//2 here equals the turn currently being
            # finalized (the agent's reply for it hasn't been appended
            # yet) — see _qualification_note's turn-count escalation,
            # which reads this to know how many turns have passed since
            # anything was last captured.
            session.last_qual_capture_turn = len(session.history) // 2

    if result.get("action"):
        session.current_page = result["action"]["page"]
    session.history.append(HistoryEntry(role="agent", text=result["reply"]))
    if session.visitor_id:
        gate_log.append_transcript_turn(session.visitor_id, "agent", result["reply"])
    return result


def run_turn(message: str, session: SessionState) -> AgentResult:
    _begin_turn(session, message)
    if _client is not None:
        try:
            result = _select_with_claude(message, session)
        except Exception:
            logger.exception("LLM call failed, falling back to keyword matcher")
            result = _fallback_reply(_keyword_match(message))
    else:
        result = _fallback_reply(_keyword_match(message))
    return _finalize_turn(session, result)


# ---------------------------------------------------------------------------
# Streaming turn — run_turn_stream(), used only by the voice pipeline
# (agent_processor.py) so TTS can start speaking "reply" as it's generated
# instead of waiting for the whole tool-call JSON object to finish. Text
# chat keeps using the plain run_turn() above, completely unchanged — a
# REST response has no equivalent benefit from this.
#
# The hand-rolled extractors below exist because a streaming tool call
# arrives as raw, not-yet-valid JSON text fragments (Anthropic's
# input_json_delta events) — standard json.loads() can't touch it until the
# whole object closes. They're scoped narrowly to this one known schema
# (find a specific key, decode its value) rather than a general streaming
# JSON parser, matching how this codebase already avoids adding a
# dependency for a narrow, well-understood need (see the typing-sound
# effect's ffmpeg shell-out, before it was removed).
#
# Only ever a speed optimization, never a second source of truth: the
# authoritative AgentResult always comes from the SDK's own final, fully
# guaranteed-correct parse (via stream.get_final_message()) once the stream
# ends — exactly the same parse _select_with_claude already does. If the
# incremental decode ever disagrees with that authoritative text, the
# mismatch is caught and the turn falls back to speaking the whole reply
# the old way (see run_turn_stream's done_streamed/done_fallback split)
# rather than trusting a possibly-corrupted fast path.
# ---------------------------------------------------------------------------


def _decode_json_string_prefix(s: str) -> tuple[str, bool]:
    """Decode as much of a JSON string's content as is unambiguously
    decodable from `s` (the raw text starting right after the value's
    opening quote — may be incomplete, may run past the closing quote if
    more has already arrived than one field's worth).

    Returns (decoded_text, closed) — closed is True once an unescaped
    closing quote was found. If `s` ends mid-escape-sequence (e.g. a lone
    trailing backslash, or a \\uXXXX cut short by a chunk boundary),
    decoding stops right before the incomplete escape rather than guessing
    — the next feed() call (see _StreamingFieldExtractor) will have more
    text and pick up from there via a fresh full redecode, which is safe
    since `s` only ever grows, never changes retroactively.

    Doesn't handle UTF-16 surrogate pairs for astral-plane characters
    (\\uD800-\\uDBFF + \\uDC00-\\uDFFF) — spoken sales-call replies aren't
    expected to contain them, and if one ever appears, the authoritative
    final parse (not this decoder) is still what actually gets spoken and
    logged; see the module note above.
    """
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '"':
            return "".join(out), True
        if c == "\\":
            if i + 1 >= n:
                break  # escape cut off by a chunk boundary -- wait for more
            nxt = s[i + 1]
            simple = {'"': '"', "\\": "\\", "/": "/", "n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
                continue
            if nxt == "u":
                if i + 6 > n:
                    break  # \uXXXX cut off by a chunk boundary -- wait for more
                try:
                    out.append(chr(int(s[i + 2 : i + 6], 16)))
                except ValueError:
                    break  # malformed escape -- stop; authoritative parse is still correct
                i += 6
                continue
            break  # unrecognized escape -- stop conservatively
        out.append(c)
        i += 1
    return "".join(out), False


class _StreamingFieldExtractor:
    """Incrementally decodes one known top-level string field's value (e.g.
    "reply" or "lead_in") out of a growing, still-invalid raw JSON buffer.
    Feed it raw text chunks as they arrive; it reports newly-decoded plain
    text since the last feed() call, becoming .closed once that field's
    value has fully arrived.

    Assumes the key appears at most once and searches for the literal
    `"<key>":` marker anywhere in the accumulated buffer — safe here because
    this schema's field names are all distinct and none of them nest inside
    another field's string value (the other fields are short, plain
    identifiers with no embedded quotes)."""

    def __init__(self, key: str):
        self._key_marker = f'"{key}"'
        self._raw = ""
        self._value_start: Optional[int] = None
        self._decoded = ""
        self._closed = False

    def feed(self, chunk: str) -> str:
        if self._closed:
            return ""
        self._raw += chunk
        if self._value_start is None:
            key_idx = self._raw.find(self._key_marker)
            if key_idx == -1:
                return ""
            i = key_idx + len(self._key_marker)
            while i < len(self._raw) and self._raw[i] in " \t\r\n":
                i += 1
            if i >= len(self._raw) or self._raw[i] != ":":
                return ""
            i += 1
            while i < len(self._raw) and self._raw[i] in " \t\r\n":
                i += 1
            if i >= len(self._raw) or self._raw[i] != '"':
                return ""  # opening quote hasn't arrived yet
            self._value_start = i + 1

        decoded, closed = _decode_json_string_prefix(self._raw[self._value_start :])
        new_text = decoded[len(self._decoded) :]
        self._decoded = decoded
        if closed:
            self._closed = True
        return new_text

    @property
    def started(self) -> bool:
        return self._value_start is not None

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def value(self) -> str:
        return self._decoded


class _BalancedObjectExtractor:
    """Finds a known top-level object field's raw JSON span (e.g.
    "action": {...}) once it's balanced-complete, tracking brace depth while
    respecting string boundaries so a literal "{" or "}" inside one of
    action's own string values (page/component/method — plain identifiers,
    but defensive here costs nothing) doesn't miscount. Once closed, the
    span is handed to json.loads() — this class only finds WHERE to cut,
    the actual parsing is still real, tested stdlib JSON parsing."""

    def __init__(self, key: str):
        self._key_marker = f'"{key}"'
        self._raw = ""
        self._span_start: Optional[int] = None
        self._depth = 0
        self._in_string = False
        self._escape_next = False
        self._closed = False
        self._value: Optional[str] = None

    def feed(self, chunk: str) -> None:
        if self._closed:
            return
        self._raw += chunk
        if self._span_start is None:
            key_idx = self._raw.find(self._key_marker)
            if key_idx == -1:
                return
            i = key_idx + len(self._key_marker)
            while i < len(self._raw) and self._raw[i] in " \t\r\n":
                i += 1
            if i >= len(self._raw) or self._raw[i] != ":":
                return
            i += 1
            while i < len(self._raw) and self._raw[i] in " \t\r\n":
                i += 1
            if i >= len(self._raw) or self._raw[i] != "{":
                return  # opening brace hasn't arrived yet
            self._span_start = i
            self._depth = 0

        # Resume scanning from wherever we last left off, not from the
        # start of the span every time -- unlike the string extractor above,
        # brace-depth/in-string state can't be safely recomputed from
        # scratch on a partial re-scan the same way (recomputing from the
        # start each call would be equally correct here too, just wasteful;
        # tracking a cursor is simple enough to do properly).
        start = getattr(self, "_scan_from", self._span_start)
        for idx in range(start, len(self._raw)):
            ch = self._raw[idx]
            if self._escape_next:
                self._escape_next = False
                continue
            if self._in_string:
                if ch == "\\":
                    self._escape_next = True
                elif ch == '"':
                    self._in_string = False
                continue
            if ch == '"':
                self._in_string = True
            elif ch == "{":
                self._depth += 1
            elif ch == "}":
                self._depth -= 1
                if self._depth == 0:
                    self._value = self._raw[self._span_start : idx + 1]
                    self._closed = True
                    self._scan_from = idx + 1
                    return
        self._scan_from = len(self._raw)

    @property
    def key_seen(self) -> bool:
        return self._span_start is not None

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def value(self) -> Optional[str]:
        return self._value


async def _stream_with_claude(message: str, session: SessionState) -> AsyncIterator[tuple]:
    if _async_client is None:
        raise RuntimeError("no async client")

    history = "\n".join(f"{h.role}: {h.text}" for h in session.history) or "(nothing yet — this is the first message)"
    system = SYSTEM_TEMPLATE.format(
        agent_name=AGENT_NAME,
        agent_location=AGENT_LOCATION,
        current_page=session.current_page,
        current_time=_current_time_note(),
        overview=PRODUCT_OVERVIEW,
        registry=_registry_prompt(),
        knowledge=KNOWLEDGE,
        interruption_note=INTERRUPTION_NOTE if session.was_interrupted else "",
        name_note=_name_note(session),
        company_note=_company_note(session),
        qualification_note=_qualification_note(session),
        pacing_note=_pacing_note(session),
        history=history,
    )

    action_extractor = _BalancedObjectExtractor("action")
    lead_in_extractor = _StreamingFieldExtractor("lead_in")
    reply_extractor = _StreamingFieldExtractor("reply")
    lead_in_and_action_handled = False

    async with _async_client.messages.stream(
        model=_model,
        max_tokens=700,
        system=system,
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": f'Prospect just said: "{message}"'}],
        tools=[_tool_schema()],
        tool_choice={"type": "tool", "name": TOOL_NAME},
    ) as stream:
        async for event in stream:
            if event.type != "content_block_delta" or event.delta.type != "input_json_delta":
                continue
            chunk = event.delta.partial_json

            action_extractor.feed(chunk)
            lead_in_extractor.feed(chunk)
            reply_new_text = reply_extractor.feed(chunk)

            if not lead_in_and_action_handled and lead_in_extractor.closed and (
                not action_extractor.key_seen or action_extractor.closed
            ):
                lead_in_and_action_handled = True
                if action_extractor.value:
                    try:
                        action_dict = json.loads(action_extractor.value)
                    except Exception:
                        action_dict = None
                    if action_dict and _is_valid_action(action_dict):
                        yield ("lead_in", lead_in_extractor.value)
                        yield ("action", action_dict)
                    # An action span that parsed but failed validation, or
                    # didn't parse at all, is treated as "no action" for
                    # streaming purposes too -- _parse_tool_result applies
                    # the exact same validation to the authoritative result,
                    # so the two can never disagree on whether an action
                    # actually fires.

            # Safe to start streaming reply's own text only once we know
            # for certain nothing needs to be said before it: either there's
            # a confirmed action+lead_in already spoken above, or "action"
            # never appeared in the buffer at all despite reply's own key
            # already having been found (meaning, given the reordered
            # schema, it never will -- see _tool_schema's docstring).
            reply_safe_to_stream = reply_extractor.started and (
                lead_in_and_action_handled or not action_extractor.key_seen
            )
            if reply_safe_to_stream and reply_new_text:
                yield ("reply_delta", reply_new_text)

    final_message = await stream.get_final_message()
    tool_use = next((b for b in final_message.content if b.type == "tool_use"), None)
    if tool_use is None:
        raise RuntimeError("no tool use in streamed response")
    result = _parse_tool_result(tool_use.input, final_message.stop_reason)

    # Only trust that reply's incremental text was genuinely fully spoken
    # already if the fast decoder actually reached a clean close AND agrees
    # exactly with the authoritative text -- see the module note above on
    # why a mismatch here means "don't trust it," not "patch the
    # difference."
    reply_fully_streamed = reply_extractor.closed and reply_extractor.value == result.get("reply")
    yield ("_reply_fully_streamed", reply_fully_streamed)
    yield ("result", result)


async def run_turn_stream(message: str, session: SessionState) -> AsyncIterator[tuple]:
    """Streaming counterpart to run_turn(), used only by the voice pipeline
    (agent_processor.py). Yields, in order:

      ("lead_in", str)              -- only if the turn triggers an action
      ("action", dict)              -- right after lead_in, same turn
      ("reply_delta", str)          -- zero or more, raw incremental text as
                                        "reply" streams in (NOT pre-split
                                        into sentences -- the caller already
                                        owns that pacing logic, see
                                        agent_processor.py's _speak_reply)
      ("done_streamed", AgentResult) -- reply's text was already fully
                                        covered by the reply_delta events
                                        above; nothing more needs speaking
      ("done_fallback", AgentResult) -- streaming wasn't available, failed,
                                        or couldn't be trusted end-to-end;
                                        the caller must speak this result's
                                        lead_in/action/reply the same way it
                                        always has, from scratch

    Exactly one of done_streamed/done_fallback is always the final event.
    _begin_turn() runs exactly once regardless of which path is taken, so
    the user's message is never double-logged."""
    _begin_turn(session, message)

    if _async_client is not None:
        try:
            reply_fully_streamed = False
            result: Optional[AgentResult] = None
            async for event in _stream_with_claude(message, session):
                if event[0] == "_reply_fully_streamed":
                    reply_fully_streamed = event[1]
                elif event[0] == "result":
                    result = event[1]
                else:
                    yield event
            if result is not None:
                final = _finalize_turn(session, result)
                if reply_fully_streamed:
                    yield ("done_streamed", final)
                else:
                    yield ("done_fallback", final)
                return
        except Exception:
            logger.exception("Streaming LLM call failed, falling back to non-streaming path")

    # Same fallback chain run_turn() itself uses -- deliberately NOT calling
    # run_turn() directly here, since that would call _begin_turn() a
    # second time for this same message.
    if _client is not None:
        try:
            result = _select_with_claude(message, session)
        except Exception:
            logger.exception("LLM call failed, falling back to keyword matcher")
            result = _fallback_reply(_keyword_match(message))
    else:
        result = _fallback_reply(_keyword_match(message))
    yield ("done_fallback", _finalize_turn(session, result))


def generate_call_summary(visitor_id: str) -> Optional[str]:
    """One focused, non-streaming LLM call summarizing a finished call for
    the admin dashboard — deliberately separate from the live run_turn/
    run_turn_stream path so it never adds cost or latency to an actual
    conversation. Called from two places: bot.py's on_client_disconnected
    (fire-and-forget, right when a call really ends, so a summary is
    normally already cached by the time an admin looks) and server.py's
    admin summary endpoint (on-demand fallback for the rare case nothing's
    cached yet). Returns None if there's no LLM configured or nothing to
    summarize — callers should just leave the summary uncached in that case
    rather than persisting a fabricated placeholder."""
    if _client is None:
        return None
    turns = gate_log.list_transcript(visitor_id)
    if not turns:
        return None
    transcript = "\n".join(f"{t['role']}: {t['text']}" for t in turns)
    try:
        msg = _client.messages.create(
            model=_model,
            # 400, not 150-words-worth (~200): DeepSeek's thinking mode is
            # disabled below the same way _select_with_claude disables it,
            # but leaves headroom regardless — confirmed via a real test
            # that omitting thinking={"type": "disabled"} here let a
            # thinking block eat into the budget before any summary text
            # was written at all, truncating it mid-sentence.
            max_tokens=400,
            system=(
                "Summarize this sales call transcript in under 150 words for a sales rep who "
                "wasn't on the call. Cover: what the prospect needed, what was shown/discussed, "
                "how qualified they seem, and any clear next step. Plain prose, no headers or "
                "bullet points."
            ),
            thinking={"type": "disabled"},
            messages=[{"role": "user", "content": transcript}],
        )
        text_block = next((b for b in msg.content if b.type == "text"), None)
        return text_block.text.strip() if text_block else None
    except Exception:
        logger.exception(f"Failed to generate call summary for visitor {visitor_id}")
        return None
