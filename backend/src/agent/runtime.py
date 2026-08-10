import glob
import os
import time
from datetime import datetime
from typing import Optional, TypedDict
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
    _model = "deepseek-v4-flash"
else:
    _client = None
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

0. Your opening line is already a short self-intro plus an open question ("what can I help you with?") — don't repeat it, and don't turn the start of the call into a discovery interview. If the prospect volunteers their name (or role/company) at any point, set the "prospect_name" field, acknowledge it naturally in a few words, and keep going with whatever they actually asked — don't make it its own detour.

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
8. Beyond the two mechanical questions (team vs. individual, time-to-value), build a real qualification picture over the course of the call using MEDDIC: Metrics (the actual result they're trying to move), Economic Buyer (who owns budget / signs off), Decision Criteria (what they're evaluating this against), Decision Process (steps and timeline to a decision), Identify Pain (the real problem driving this), Champion (who internally wants this to happen). Ask about ONE of these at a time, only when it genuinely fits what's already being discussed — never back-to-back, never announced ("let me ask a qualifying question"), never as a checklist. Check the MEDDIC note below before asking anything — if a field is already captured, don't ask again, use it to go one level deeper instead. Not every call will cover all six, and that's fine; a natural conversation beats a completed form.
9. When the prospect clearly signals they want to move faster — "yes, show me", "send me the video", "I'm sold, what's next" — honor that immediately instead of continuing your own planned walkthrough. A direct request always overrides the default step-by-step order; this applies even mid-explanation, not just between turns.
10. Don't spread equal weight across every feature you know about. The two or three things worth repeating whenever they're relevant are: MLR-ready cinematic content, medically grounded claims, and content sourced straight from the brand's own dossier. Reach for these specifically when they connect to what the prospect cares about, rather than a flat, everything-gets-equal-airtime tour — deliberate repetition of a few real anchors is what actually sticks, not covering more ground.
11. Pace toward the call-length note below — it's a target for the whole conversation, not a hard cutoff mid-sentence. Running long is a signal to prioritize what they're actually asking over covering everything you could.
{interruption_note}{name_note}{company_note}{meddic_note}{pacing_note}
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


def _meddic_note(session: SessionState) -> str:
    """See instruction 8 above — this is what lets the agent tell "already
    captured, don't ask again" from "still genuinely unknown" for each of
    the six MEDDIC fields, mirroring _name_note's pattern for a single field."""
    known = {label: getattr(session, attr) for attr, label in _MEDDIC_LABELS.items() if getattr(session, attr)}
    if not known:
        return "\nYou haven't captured any MEDDIC fields yet — see instruction 8, one at a time, when it naturally fits.\n"
    captured = "\n".join(f"- {label}: {value}" for label, value in known.items())
    missing = [label for attr, label in _MEDDIC_LABELS.items() if not getattr(session, attr)]
    missing_str = ", ".join(missing) if missing else "none — all six captured"
    return (
        f"\nMEDDIC captured so far:\n{captured}\nStill missing: {missing_str}. Don't re-ask what's "
        "already captured above — use it to go deeper instead.\n"
    )


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
        meddic_note=_meddic_note(session),
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
        tools=[
            {
                "name": TOOL_NAME,
                "description": "Reply to the prospect and, if relevant, trigger a UI action in the demo.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "reply": {
                            "type": "string",
                            "description": (
                                f"Spoken as {AGENT_NAME}. One or two short sentences by default; longer only if "
                                "the prospect explicitly asked to elaborate/explain in detail. If 'action' is "
                                "set, this is spoken AFTER the screen has already changed, so it can talk about "
                                "what's now visible instead of what you're about to go look at."
                            ),
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
                    },
                    "required": ["reply"],
                },
            }
        ],
        tool_choice={"type": "tool", "name": TOOL_NAME},
    )

    tool_use = next((b for b in msg.content if b.type == "tool_use"), None)
    if tool_use is None:
        raise RuntimeError("no tool use in response")

    data = tool_use.input
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
        logger.warning(f"tool_use missing 'reply' (stop_reason={msg.stop_reason!r}), recovering: {data!r}")
        if action:
            match = next(
                (a for a in FLAT_ACTIONS if a.page == action["page"] and a.component == action["component"]),
                None,
            )
            reply = f"This is the {match.component_label}." if match else "Here it is."
        else:
            reply = "Sorry, could you say that again?"

    # prospect_name plus the six MEDDIC fields all follow the identical
    # "only set on the turn it was just learned" pattern — collected here in
    # one pass rather than six near-identical if-blocks.
    captured_fields = {
        key: data[key]
        for key in ("prospect_name", *_MEDDIC_LABELS)
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


def run_turn(message: str, session: SessionState) -> AgentResult:
    session.history.append(HistoryEntry(role="user", text=message))
    if session.visitor_id:
        gate_log.append_transcript_turn(session.visitor_id, "user", message)

    if _client is not None:
        try:
            result = _select_with_claude(message, session)
        except Exception:
            logger.exception("LLM call failed, falling back to keyword matcher")
            result = _fallback_reply(_keyword_match(message))
    else:
        result = _fallback_reply(_keyword_match(message))
    # Consumed for this turn's prompt already — clear so it doesn't leak
    # into a later, unrelated turn.
    session.was_interrupted = False

    prospect_name = result.pop("prospect_name", None)
    if prospect_name and not session.prospect_name:
        session.prospect_name = prospect_name

    for field_name in _MEDDIC_LABELS:
        value = result.pop(field_name, None)
        if value and not getattr(session, field_name):
            setattr(session, field_name, value)

    if result.get("action"):
        session.current_page = result["action"]["page"]
    session.history.append(HistoryEntry(role="agent", text=result["reply"]))
    if session.visitor_id:
        gate_log.append_transcript_turn(session.visitor_id, "agent", result["reply"])
    return result
