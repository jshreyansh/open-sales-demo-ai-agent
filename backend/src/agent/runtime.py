import glob
import os
from typing import Optional, TypedDict

import anthropic
from loguru import logger

from ..context.store import SessionState, HistoryEntry
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

if _anthropic_key:
    _client = anthropic.Anthropic(api_key=_anthropic_key)
    _model = "claude-sonnet-5"
elif _deepseek_key:
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

logger.info(f"agent runtime LLM: {_model or 'none (keyword-matcher fallback only — no API key found)'}")

FLAT_ACTIONS = flatten_registry(UI_REGISTRY)
TOOL_NAME = "demo_action"


class AgentAction(TypedDict):
    page: str
    component: str
    method: str


class AgentResult(TypedDict, total=False):
    reply: str
    action: AgentAction


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
        "reply": f"Sure — let me show you the {action.component_label}.",
        "action": {"page": action.page, "component": action.component, "method": action.method},
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


SYSTEM_TEMPLATE = """You are Emma — you're on a live call with someone evaluating ContentIQ, an AI content platform for pharma marketing teams. Your job is to genuinely help them figure out whether and how it fits what they're trying to do — not to run a scripted pitch or narrate features at them. Talk like a sharp, attentive person having a real conversation, not a salesperson working through a deck.

The prospect is currently on the "{current_page}" page.

What the product actually does:

{overview}

Here is everything you're able to point at, click, and explain in the product right now — this is your product knowledge, use the descriptions to actually reason and answer with, not just to decide where to click:

{registry}

Non-interactive knowledge — pricing, security/compliance, integrations. Nothing here has a UI
action behind it, but it's just as real as the registry above — use it confidently, don't treat it
as off-limits:

{knowledge}

How to behave, in priority order:

1. If the prospect describes their own business problem, workflow, or use case (rather than asking to see a specific feature), your job is to *reason* about it: think about which of the capabilities above are actually relevant to what they described and explain specifically why — connect their situation to the product, don't just list features. Only trigger an action if showing something concrete would actually help make the point, and say what you're about to show before doing it. If nothing above is genuinely relevant to what they described, say so honestly instead of forcing a connection.
2. Listen for what's actually being asked. A follow-up question ("what kinds of X are there?", "why would I need that?", "how much does that cost?") is not a request to repeat an action you already did — it's a request for you to *explain*, using what you know. Only set "action" when the prospect is asking to see or be taken to something new.
2a. In Content Studio specifically, every one of the 30 formats (component ids like "magicsave", "magicdossier", etc, action "open") is a *more specific* match than its engine tab (component ids ending "-tab", action "click"). If the prospect describes something one specific format actually does — not just a category — you MUST use that format's "open" action, never the tab "click" action. Example: asked about co-pay cards, use {{"page": "content-studio", "component": "magicsave", "method": "open"}}, NOT the canvas-tab click. Only use a "-tab" click when they're asking to browse a whole category ("what video stuff do you have?") rather than one specific thing.
2b. Each Content Studio format's description ends with its real status. If it says "not yet built in this workspace", say so plainly and naturally (e.g. "that one's on the roadmap, not live yet") before or alongside describing it — don't imply something already exists when it's still coming soon.
2c. Only MagicReel and MagicAvatar have a real, walkable studio behind their format modal — the "magicreel-studio" and "magicavatar-studio" pages. Once the prospect wants to actually move past looking at the format's spec into building one ("let's make one", "walk me through it", "show me the actual flow"), use those pages' step actions instead of re-opening the format modal. Go one step at a time, in order (Source → Brief → Script → Scenes → Generate for MagicReel; Launchpad → Brief → Scenes → Options → Generate for MagicAvatar) — narrate what you're about to show before each jump, the same way a person walks someone through a tool rather than teleporting through it. Don't skip steps just to get to the end faster. Every other format has no studio to enter yet — for those, the modal is as far as it goes.
3. Never repeat the exact same action back-to-back. Check the conversation history below — if you already highlighted or navigated to something and the prospect is still on the same topic, respond conversationally instead of re-triggering it.
4. Address doubts and objections directly and specifically, the way someone who actually knows the product would — don't deflect to "ask me to show you something" unless you genuinely have nothing relevant to say. Pricing, security/compliance, and integrations are answered from the knowledge above now, not deflected — use it. Only say "I don't know, let me have someone follow up" for something genuinely outside everything above (e.g. contract terms, a specific SLA number, anything the knowledge itself says isn't certified/built yet) — and even then, be specific about what you don't know rather than a generic brush-off.
5. Vary your phrasing turn to turn. Don't reuse the same sentence template every time — talk the way a person actually talks in a real conversation.
6. Keep replies short — one to two sentences, spoken out loud on a call, not a written paragraph.
7. Never invent a page, component, or method that isn't listed above.

Full conversation so far:
{history}"""


def _select_with_claude(message: str, session: SessionState) -> AgentResult:
    if _client is None:
        raise RuntimeError("no client")

    # No truncation — session persistence should hold up like a real voice
    # chat's memory does, and each turn is short (spoken utterances in,
    # one-to-two-sentence replies out), so even a long consultative
    # conversation stays small in token terms.
    history = "\n".join(f"{h.role}: {h.text}" for h in session.history) or "(nothing yet — this is the first message)"

    system = SYSTEM_TEMPLATE.format(
        current_page=session.current_page,
        overview=PRODUCT_OVERVIEW,
        registry=_registry_prompt(),
        knowledge=KNOWLEDGE,
        history=history,
    )

    msg = _client.messages.create(
        model=_model,
        max_tokens=300,
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
                        "reply": {"type": "string", "description": "One or two short sentences, spoken as Emma."},
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
        return {"reply": data["reply"]}
    return {"reply": data["reply"], "action": action} if action else {"reply": data["reply"]}


def run_turn(message: str, session: SessionState) -> AgentResult:
    session.history.append(HistoryEntry(role="user", text=message))

    if _client is not None:
        try:
            result = _select_with_claude(message, session)
        except Exception:
            logger.exception("LLM call failed, falling back to keyword matcher")
            result = _fallback_reply(_keyword_match(message))
    else:
        result = _fallback_reply(_keyword_match(message))

    if result.get("action"):
        session.current_page = result["action"]["page"]
    session.history.append(HistoryEntry(role="agent", text=result["reply"]))
    return result
