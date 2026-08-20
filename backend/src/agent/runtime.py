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
from .walkthrough import STEP_SUB_ACTIONS, WALKTHROUGH_STEPS_BY_INDEX


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
    # Scripted platform walkthrough position (see walkthrough.py +
    # _walkthrough_note) — unlike the fields above, NOT "set once": the
    # model sets this every turn it moves position (start/advance/resume/
    # jump), and run_turn()'s _finalize_turn overwrites session.walkthrough_step
    # with it directly rather than only-if-unset.
    start_walkthrough: bool
    walkthrough_step: int
    end_walkthrough: bool
    walkthrough_awaiting_answer: bool
    # Set-once, like the MEDDIC/qual fields — see SessionState.farewell_question_asked
    # for why this needs to persist across turns instead of resetting.
    farewell_question_asked: bool
    # Internal only — never part of the response contract the frontend/voice
    # side-channels see. Set by _parse_tool_result when "reply" was missing
    # and recovered with a bare template; popped and consumed by
    # _maybe_backfill_reply/_maybe_backfill_reply_sync, which replace the
    # template with a real, narrow follow-up completion before any caller
    # ever sees the result.
    _reply_needs_backfill: bool


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


def _repair_action(action: AgentAction) -> Optional[AgentAction]:
    """Best-effort recovery for a tool_use action that fails _is_valid_action.

    Observed in production (DeepSeek): for certain wizard sub-step jumps, the
    model echoes the method name into "component" too — e.g.
    {"page": "magicreel-studio", "component": "step-brief", "method":
    "step-brief"} instead of the registry's real
    {"component": "wizard", "method": "step-brief"}. "page" and "method" are
    consistently the right ones in these cases; only "component" is wrong.
    Confirmed against real call logs, not guessed: the same exact shape
    (method value duplicated into component) recurred for several different
    wizard sub-steps in one session, always paired with a request that was
    otherwise completely unambiguous.

    Without this, the caller nulls the whole action out and falls back to a
    generic "no action, no reply" response — the worst possible answer for a
    request the model actually understood correctly.

    Only ever repairs when exactly one registry entry matches on (page,
    method) with the given component discarded — an ambiguous or empty match
    is left alone (returns None) rather than guessing, since a wrong guess
    here would be worse than the existing "no action" fallback.

    Called from both the streaming early-yield path and the final
    authoritative _parse_tool_result — see their call sites' comments for why
    they must never disagree on whether (and how) an action resolves."""
    if _is_valid_action(action):
        return action
    candidates = [
        a for a in FLAT_ACTIONS
        if a.page == action.get("page") and a.method == action.get("method")
    ]
    if len(candidates) != 1:
        return None
    fixed: AgentAction = {"page": action["page"], "component": candidates[0].component, "method": action["method"]}
    logger.warning(f"repairing malformed action (component {action.get('component')!r} -> {candidates[0].component!r}): {action!r}")
    return fixed


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
                "start_walkthrough": {
                    "type": "boolean",
                    "description": (
                        "Set true on ANY turn the prospect expresses wanting the platform tour — no "
                        "fixed phrasing required, just the intent. Real examples that all mean yes, "
                        "start it: 'sure, walk me through it', 'give me a walkthrough', 'give me a "
                        "whole walkthrough', 'yeah show me around', 'let's do the walkthrough', 'yes "
                        "please', 'walk me through everything', 'take me on the tour', or even a garbled/"
                        "unclear transcript where you can only infer they probably meant the tour — if "
                        "your own reply is going to say anything like 'let's do it' or 'sounds like you "
                        "mean a tour', set this too, don't let the field lag behind what you're already "
                        "about to say. This is a dedicated field specifically so this decision never gets "
                        "missed — decide it BEFORE writing \"reply\" below, not after, and set it "
                        "independently of whatever else you're doing this turn. Omit only when they are "
                        "NOT asking for the tour."
                    ),
                },
                "start_module_walkthrough": {
                    "type": "string",
                    "enum": ["magicreel", "magicavatar"],
                    "description": (
                        "Set this instead of \"start_walkthrough\" when the prospect wants a continuous, "
                        "self-driving, end-to-end build of ONE SPECIFIC format — not the whole platform "
                        "tour. Real examples: 'just show me how to make a MagicReel, not the whole "
                        "platform', 'walk me through MagicAvatar start to finish', or your own clarifying "
                        "question (see instruction 0c) getting answered with 'just the MagicReel one'. "
                        "This runs through the exact same auto-advancing steps as the full tour's own "
                        "MagicReel/MagicAvatar deep-dive (Source/Brief/Script/Scenes/Generate, or "
                        "Brief/Scenes/Options/Generate) — it just starts there directly and ends there, "
                        "without ever touching the rest of the platform (Content Studio overview, MLR, "
                        "analytics, dashboard). Do NOT use this for a quick one-off glance at a stage "
                        "('let's make one', with no request for the WHOLE flow, no urgency about seeing "
                        "it end to end) — that's instruction 2c's plain browsing, no field needed. Omit "
                        "on every other turn, including once the module walkthrough is already under way."
                    ),
                },
                "walkthrough_awaiting_answer": {
                    "type": "boolean",
                    "description": (
                        "Two-part check, run it BEFORE writing \"reply\", not after (same rule as "
                        "\"start_walkthrough\" above): (1) is this turn a REAL interruption mid-walkthrough "
                        "— a genuine question or new topic, not just an ack like 'okay' or 'cool'? (2) is "
                        "your \"reply\" about to end with a check-in question, OR are you asking them to "
                        "repeat something unclear (garbled transcript, didn't catch it)? If YES, set this "
                        "field true THIS turn — don't let it lag behind what you already decided to say. "
                        "Real examples: '...does that answer it, or should I keep going with the tour?', "
                        "'...want me to continue where we left off?', 'Sorry, could you say that again?'. "
                        "IMPORTANT — this is a ONE-TIME switch, not something you re-decide every turn: once "
                        "it's true, the system keeps the tour paused on its own through as many follow-up "
                        "questions as the prospect asks, even on turns where you omit this field entirely. "
                        "You do NOT need to keep setting it true again on every turn of a tangent — just "
                        "answer their questions naturally. The ONLY thing that lifts the pause is "
                        "\"resume_walkthrough\" (see below) being set on a later turn. Set this true only on "
                        "the turn the pause actually STARTS; omit it on every other turn, paused or not."
                    ),
                },
                "resume_walkthrough": {
                    "type": "boolean",
                    "description": (
                        "Set true on the EXACT turn the prospect gives a real go-ahead to pick the paused "
                        "walkthrough back up — 'let's continue', 'keep going', 'yes, continue the tour', "
                        "'back to the walkthrough', an unambiguous 'let's move on' after a run of questions. "
                        "This is the ONLY thing that lifts a pause started by \"walkthrough_awaiting_answer\" "
                        "— the pause otherwise holds through any number of follow-up questions, so don't set "
                        "this just because you answered something well or the conversation paused briefly; "
                        "only when they actually said something that means 'okay, let's get back to it.' "
                        "Once set, the next scripted beat picks up from your CURRENT step automatically — you "
                        "don't need to re-narrate it yourself this turn, a short acknowledgment is enough "
                        "(\"Sure, let's pick that back up.\"). If instead they ask to start over from the "
                        "beginning, that's \"start_walkthrough\" above, not this field. Omit on every other turn."
                    ),
                },
                "farewell_question_asked": {
                    "type": "boolean",
                    "description": (
                        "Set true on the exact turn your \"reply\" is about to ask a closing/qualifying "
                        "question (a MEDDIC/qualification question, or 'want me to connect you with a "
                        "rep') specifically because the prospect just indicated they're leaving or "
                        "ending the call soon ('I have to go', 'I'm out of time', 'gotta run', etc). "
                        "Decide this BEFORE writing \"reply\", same rule as \"start_walkthrough\" above. "
                        "This is a one-time-per-call flag: once it's already true (check the note in "
                        "the prompt above — it tells you plainly if this already happened), do NOT ask "
                        "ANOTHER question the next time they indicate leaving, even if it feels like a "
                        "clean opening — just give a short, warm goodbye with no question this time, and "
                        "omit this field entirely on that turn (it's already true, nothing to set). Two "
                        "closing questions across two separate 'I have to go' moments reads as not "
                        "listening, even though each one alone would've been reasonable."
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
                "walkthrough_step": {
                    "type": "integer",
                    "description": (
                        "Set this (1-10) to advance to the next step once the prospect has given a "
                        "go-ahead, to resume at your current step after answering an interruption, or "
                        "to jump straight to a step they specifically asked for. Do NOT use this to "
                        "start the walkthrough — that's \"start_walkthrough\" above, which always wins "
                        "on the turn it's true (this field is ignored that turn). This field ONLY tracks "
                        "position in the scripted 10-step platform tour (see the walkthrough note below, "
                        "which tells you plainly whether one is active) — it has nothing to do with "
                        "narrating your own progress through a studio wizard's internal steps (MagicReel's "
                        "Source/Brief/Script/Scenes/Generate, MagicAvatar's own steps, per instruction 2c). "
                        "Never set it there; it's silently ignored outside an active scripted tour anyway. "
                        "Omit on any turn that doesn't change your position in the actual scripted tour."
                    ),
                },
                "end_walkthrough": {
                    "type": "boolean",
                    "description": (
                        "Set true the turn the prospect declines to continue the walkthrough, once "
                        "you've wrapped up step 10, OR the prospect indicates they're leaving or ending "
                        "the call soon — 'I have to go', 'I have to drop', 'I'm out of time', 'gotta "
                        "run', etc. This last case is easy to miss because your own \"reply\" that turn "
                        "is a normal, warm goodbye rather than something that sounds like ending a tour "
                        "— set this anyway, in that same turn, decided BEFORE writing \"reply\" (same "
                        "rule as \"start_walkthrough\"/\"farewell_question_asked\" above). Forgetting it "
                        "here is the single biggest failure mode observed live: the prospect says "
                        "goodbye, you reply warmly, but without this field the auto-continue scheduler "
                        "has no idea the tour should stop and just keeps firing the next beat anyway — "
                        "on top of a goodbye that already happened, which reads as not listening at all. "
                        "If it turns out to be a false alarm and they keep talking, a fresh \"give me the "
                        "walkthrough\" request naturally restarts it via \"start_walkthrough\" — that's a "
                        "fine tradeoff against risking the tour steamrolling a real goodbye. Omit "
                        "otherwise."
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
    if action:
        action = _repair_action(action)

    reply = data.get("reply")
    reply_needs_backfill = False
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
            # A real bug in production (Dushyant, 2026-08-18): this bare
            # template is all that ever gets spoken when it happens — by the
            # time it's discovered here, action+lead_in are already spoken
            # live (see _stream_with_claude's incremental extractors), so a
            # full-turn retry risks a fresh reply contradicting what was just
            # said (the exact reason _consume_turn_stream never retries a
            # partially-spoken turn either). Marked here, backfilled by the
            # caller (see _maybe_backfill_reply/_maybe_backfill_reply_sync)
            # with a narrow follow-up asking ONLY for the missing reply text,
            # conditioned on the action+lead_in as already-settled fact —
            # this template stays the last-resort value if that also fails.
            reply_needs_backfill = True
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

    # Walkthrough position fields follow a different rule than the "set once"
    # fields above (they change every step, so 0/False are meaningful too,
    # not just falsy noise) — collected separately with an is-not-None/
    # explicit-key check rather than truthiness.
    if data.get("start_walkthrough"):
        captured_fields["start_walkthrough"] = True
    if data.get("start_module_walkthrough"):
        captured_fields["start_module_walkthrough"] = data["start_module_walkthrough"]
    if "walkthrough_step" in data and data["walkthrough_step"] is not None:
        captured_fields["walkthrough_step"] = data["walkthrough_step"]
    if data.get("end_walkthrough"):
        captured_fields["end_walkthrough"] = True
    # Only captured when true, same as start/end_walkthrough above — unlike
    # the old design, this is no longer reset to False every turn just
    # because the model omitted it (see SessionState.walkthrough_awaiting_answer
    # and _finalize_turn's sticky-pause logic): a pause the model starts on
    # one turn must survive every later turn where it doesn't re-mention this
    # field, since that's exactly what silently let the pause lapse mid-tangent
    # in production. "resume_walkthrough" is the only thing that clears it.
    if data.get("walkthrough_awaiting_answer"):
        captured_fields["walkthrough_awaiting_answer"] = True
    if data.get("resume_walkthrough"):
        captured_fields["resume_walkthrough"] = True
    # "Set once" like the MEDDIC/qual fields above (only captured when true —
    # see SessionState.farewell_question_asked for why this must never be
    # explicitly reset back to False by a later turn).
    if data.get("farewell_question_asked"):
        captured_fields["farewell_question_asked"] = True

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
    if reply_needs_backfill:
        result["_reply_needs_backfill"] = True
    return result


#
# The system prompt is split into a STATIC half (_STATIC_SYSTEM_TEMPLATE,
# below — role, product overview, registry, knowledge, all 12 numbered
# instructions) and a DYNAMIC half (_DYNAMIC_SYSTEM_TEMPLATE, further down —
# current page/time, the six per-turn notes, conversation history). The
# static half is ~50K chars and was being resent, unchanged byte-for-byte,
# on every single turn — Anthropic has to reprocess all of it from scratch
# each time with no caching, which measured out to 6-12s of dead air per
# turn in a real call (see the walkthrough-latency investigation). Splitting
# it out lets _build_system() below mark it as a single Anthropic
# prompt-cache breakpoint (cache_control: ephemeral) so repeat turns within
# the same call reuse the cached prefix instead of reprocessing it — this
# only helps because the static half is now genuinely static: no session
# state (current_page, current_time, notes, history) leaks into it anymore,
# which is exactly what would have busted the cache on every turn. DeepSeek
# gets the same two halves concatenated into one plain string, unaffected —
# cache_control is an Anthropic-only mechanism, only applied when
# _provider == "anthropic" (see _build_system).
STATIC_ROLE_INTRO = """You are {agent_name} — one of the best reps SwishX has, on a live call with someone evaluating SwishX, an AI content platform for pharma marketing teams. You sell the way top consultative reps actually sell: genuinely curious about the prospect's world before you pitch anything, confident without being pushy, and every single thing you show or say ties back to what THEY told you they care about — never a generic feature tour. Talk like a sharp, attentive person having a real conversation, not someone reading from a deck.

You work out of {agent_location}. If asked where you're based, say so confidently — don't say you don't know, and don't guess somewhere else.

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

0a. Any time the prospect expresses wanting the platform tour — in ANY phrasing, not just a fixed template, including a correction like "no, give me a WHOLE walkthrough" — set "start_walkthrough" true (see that field's own description for real example phrasings) and start it right there in this same reply: give a short, own-words 2-3 sentence overview of what SwishX does (pull from the product overview above, don't recite it verbatim), and set NO action this turn (you're already on the dashboard, nothing to click or highlight yet — but don't frame that as a deliberate stop either, no "let's start on the dashboard" or "I'll walk you through the dashboard first," since nothing here actually gets toured or explained beyond this overview; the dashboard's own explicit, deliberate visit is the tour's wrap-up step, not this one). From your NEXT reply onward, follow the walkthrough note below (which will now be populated) instead of freelancing your own navigation — it already covers what step 1 asked for, so don't repeat the overview, move straight into step 2. If they instead ask about something specific, answer that first per the instructions below — the walkthrough is opt-in, not the default path through the call.

0b. If the prospect asks to "continue"/"keep going with" the walkthrough and your own conversation history below already shows you delivering the full tour (something like "that wraps up the full tour" or reaching the dashboard as the final stop) — there's nothing left to continue TO. Don't just repeat the last step you showed again (confirmed live: this produced a near-duplicate of the exact same dashboard/Content-Studio paragraph you'd already just said). Instead say plainly that you've already covered the full platform, and ask what specifically they'd like to revisit or dig into. This does NOT apply when they explicitly ask to restart/redo the tour from the beginning ("give me the walkthrough from the start," "start over") — that's a genuine fresh pass, set "start_walkthrough" true and actually deliver it same as always; the distinction is a vague "continue" with nowhere left to go versus an explicit request for a new full pass.

0c. If the prospect asks for a continuous, guided, end-to-end build of ONE SPECIFIC format — "show me the whole MagicReel flow," "walk me through MagicAvatar start to finish," "how do I make a MagicReel" — and it's genuinely unclear whether they also want the broader platform tour, ask a quick clarifying question first: "Want the whole platform walkthrough, or just [format] end-to-end?" — set no action and no walkthrough field this turn, just ask and wait. If they answer with the module ("just MagicReel," "the MagicReel one," "not the whole platform"), set "start_module_walkthrough" on that next turn. If their ORIGINAL ask was already unambiguous about wanting just the one format — your exact scenario: "just show me MagicReel, not the whole platform" — skip the clarifying question entirely and set "start_module_walkthrough" right away. Once running, it uses the exact same continuous, self-driving pacing as the full tour's own MagicReel/MagicAvatar deep-dive (see the walkthrough note below) — the only difference is it ends when that one format is done instead of continuing into the rest of the platform. This is different from a quick one-off "let's make one" with no request to see the WHOLE thing end-to-end — that's ordinary browsing (instruction 2c), no field needed.

1. If the prospect describes their own business problem, workflow, or use case (rather than asking to see a specific feature), your job is to *reason* about it: think about which of the capabilities above are actually relevant to what they described and explain specifically why — connect their situation to the product, don't just list features. Only trigger an action if showing something concrete would actually help make the point, and say what you're about to show before doing it. If nothing above is genuinely relevant to what they described, say so honestly instead of forcing a connection.
2. Listen for what's actually being asked. A follow-up question ("what kinds of X are there?", "why would I need that?", "how much does that cost?") is not a request to repeat an action you already did — it's a request for you to *explain*, using what you know. Only set "action" when the prospect is asking to see or be taken to something new.

2z. Speech-to-text sometimes hands you a transcript that's fragmentary, garbled, or just a stray name/word with no real content (e.g. "Can you show me, Vê?" or "I want to see the magic real lot"). If you genuinely can't tell what they're asking for — not just an unusual phrasing you can still reason through, but actually unclear — don't guess at an action or force an answer onto the nearest topic. Say so plainly and ask them to repeat it ("Sorry, I didn't quite catch that — could you say it again?"), set no "action" this turn, and wait for their next turn instead. If a scripted walkthrough is active when this happens, this counts as a real interruption — set "walkthrough_awaiting_answer" true the same way instruction 2c and the walkthrough note describe, so the tour actually stays paused until they've had a chance to clarify, instead of the next scripted beat firing on top of an unresolved "could you repeat that."
2a. In Content Studio specifically, every one of the 30 formats (component ids like "magicsave", "magicdossier", etc, action "open") is a *more specific* match than its engine tab (component ids ending "-tab", action "click"). If the prospect describes something one specific format actually does — not just a category — you MUST use that format's "open" action, never the tab "click" action. Example: asked about co-pay cards, use {{"page": "content-studio", "component": "magicsave", "method": "open"}}, NOT the canvas-tab click. Only use a "-tab" click when they're asking to browse a whole category ("what video stuff do you have?") rather than one specific thing.
2b. Each Content Studio format's description ends with its real status. If it says "not yet built in this workspace", say so plainly and naturally (e.g. "that one's on the roadmap, not live yet") before or alongside describing it — don't imply something already exists when it's still coming soon.
2c. Only MagicReel and MagicAvatar have a real, walkable studio behind their format modal — the "magicreel-studio" and "magicavatar-studio" pages. Once the prospect wants to actually move past looking at the format's spec into building one ("let's make one", "walk me through it", "show me the actual flow"), use those pages' step actions instead of re-opening the format modal. Go one step at a time, in order (Source → Brief → Script → Scenes → Generate for MagicReel; Launchpad → Brief → Scenes → Options → Generate for MagicAvatar) — narrate what you're about to show before each jump, the same way a person walks someone through a tool rather than teleporting through it. Don't skip steps just to get to the end faster. Every other format has no studio to enter yet — for those, the modal is as far as it goes. This plain, one-step-at-a-time browsing is for a quick "let's make one" with no urgency about seeing the WHOLE thing — if instead the prospect wants the continuous, guided, end-to-end build with nothing stopping in between, that's instruction 0c's "start_module_walkthrough" instead, which self-drives through these same steps automatically.

This has two different pacing rules depending on how you got here. Standalone (the prospect asked to build one outside any scripted walkthrough): end each stage's explanation with a short, natural prompt inviting them to continue — "Does that sound good? Should I keep going?", "Want me to move to the next part?", "Ready to continue?" — then wait: only advance to the next stage once they actually give a go-ahead ("yeah", "let's go", "next", "sounds good"). If their reply is a question or comment about the stage you just showed instead, answer that and stay put — don't advance just because they said something. During an active scripted walkthrough (the walkthrough note below shows you on step 6 or 7), use that same continuous auto-advancing pacing instead — keep moving stage to stage on your own without waiting for a go-ahead, exactly like the rest of the tour, and only actually pause for a genuine question (see the walkthrough note's interruption rule, including setting "walkthrough_awaiting_answer"). Once that pause starts, it holds through however many follow-up questions the prospect asks — you don't need to keep re-setting the field on every turn of the tangent, just answer naturally; only set "resume_walkthrough" once they actually say something that means "let's continue," which is what starts the tour moving again. Either way, don't name or preview the NEXT stage inside the CURRENT stage's "reply" (no "let's move on to the brief next" tacked onto the end of the Source stage's explanation) — that announcement belongs solely to "lead_in" on the turn you actually jump there. Saying it in both places back to back is the one thing to avoid; wrap up this stage's own content and stop.
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
12. This is a sandbox for evaluating and exploring the product's flow, not a live generation pipeline — most of what you show is a pre-loaded example, not something actually produced from what the prospect said. Selecting a tier (HD/Cinematic) is real and does change what's shown. Nothing else does: a dossier, audience, voice, language, script structure, or any other option the prospect names doesn't actually switch what's on screen — it stays on whatever's already pre-loaded there, regardless of which method you fire. When the prospect names or asks for a specific one of these, never claim you switched to it — that's a lie the prospect can see disproven on their own screen. Instead, acknowledge what they said by name, then connect it to the pre-loaded example naturally ("since you're thinking cardiology, this pre-loaded example is actually in that same space, so it's a good one to walk through") — sound confident and natural doing this, not like you're apologizing for a limitation.
13. If the prospect explicitly pushes for real, live generation of a video or image from scratch — not just walking through a flow, but actually asking you to make one right now — don't pretend to generate it and don't run a wizard flow to a fake result for this. Explain plainly that this meeting is for evaluating and exploring the product's flows, that you can't generate directly here, but you can show them numerous real examples to browse — then fire component "example-gallery" action "open" (page "meeting"). Mention that for a real platform showcase with actual generation, they can book time with a human-led session, and that you're sending the link in the chat now.

14. When the prospect asks to be connected with the team, to book a meeting, or to talk to a human: ASK FIRST, then act. Say something like "want me to open the booking portal so you can pick a time?" and set no action on that turn — you're asking, not doing. Only if they actually say yes on the NEXT turn, fire component "booking-portal" action "open" (page "meeting"), which opens the scheduling page in a separate browser tab so this call keeps running. If they say no, or want to just leave it with you, don't fire it — take their email and say the team will reach out. Never open the tab without that explicit yes: a tab opening unasked mid-call is startling, and it's the one action here that leaves the meeting screen."""

# Rendered ONCE at import time into a plain string constant — never
# reformatted per-request — so the exact same bytes go out on every call,
# which is what makes the Anthropic cache breakpoint in _build_system()
# below actually hit instead of missing on some incidental formatting
# difference. AGENT_NAME/AGENT_LOCATION/PRODUCT_OVERVIEW/_registry_prompt()/
# KNOWLEDGE are all compile-time constants (no session state), which is
# exactly what makes this safe to render once instead of per-turn.
STATIC_SYSTEM_PROMPT: str = STATIC_ROLE_INTRO.format(
    agent_name=AGENT_NAME,
    agent_location=AGENT_LOCATION,
    overview=PRODUCT_OVERVIEW,
    registry=_registry_prompt(),
    knowledge=KNOWLEDGE,
)

# Only the parts that genuinely change turn to turn: current page/time, the
# six per-turn notes, and conversation history. Everything else lives in
# STATIC_ROLE_INTRO above.
_DYNAMIC_SYSTEM_TEMPLATE = """The prospect is currently on the "{current_page}" page. Right now, where you are, it's {current_time}. Use this if asked the time, date, or day — don't say you don't know, and don't guess somewhere else.
{interruption_note}{name_note}{company_note}{qualification_note}{walkthrough_note}{farewell_note}{pacing_note}
Full conversation so far:
{history}"""


def _build_system(session: SessionState) -> "str | list[dict]":
    """Builds the full system prompt for one turn, split so the ~50K-char
    static half (STATIC_SYSTEM_PROMPT) can be cached instead of reprocessed
    on every call. Anthropic-only: cache_control is an Anthropic API
    mechanism, so DeepSeek (or any other provider) gets the two halves
    concatenated into one plain string, identical in content to what it
    always received, just structurally different in how it's packaged."""
    dynamic = _DYNAMIC_SYSTEM_TEMPLATE.format(
        current_page=session.current_page,
        current_time=_current_time_note(),
        interruption_note=INTERRUPTION_NOTE if session.was_interrupted else "",
        name_note=_name_note(session),
        company_note=_company_note(session),
        qualification_note=_qualification_note(session),
        walkthrough_note=_walkthrough_note(session),
        farewell_note=_farewell_note(session),
        pacing_note=_pacing_note(session),
        history="\n".join(f"{h.role}: {h.text}" for h in session.history) or "(nothing yet — this is the first message)",
    )
    if _provider == "anthropic":
        return [
            {"type": "text", "text": STATIC_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": dynamic},
        ]
    return f"{STATIC_SYSTEM_PROMPT}\n\n{dynamic}"


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
            f"\nThe prospect's name is {name}. Use it RARELY — roughly once every 4-5 of your replies "
            "at most, never in back-to-back turns, and never just to soften an ordinary sentence "
            f"(\"Great question, {name}\", \"Absolutely, {name}\", \"So this is {name}...\" are the "
            "pattern to avoid — confirmed from a real call where nearly every single reply used it, "
            "which reads as a verbal tic, not warmth). Save it for one deliberate moment: a "
            "confident, classic close pattern, after you've proposed something or checked in, ending "
            f"with a warm tag question — \"Sound good, {name}?\", \"Make sense, {name}?\", \"That work "
            f"for you, {name}?\" Most of your replies should have no name in them at all.\n"
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


def _walkthrough_note(session: SessionState) -> str:
    """Mirrors _qualification_note's shape: grounds the model in exactly
    where it is in the scripted platform walkthrough (see walkthrough.py),
    since relying on the model to reconstruct its own multi-turn position
    from prose alone is exactly what caused drift (skipped/reordered steps)
    in earlier, looser prompt-only designs this session. Returns "" when no
    tour is active — nothing to ground.

    Also surfaces session.walkthrough_awaiting_answer as ground truth when
    true, rather than leaving "is this a resume moment" to the model's own
    judgment from conversation history — that used to be this function's
    design (see git history), but real testing showed the model reliably
    advances "walkthrough_step" on a plain go-ahead (its own field
    description already justifies that alone) without ALSO setting the
    separate "resume_walkthrough" field needed to actually clear the pause,
    since nothing told it a pause was even in effect. Confirmed live: three
    separate "continue the walkthrough" turns in a row each correctly
    advanced the step number, but never once set "resume_walkthrough" —
    leaving the pause stuck for the rest of the call, permanently disabling
    auto-continue. Same fix as everywhere else in this file: give the model
    the actual current state, don't make it infer one."""
    step = WALKTHROUGH_STEPS_BY_INDEX.get(session.walkthrough_step) if session.walkthrough_step else None
    if step is None:
        return ""

    action_line = (
        f'Action for this step: {{"page": "{step.action["page"]}", "component": "{step.action["component"]}", "method": "{step.action["method"]}"}}.'
        if step.action
        else "No action for this step — just talk, don't navigate."
    )
    # A module-scoped walkthrough (see start_module_walkthrough) is capped
    # at walkthrough_scope_end — once reached, there IS no "next step" as
    # far as this run is concerned, even though a numerically higher step
    # genuinely exists in the full platform list. Without this check the
    # model would be told "next step is MLR/analytics/etc", which is
    # exactly the platform-wide continuation a scoped "just MagicReel"
    # request was meant to avoid.
    at_scope_end = session.walkthrough_scope_end is not None and step.index >= session.walkthrough_scope_end
    next_step = WALKTHROUGH_STEPS_BY_INDEX.get(step.index + 1) if not at_scope_end else None
    if next_step:
        next_action_line = (
            f'{{"page": "{next_step.action["page"]}", "component": "{next_step.action["component"]}", "method": "{next_step.action["method"]}"}}'
            if next_step.action
            else "no action for that step — just talk, don't navigate"
        )
        next_line = (
            f'Once step {step.index} is fully delivered, the next step is step {next_step.index} — '
            f'"{next_step.title}." When you advance to it, its action is: {next_action_line}. Its guidance: '
            f'{next_step.guidance}'
        )
    elif session.walkthrough_scope_end is not None:
        next_line = (
            "This is a module-scoped walkthrough (just this one format, not the whole platform) — "
            "once this step is fully delivered, that's the whole thing done. Wrap up and set "
            "\"end_walkthrough\" — don't advance into any other platform section (Content Studio "
            "overview, other formats, MLR, analytics, dashboard) unless the prospect explicitly asks "
            "for more after this."
        )
    else:
        next_line = "This is the final step — wrap up and set \"end_walkthrough\" once done."
    # Full title->index table, always shown — without this, a skip-ahead
    # request ("jump to the MLR tab") makes the model guess or count its way
    # to a step number instead of reading it, and real testing showed that
    # guess can land one off (firing the right action but reporting the
    # wrong index), which then desyncs every step after it. Same fix as the
    # rest of this file: give the model the lookup table, don't make it infer
    # one.
    full_list = "; ".join(f"{s.index}={s.title}" for s in WALKTHROUGH_STEPS_BY_INDEX.values())

    paused_line = (
        "\nTHE TOUR IS CURRENTLY PAUSED (a real interruption or unclear-transcript moment set this "
        "earlier) — it stays paused through however many questions the prospect asks, and the "
        "system will NOT auto-advance on its own while this holds, no matter how long the pause "
        "lasts. Keep answering their questions normally. The MOMENT their message is a real "
        "go-ahead to pick the tour back up (\"let's continue\", \"keep going\", \"yeah, continue the "
        "walkthrough\", etc.) — set \"resume_walkthrough\" true on that exact turn, IN ADDITION TO "
        "whatever \"walkthrough_step\"/action you're already setting to actually deliver that step's "
        "content. Advancing \"walkthrough_step\" alone is not enough and will NOT lift the pause — "
        "without \"resume_walkthrough\" also set, the tour stops auto-advancing on its own for the "
        "rest of the call even though you're still answering 'continue' requests turn by turn.\n"
        if session.walkthrough_awaiting_answer
        else ""
    )
    position_line = (
        f'You\'re currently giving a module-scoped walkthrough — just "{step.title}" end-to-end, '
        f"not the whole platform tour: "
        if session.walkthrough_scope_end is not None
        else f"You're currently giving the scripted platform walkthrough — step {step.index} of 10: "
    )
    # Ground truth for step 6/7's own internal "have I already fired
    # start-generation" state — see SessionState.walkthrough_generate_fired.
    # Without this, the model has no explicit signal that it already kicked
    # off the render and reliably keeps re-narrating/re-firing it under
    # auto-continue's rapid, unattended pacing instead of wrapping up —
    # confirmed live, 3 separate auto-continue beats in a row each fired
    # "start-generation" again, narrated as if for the first time.
    generate_fired_line = (
        (
            "\nYou ALREADY fired \"start-generation\" for this step earlier in this same run — do "
            "NOT fire it again and don't re-narrate \"kicking off the render\"/\"here it goes\"/"
            "\"firing off the render\" as if for the first time. If you haven't yet shown the actual "
            "rendered result to the prospect, do that now, briefly — the fake render only takes a "
            "few seconds, so if it's not ready yet, bridge with one short line, not another render "
            "narration. Once the result has been shown, this step is done: "
            + (
                "set \"end_walkthrough\" now (this is a module-scoped walkthrough)."
                if session.walkthrough_scope_end is not None
                else f"advance \"walkthrough_step\" to {step.index + 1} now."
            )
            + "\n"
        )
        if step.index in (6, 7) and session.walkthrough_generate_fired
        else ""
    )
    # Ground truth for step 6/7's own internal sub-navigation (step-source,
    # select-source-*, step-brief, brief-*, step-script, ...) — see
    # SessionState.walkthrough_fired_actions and walkthrough.py's
    # STEP_SUB_ACTIONS. Same reasoning as generate_fired_line above,
    # generalized: without this, the model has no explicit signal for which
    # of these it already fired and reliably re-fires/re-narrates one under
    # auto-continue's rapid, unattended pacing — confirmed live, "step-brief"
    # fired 3 separate times across 3 auto-continue beats, each re-narrating
    # the Brief step's intro (and re-covering sub-parts already delivered) as
    # if for the first time.
    #
    # Listing "already covered" alone (an earlier version of this) wasn't
    # enough on its own — confirmed live, the model still fired "step-brief"
    # a SECOND time (the wrong, already-done value, with a hallucinated
    # extra "method_note" field) instead of "brief-brand-product" (the
    # correct next one), specifically at the last Brief sub-part, twice in
    # the same call. Computing and stating the exact next value removes
    # that inference step entirely instead of trusting the model to work
    # out the complement of a list itself.
    #
    # Excludes "start-generation" from the "already covered" list, which
    # generate_fired_line above already covers with its own stronger wording
    # (forcing wrap-up on a repeat) — but it's left in STEP_SUB_ACTIONS so
    # it still shows up correctly as "the next one" once everything else is
    # done.
    sub_actions = STEP_SUB_ACTIONS.get(step.index, [])
    already_fired_actions = sorted(session.walkthrough_fired_actions - {"start-generation"})
    next_sub_action = next((a for a in sub_actions if a not in session.walkthrough_fired_actions), None)
    fired_actions_line = (
        (
            (
                f"\nYou've ALREADY covered these sub-parts of this step this run: {', '.join(already_fired_actions)}. "
                "Do NOT re-fire or re-narrate any of these as if for the first time.\n"
                if already_fired_actions
                else ""
            )
            + (
                f"The exact next sub-part/stage to move into (once you're done with whatever you're "
                f"currently on) is action \"{next_sub_action}\" — use that exact value, not one you've "
                "already fired above.\n"
                if next_sub_action
                else ""
            )
        )
        if step.index in (6, 7) and sub_actions
        else ""
    )
    return (
        f"\nFull walkthrough step list (for resolving skip-ahead requests by name — always use "
        f"the exact number listed here, never estimate or count): {full_list}.\n"
        f"{position_line}"
        f'"{step.title}." {action_line} Guidance for this step: {step.guidance} {next_line}\n'
        f"{paused_line}"
        f"{generate_fired_line}"
        f"{fired_actions_line}"
        "If this step's content was already fully delivered in your own last reply (check the "
        "conversation history below) and the prospect's message just now was an ordinary "
        "acknowledgment rather than a real question, move on to the next step now instead of "
        "repeating or expanding on what you already said. Only set \"walkthrough_step\" to the "
        "next step's number on the SAME turn you actually fire that next step's action (or, for a "
        "no-action step, actually deliver its content) — a line like \"let's head into X next\" is a "
        "fine natural transition to say, but don't bump the step number until the matching action/"
        "content for that new step is really happening in this same reply, not queued for later. Use "
        "the exact \"action\" object given above for that next step, verbatim — don't invent your own "
        "page/component/method (e.g. a generic scroll) even if it sounds like a reasonable way to "
        "reveal the same content; the frontend only recognizes the exact registered actions. Also: "
        "don't preview that next step by name inside THIS step's own \"reply\" (no \"let's move on to "
        "X next\" tacked onto the end) — that transition announcement is \"lead_in\"'s job, on the turn "
        "you actually jump there. Saying it in both places, once here and again as the next turn's "
        "lead_in, is redundant and reads as robotic — say it once.\n"
        "General walkthrough rules: once started, keep moving through steps turn to turn without "
        "needing an explicit \"yes, continue\" first — the prospect's ordinary next turn (even a "
        "short \"okay\"/\"cool\"/filler ack) is itself enough of a go-ahead to advance. This is the "
        "one deliberate exception to instruction 3's caution about firing several different actions "
        "back-to-back without a real go-ahead — during an active walkthrough, moving to the next "
        "step IS the expected behavior — in fact the system will keep prompting you to continue on "
        "its own between beats, without the prospect needing to say anything at all, specifically so "
        "a prospect who's just quietly watching (the common case) still gets the full tour instead of "
        "it stalling out waiting for them to speak. If instead the prospect asks a real question or "
        "raises something new (not just an ack), that's a genuine interruption: answer it fully "
        "first without changing \"walkthrough_step\" this turn, then explicitly ask something like "
        "\"want me to keep going with the tour?\" AND set \"walkthrough_awaiting_answer\" true on "
        "that same turn — this is what pauses the automatic continuation and makes it actually wait "
        "for their real answer instead of plowing ahead; forgetting to set it here means the tour "
        "would keep going right past their question, which is exactly the failure this field exists "
        "to prevent. This pause is STICKY: once set, it holds through as many follow-up questions as "
        "they ask, even across several turns — you don't need to re-set it again on every one of those "
        "turns, just keep answering naturally and don't touch \"walkthrough_step\". The ONLY thing that "
        "resumes the tour is the prospect clearly saying something that means yes, let's continue — set "
        "\"resume_walkthrough\" true on THAT turn (not \"walkthrough_step\"; the system already knows "
        "which step you're on and picks it back up on its own). If they ask to skip straight to a specific part of the tour, jump "
        "\"walkthrough_step\" directly to it instead of insisting on the fixed order. If they say "
        "they're done with the tour, set \"end_walkthrough\" instead of advancing. Same field, "
        "different trigger: if the prospect indicates they're LEAVING the call itself (\"I have to "
        "go\", \"I have to drop\", out of time, etc), set \"end_walkthrough\" true on that same turn "
        "too, even though your reply is just a warm goodbye rather than anything that sounds like "
        "wrapping up a tour — this is NOT the same as the genuine-interruption case above (don't set "
        "\"walkthrough_awaiting_answer\" for a goodbye, and don't ask another question if "
        "\"farewell_question_asked\" is already true), it's a real stop. Without this, the "
        "auto-continue scheduler has no signal at all that the call is ending and will keep firing "
        "the next beat right past your own goodbye — confirmed live as the single worst failure mode "
        "of this whole feature, worse than any individual missed field elsewhere.\n"
    )


def _farewell_note(session: SessionState) -> str:
    """See SessionState.farewell_question_asked — surfaces the "already used
    my one closing question" state directly rather than expecting the model
    to infer it correctly from prose history under time pressure. Empty
    string once nothing's happened yet, so this costs nothing on a normal
    call that never gets cut short."""
    if not session.farewell_question_asked:
        return ""
    return (
        "\nYou already asked a closing/qualifying question the last time the prospect indicated "
        "they were leaving this call. If they indicate leaving again now, do NOT ask another "
        "question — no qualification question, no \"want me to connect you with a rep\" ask, "
        "nothing, even if it feels like a natural opening. Just give a short, warm goodbye and let "
        "them go. Two closing questions across two separate \"I have to go\" moments reads as not "
        "listening, even though each one alone would've been reasonable.\n"
    )


def _pacing_note(session: SessionState) -> str:
    elapsed_min = (time.monotonic() - session.started_at) / 60
    return (
        f"\nThis call has been running about {elapsed_min:.0f} minute(s) so far. Ideal target for the "
        "whole conversation is around 10 minutes — not a hard stop, just a sense of how much runway is left.\n"
    )


def _select_with_claude(message: str, session: SessionState, user_content: Optional[str] = None) -> AgentResult:
    if _client is None:
        raise RuntimeError("no client")

    # No truncation — session persistence should hold up like a real voice
    # chat's memory does, and each turn is short (spoken utterances in,
    # one-to-two-sentence replies out), so even a long consultative
    # conversation stays small in token terms.
    system = _build_system(session)

    # user_content lets a caller override the literal API turn content —
    # used by run_walkthrough_continuation() to send a synthetic
    # continuation directive instead of "Prospect just said" framing, since
    # nothing was actually said. `message` itself is only used to build the
    # default framing below; run_walkthrough_continuation passes "" for it
    # since user_content always overrides it there.
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
        messages=[{"role": "user", "content": user_content or f'Prospect just said: "{message}"'}],
        tools=[_tool_schema()],
        tool_choice={"type": "tool", "name": TOOL_NAME},
    )

    tool_use = next((b for b in msg.content if b.type == "tool_use"), None)
    if tool_use is None:
        raise RuntimeError("no tool use in response")

    return _parse_tool_result(tool_use.input, msg.stop_reason)


def _backfill_reply_messages(action: AgentAction, lead_in: str) -> list:
    """Shared prompt for backfilling a missing 'reply' (see
    _parse_tool_result's docstring for why this exists) — used by both the
    sync and async LLM clients below. Deliberately narrow: action and
    lead_in already happened and were already spoken live, so this only
    ever asks for the one missing piece, treating them as settled fact
    rather than re-deciding the turn (which risks a fresh reply
    contradicting what's already been said out loud)."""
    match = next(
        (a for a in FLAT_ACTIONS if a.page == action["page"] and a.component == action["component"] and a.method == action["method"]),
        None,
    )
    action_desc = f"{match.page_label} — {match.component_label}" if match else action["component"]
    return [
        {
            "role": "user",
            "content": (
                f'You just decided to take this action: "{action_desc}", and already said this '
                f'transition out loud: "{lead_in}". Write ONLY the next 1-2 sentences you would '
                "say right after that — continuing naturally from the lead-in (don't repeat it), "
                "explaining what this shows or why it matters to the prospect given the "
                "conversation so far. Plain spoken text, no markup, no quotes around it."
            ),
        }
    ]


def _backfill_reply_sync(action: AgentAction, lead_in: str, session: SessionState) -> Optional[str]:
    """Sync counterpart to _backfill_reply_async — used by run_turn()'s
    text-chat-only path, which has no event loop to await into. Best-effort:
    any failure here just means the caller keeps the bare template that was
    already in `result["reply"]`, exactly like before this existed."""
    if _client is None:
        return None
    try:
        msg = _client.messages.create(
            model=_model,
            max_tokens=120,
            system=_build_system(session),
            thinking={"type": "disabled"},
            messages=_backfill_reply_messages(action, lead_in),
        )
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        return text or None
    except Exception:
        logger.exception("reply backfill call failed, keeping template fallback")
        return None


async def _backfill_reply_async(action: AgentAction, lead_in: str, session: SessionState) -> Optional[str]:
    """Async counterpart to _backfill_reply_sync — used by the voice
    pipeline's streaming/fallback paths, all of which already run inside an
    event loop."""
    if _async_client is None:
        return None
    try:
        msg = await _async_client.messages.create(
            model=_model,
            max_tokens=120,
            system=_build_system(session),
            thinking={"type": "disabled"},
            messages=_backfill_reply_messages(action, lead_in),
        )
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        return text or None
    except Exception:
        logger.exception("reply backfill call failed, keeping template fallback")
        return None


def _maybe_backfill_reply_sync(result: AgentResult, session: SessionState) -> AgentResult:
    """Patches a template-recovered reply (see _parse_tool_result) with a
    real, in-persona explanation, for run_turn()'s sync-only text-chat path.
    No-op when the marker isn't set or there's no action to ground the
    backfill in (the "Sorry, could you say that again?" no-action fallback
    is already a safe response on its own — nothing was already spoken
    ahead of it, so there's nothing to backfill)."""
    if not result.pop("_reply_needs_backfill", False):
        return result
    action = result.get("action")
    if not action:
        return result
    backfilled = _backfill_reply_sync(action, result.get("lead_in", ""), session)
    if backfilled:
        result["reply"] = backfilled
    return result


async def _maybe_backfill_reply(result: AgentResult, session: SessionState) -> AgentResult:
    """Async counterpart to _maybe_backfill_reply_sync — used by every
    voice-pipeline call site (run_turn_stream/_stream_with_claude/
    run_walkthrough_continuation), all of which can await."""
    if not result.pop("_reply_needs_backfill", False):
        return result
    action = result.get("action")
    if not action:
        return result
    backfilled = await _backfill_reply_async(action, result.get("lead_in", ""), session)
    if backfilled:
        result["reply"] = backfilled
    return result


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


def _finalize_turn(session: SessionState, result: AgentResult, persist: bool = True) -> AgentResult:
    """Shared end-of-turn bookkeeping — persisting anything the model just
    captured (prospect_name, MEDDIC fields, qualification fields) onto the
    session, updating current_page if an action fired, and logging the
    agent's reply. Shared by run_turn() and run_turn_stream() so this only
    exists in one place.

    persist=False (only ever passed by run_walkthrough_continuation's
    prefetch caller — see agent_processor.py's _drain_prefetch) skips both
    gate_log writes below while still fully mutating `session` — used when
    `session` is a disposable clone being speculatively advanced ahead of
    time, not the real session. Session-field mutations are cheap and
    harmless to redo/discard; the two gate_log calls are not, since they
    write straight through to a durable, hard-to-undo store. Real testing
    found this the hard way: log arithmetic on a real call showed 2 of 18
    _finalize_turn() calls were never actually spoken, yet had already
    written themselves permanently into session.history and the transcript
    DB — one of them a hallucinated reversion to an earlier wizard step
    that then poisoned every later turn's context. See
    commit_prefetched_turn, which replays a confirmed-to-be-spoken clone's
    mutations (and the gate_log writes this skipped) onto the real session."""
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
            if persist and session.visitor_id:
                gate_log.save_qualification_field(session.visitor_id, field_name, value)
            # len(history)//2 here equals the turn currently being
            # finalized (the agent's reply for it hasn't been appended
            # yet) — see _qualification_note's turn-count escalation,
            # which reads this to know how many turns have passed since
            # anything was last captured.
            session.last_qual_capture_turn = len(session.history) // 2

    # Walkthrough position — plain overwrite every turn the model moves it,
    # unlike the "set once" fields above. Precedence: end_walkthrough >
    # start_walkthrough > start_module_walkthrough > walkthrough_step —
    # start_walkthrough forces step 1 regardless of whatever (if anything)
    # walkthrough_step was also set to, since it's the dedicated,
    # unambiguous "begin the tour" signal (see _tool_schema's
    # start_walkthrough field — split out specifically because real testing
    # showed the model reliably firing the right "action" but silently
    # never setting a combined start/advance walkthrough_step field on the
    # actual first trigger turn).
    end_walkthrough = result.pop("end_walkthrough", None)
    start_walkthrough = result.pop("start_walkthrough", None)
    start_module_walkthrough = result.pop("start_module_walkthrough", None)
    resume_walkthrough = result.pop("resume_walkthrough", None)
    new_step = result.pop("walkthrough_step", None)
    prev_walkthrough_step = session.walkthrough_step
    # Read early (non-destructively — "action" itself is popped nowhere,
    # just read again later) so the guard right below can use it.
    action_method = (result.get("action") or {}).get("method")

    # Ground truth guard: start-generation firing for the FIRST time this
    # step 6/7 run must never ALSO end or advance the walkthrough in the
    # SAME turn — the rendered result needs its own beat first (see the
    # guidance's own "move into step 7 on the turn AFTER that, not the same
    # one"). Confirmed live TWICE, two different ways the model expressed
    # "done" in the same breath as firing the render: once via
    # walkthrough_step advancing past 6/7 (full platform tour), once via
    # end_walkthrough=True (a module-scoped tour, where "done with this
    # step" correctly means "done with the whole scoped run" instead of a
    # numbered next step — but still happened before the result was ever
    # shown). Checked here, before the end_walkthrough/start_walkthrough/
    # start_module_walkthrough/new_step precedence chain below even runs,
    # since end_walkthrough's own branch would otherwise win outright and
    # this same-turn combination would never reach the new_step-only guard
    # a narrower, earlier version of this fix used to have.
    if (
        prev_walkthrough_step in (6, 7)
        and action_method == "start-generation"
        and not session.walkthrough_generate_fired
        and (end_walkthrough or (new_step is not None and new_step > prev_walkthrough_step))
    ):
        logger.warning(
            f"[{session.visitor_id}] start-generation fired and the walkthrough tried to "
            f"{'end (end_walkthrough)' if end_walkthrough else f'advance (walkthrough_step={new_step!r})'} "
            f"in the SAME turn — holding at step {prev_walkthrough_step} so the result gets its own beat first"
        )
        end_walkthrough = False
        new_step = None

    if end_walkthrough:
        session.walkthrough_step = None
        session.walkthrough_scope_end = None
    elif start_walkthrough:
        # A genuine full-tour request always means "no scoping" — even if
        # a module-scoped walkthrough was already active, this supersedes
        # it (matches instruction 0b: an explicit "start over"/"whole
        # platform" request is a real, deliberate restart).
        session.walkthrough_step = 1
        session.walkthrough_scope_end = None
    elif start_module_walkthrough:
        # "magicreel"/"magicavatar" map onto their existing deep-dive
        # step indices in walkthrough.py (6, 7) — this is the SAME
        # auto-advancing machinery the full tour already uses for these
        # two steps, just entered directly and capped there instead of
        # continuing into the rest of the platform. See _walkthrough_note
        # for how walkthrough_scope_end changes what "the next step" means.
        module_entry_step = {"magicreel": 6, "magicavatar": 7}.get(start_module_walkthrough)
        if module_entry_step is not None:
            session.walkthrough_step = module_entry_step
            session.walkthrough_scope_end = module_entry_step
    elif new_step is not None:
        if prev_walkthrough_step is not None:
            if session.walkthrough_scope_end is not None and new_step > session.walkthrough_scope_end:
                # The model tried to advance past a module-scoped
                # walkthrough's own boundary (e.g. MagicReel done, trying
                # to roll into MagicAvatar/MLR/analytics) — that's exactly
                # what scoping this walkthrough was for preventing. Treat
                # reaching the boundary as the walkthrough ending, the same
                # way step 10 ends a full tour, rather than silently
                # letting it wander into the rest of the platform.
                logger.warning(
                    f"[{session.visitor_id}] walkthrough_step={new_step!r} would advance past "
                    f"scope_end={session.walkthrough_scope_end!r} — ending the module walkthrough instead"
                )
                session.walkthrough_step = None
                session.walkthrough_scope_end = None
            else:
                session.walkthrough_step = new_step
        else:
            # No scripted tour actually active (and start_walkthrough wasn't
            # set this turn either) — this field is meant ONLY for position
            # within the scripted 10-step walkthrough, but the model sets it
            # from other context too, e.g. narrating an ad hoc studio
            # wizard's own internal steps (Source/Brief/Script/...), which
            # has nothing to do with the scripted tour. Applying it here
            # would silently re-arm the auto-continue scheduler and inject
            # an old, unrelated scripted-tour beat into the middle of an
            # unrelated conversation — confirmed happening on a real call
            # (walkthrough_step went None -> 3 mid-wizard, then the
            # scheduler spoke a stale MagicReel beat minutes later,
            # unprompted). Only an active tour, a fresh start_walkthrough,
            # or a fresh start_module_walkthrough may ever move this field.
            logger.warning(
                f"[{session.visitor_id}] ignoring walkthrough_step={new_step!r} — no active scripted "
                "walkthrough and start_walkthrough wasn't set this turn, likely ad hoc wizard narration"
            )

    # Ground truth for "has start-generation already fired for the CURRENT
    # step 6/7 wizard run" — see SessionState.walkthrough_generate_fired.
    # Any real step change (advancing off 6/7, ending the tour, a fresh
    # module/full walkthrough start) means whatever "already generated"
    # state applied to the PREVIOUS run no longer applies — each wizard run
    # needs its own fresh signal, which is why this is checked against
    # prev_walkthrough_step rather than just "not in (6, 7)" (that alone
    # would wrongly carry step 6's flag over onto a freshly-entered step 7).
    already_fired = session.walkthrough_generate_fired
    if session.walkthrough_step != prev_walkthrough_step:
        session.walkthrough_generate_fired = False
        already_fired = False
        # A fresh run through 6/7 (or leaving it) starts with a clean slate —
        # see SessionState.walkthrough_fired_actions.
        session.walkthrough_fired_actions = set()
    # Ground truth for "which step 6/7 sub-actions have already fired in the
    # CURRENT wizard run" — see SessionState.walkthrough_fired_actions.
    # Recorded for every action, not just start-generation (that one keeps
    # its own dedicated flag/backstop right below since it needs stronger
    # handling — forcing wrap-up on a repeat, not just a prompt note).
    if session.walkthrough_step in (6, 7) and action_method:
        session.walkthrough_fired_actions.add(action_method)
    if session.walkthrough_step in (6, 7) and action_method == "start-generation":
        if already_fired:
            # The model fired it again despite _walkthrough_note's own
            # ground-truth line telling it not to (see generate_fired_line
            # below) — force the wrap-up as a hard backstop instead of
            # letting this repeat indefinitely. Same layered "prompt
            # guidance + code-level guard" pattern already used just above
            # for a module-scoped walkthrough overrunning its scope_end.
            # This turn's own reply/action still stand as generated — only
            # the step bookkeeping is corrected, so the NEXT beat sees a
            # real transition instead of repeating the same guidance again.
            logger.warning(
                f"[{session.visitor_id}] start-generation fired again for step "
                f"{session.walkthrough_step} after already firing once this run — forcing wrap-up"
            )
            if session.walkthrough_scope_end is not None:
                session.walkthrough_step = None
                session.walkthrough_scope_end = None
            else:
                session.walkthrough_step = session.walkthrough_step + 1
            session.walkthrough_generate_fired = False
        else:
            session.walkthrough_generate_fired = True

    # STICKY pause — deliberately NOT a hard reset every turn anymore. The
    # old version reset this to False whenever the model didn't re-mention
    # it, which meant a pause the model started correctly on one turn
    # silently lapsed the moment a later reply during the SAME tangent
    # didn't happen to end with another check-in question — confirmed live:
    # the tour auto-advanced through 6 scripted beats back-to-back while the
    # prospect was still mid-conversation, never having actually said
    # anything that meant "let's continue." Precedence: end/start_walkthrough
    # always clear it (a fresh or ended tour has nothing to be paused from);
    # otherwise "resume_walkthrough" is the ONLY thing that clears an active
    # pause; the model turning it true (re)starts a pause; omitting it on any
    # other turn leaves whatever's already there untouched, so a pause
    # started on turn N survives turns N+1, N+2, ... until a real resume
    # signal arrives, not just one exchange. See SessionState.walkthrough_awaiting_answer.
    new_awaiting = bool(result.pop("walkthrough_awaiting_answer", False))
    if end_walkthrough or start_walkthrough:
        session.walkthrough_awaiting_answer = False
    elif resume_walkthrough:
        session.walkthrough_awaiting_answer = False
    elif new_awaiting:
        session.walkthrough_awaiting_answer = True
    # else: leave session.walkthrough_awaiting_answer exactly as it was

    # Set-once, same pattern as the MEDDIC/qual fields above — never reset
    # back to False by a later turn. See SessionState.farewell_question_asked.
    if result.pop("farewell_question_asked", None):
        session.farewell_question_asked = True

    # Logged unconditionally (not just on change) so a real transcript can
    # show definitively whether the model set nothing at all this turn vs.
    # set something that happened to match the previous value — the
    # "replying: {...}" log elsewhere only shows the raw model output
    # BEFORE this function pops these three fields out of it, so it can
    # never actually confirm what _finalize_turn did with them. This is
    # the only place that can.
    if session.visitor_id:
        logger.info(
            f"[{session.visitor_id}] walkthrough: step {prev_walkthrough_step} -> {session.walkthrough_step} "
            f"(start_walkthrough={bool(start_walkthrough)}, walkthrough_step_field={new_step!r}, "
            f"end_walkthrough={bool(end_walkthrough)}, awaiting_answer={session.walkthrough_awaiting_answer})"
        )

    if result.get("action"):
        session.current_page = result["action"]["page"]
    session.history.append(HistoryEntry(role="agent", text=result["reply"]))
    if persist and session.visitor_id:
        gate_log.append_transcript_turn(session.visitor_id, "agent", result["reply"])
    return result


# Appended to a reply that was cut off mid-delivery, so the transcript the
# model reads back agrees with INTERRUPTION_NOTE instead of contradicting it.
# Deliberately plain-language and bracketed: it has to read as metadata, not
# as something the agent said out loud.
CUTOFF_MARKER = " …[cut off here — the prospect interrupted]"
NOTHING_SPOKEN_MARKER = "[interrupted before any of this reply was spoken aloud]"


def amend_last_agent_turn(
    session: SessionState,
    spoken_text: str,
    expected_full_text: str,
    persist: bool = True,
) -> bool:
    """Corrects the last agent history entry down to what was ACTUALLY heard.

    Why this exists as a separate, after-the-fact step rather than just
    passing the spoken text into _finalize_turn: by the time anyone knows how
    much was heard, _finalize_turn has already run. It is called inside the
    streaming generators (see _stream_with_claude / run_walkthrough_continuation)
    at the moment the model's output is complete — which is BEFORE the
    consumer has finished speaking the last sentences, and in the streaming
    case even before some of them have been spoken at all. There is no value
    that could be handed to it that would be correct. So the entry is written
    in full, and corrected here once the turn really ends.

    This is the same shape the reference implementations use: pipecat commits
    its assistant aggregation on the interruption itself, and OpenAI's
    Realtime API has the client send conversation.item.truncate after the
    barge-in. Ours is sentence-granular where theirs are word/millisecond
    granular (see the caller for why that's the right trade here).

    Guarded, never blind-indexed: only amends when the last entry is still an
    agent entry holding exactly `expected_full_text`. Anything else means
    something was appended since (a hand-raise handoff, the "still catching
    up" recovery, a whole new turn) and the row this wanted to fix is no
    longer the last one — in which case it does nothing rather than corrupt
    an unrelated entry. Returns whether it amended."""
    if not session.history:
        return False
    last = session.history[-1]
    if last.role != "agent" or last.text != expected_full_text:
        logger.warning(
            f"[{session.visitor_id}] skipping interrupted-turn amendment: last history entry is "
            f"no longer the reply that was being spoken (role={last.role!r})"
        )
        return False
    if spoken_text == expected_full_text:
        return False
    last.text = spoken_text
    if persist and session.visitor_id:
        gate_log.amend_last_agent_turn(session.visitor_id, expected_full_text, spoken_text)
    return True


def commit_prefetched_turn(session: SessionState, computed: SessionState, result: AgentResult) -> None:
    """Called by agent_processor.py's _take_ready_prefetch the moment a
    prefetch (see _drain_prefetch, run_walkthrough_continuation's
    persist=False mode) is confirmed to actually be spoken — replays
    `computed` (the disposable clone _finalize_turn already mutated,
    persist=False) onto the real `session`, plus performs the two gate_log
    writes persist=False deliberately skipped, so a CONSUMED prefetch ends
    up byte-for-byte identical to what a normal, non-prefetched call would
    have persisted, while a discarded one (never called here at all) leaves
    no trace anywhere. Qualification/MEDDIC fields are re-persisted
    individually by diffing against the pre-commit session, rather than
    just trusting `computed`'s own field values, since those already had
    their OWN gate_log write skipped inside _finalize_turn and need it done
    now for the same reason the transcript turn does."""
    for field_name in (*_MEDDIC_LABELS, *_QUAL_LABELS):
        new_value = getattr(computed, field_name)
        if new_value and new_value != getattr(session, field_name):
            if session.visitor_id:
                gate_log.save_qualification_field(session.visitor_id, field_name, new_value)
    session.__dict__.update(computed.__dict__)
    if session.visitor_id:
        gate_log.append_transcript_turn(session.visitor_id, "agent", result["reply"])


def run_turn(message: str, session: SessionState) -> AgentResult:
    _begin_turn(session, message)
    if _client is not None:
        try:
            result = _select_with_claude(message, session)
            result = _maybe_backfill_reply_sync(result, session)
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


async def _stream_with_claude(message: str, session: SessionState, user_content: Optional[str] = None) -> AsyncIterator[tuple]:
    if _async_client is None:
        raise RuntimeError("no async client")

    system = _build_system(session)

    action_extractor = _BalancedObjectExtractor("action")
    lead_in_extractor = _StreamingFieldExtractor("lead_in")
    reply_extractor = _StreamingFieldExtractor("reply")
    lead_in_and_action_handled = False

    # See _select_with_claude's matching comment — user_content lets
    # run_walkthrough_continuation() override the literal API turn content.
    async with _async_client.messages.stream(
        model=_model,
        max_tokens=700,
        system=system,
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": user_content or f'Prospect just said: "{message}"'}],
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
                    if action_dict:
                        action_dict = _repair_action(action_dict)
                    if action_dict:
                        yield ("lead_in", lead_in_extractor.value)
                        yield ("action", action_dict)
                    # An action span that parsed but failed validation (even
                    # after _repair_action's best-effort recovery), or didn't
                    # parse at all, is treated as "no action" for streaming
                    # purposes too -- _parse_tool_result applies the exact
                    # same repair to the authoritative result, so the two can
                    # never disagree on whether (or how) an action fires.

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
    result = await _maybe_backfill_reply(result, session)

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
            result = await _maybe_backfill_reply(result, session)
        except Exception:
            logger.exception("LLM call failed, falling back to keyword matcher")
            result = _fallback_reply(_keyword_match(message))
    else:
        result = _fallback_reply(_keyword_match(message))
    yield ("done_fallback", _finalize_turn(session, result))


# Sent as the API call's own user-turn content for an auto-continue cycle —
# never persisted to session.history or gate_log (see
# run_walkthrough_continuation below). Deliberately explicit that nothing
# was said, so the model doesn't half-guess it's responding to real speech.
_WALKTHROUGH_CONTINUE_DIRECTIVE = (
    "(No new input from the prospect — they haven't said anything since your last reply. "
    "Continue the scripted walkthrough on your own initiative: narrate and act on the next "
    "step now, exactly as instructed in the walkthrough note below.)"
)


async def run_walkthrough_continuation(session: SessionState, persist: bool = True) -> AsyncIterator[tuple]:
    """Auto-continue counterpart to run_turn_stream(), used only by the voice
    pipeline's auto-continue scheduler (agent_processor.py) to advance the
    scripted walkthrough on its own initiative, with no new prospect speech.
    Same streaming event contract as run_turn_stream() (see its docstring)
    so the caller can reuse the exact same consumption logic for both —
    except this can also end with NO done_streamed/done_fallback event at
    all (see bottom), which the caller must treat as "nothing to speak this
    cycle," not an error.

    persist=False is threaded straight through to _finalize_turn — see its
    own docstring. Only ever passed False by a prefetch (agent_processor.py's
    _drain_prefetch), and only ever against a disposable session clone, never
    the real session.

    Deliberately does NOT call _begin_turn(): there is no real prospect
    message to log. Calling run_turn_stream() with a synthetic "message"
    instead of this dedicated function would append a fabricated
    role="user" HistoryEntry to session.history AND a fabricated row to the
    durable gate_log transcript — the model would literally see "Prospect
    just said: ..." for words the prospect never said, and the admin
    dashboard / call summary would show it too. Instead, the continuation
    directive is sent directly as this one API call's user-turn content
    (via _select_with_claude/_stream_with_claude's user_content override)
    and never written anywhere. This still finishes through the shared
    _finalize_turn(), which only ever persists the AGENT's reply and the
    resulting walkthrough_step/action state — safe regardless of how the
    turn started, and it's what correctly advances walkthrough_step here.

    Only ever called while session.walkthrough_step is already active — the
    caller (agent_processor.py) is responsible for that check; this
    function doesn't gate on it itself."""
    if _async_client is not None:
        try:
            reply_fully_streamed = False
            result: Optional[AgentResult] = None
            async for event in _stream_with_claude("", session, user_content=_WALKTHROUGH_CONTINUE_DIRECTIVE):
                if event[0] == "_reply_fully_streamed":
                    reply_fully_streamed = event[1]
                elif event[0] == "result":
                    result = event[1]
                else:
                    yield event
            if result is not None:
                final = _finalize_turn(session, result, persist=persist)
                if reply_fully_streamed:
                    yield ("done_streamed", final)
                else:
                    yield ("done_fallback", final)
                return
        except Exception:
            logger.exception("Streaming LLM call failed during walkthrough auto-continue, falling back to non-streaming path")

    if _client is not None:
        try:
            result = _select_with_claude("", session, user_content=_WALKTHROUGH_CONTINUE_DIRECTIVE)
            result = await _maybe_backfill_reply(result, session)
            yield ("done_fallback", _finalize_turn(session, result, persist=persist))
            return
        except Exception:
            logger.exception("Walkthrough auto-continue LLM call failed entirely — skipping this continuation cycle")
    # Both paths failed (or no client configured at all): yield nothing
    # further. Unlike run_turn_stream(), there's no keyword-matcher fallback
    # here — there's no real prospect message to keyword-match against, and
    # speaking a wrong guess unprompted is worse than silently skipping one
    # auto-continue beat. The caller sees the generator end with no
    # "done_*" event and treats that as "nothing to speak this cycle."


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
