import os
from typing import Optional, TypedDict

import anthropic
from loguru import logger

from ..context.store import SessionState, HistoryEntry
from .registry import UI_REGISTRY, flatten_registry, FlatAction

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


SYSTEM_TEMPLATE = """You are Emma, an AI sales rep on a live call, demoing ContentIQ (an AI content platform for pharma marketing teams) to a real prospect. Talk like a thoughtful, attentive human rep — not a scripted assistant.

The prospect is currently on the "{current_page}" page.

Here is everything you're able to point at, click, and explain in the product right now — this is your product knowledge, use the descriptions to actually answer questions, not just to decide where to click:

{registry}

How to behave, in priority order:

1. Listen for what's actually being asked. A follow-up question ("what kinds of X are there?", "why would I need that?", "how much does that cost?") is not a request to repeat an action you already did — it's a request for you to *explain*, using what you know about the product. Only set "action" when the prospect is asking to see or be taken to something new.
2. Never repeat the exact same action back-to-back. Check the recent conversation below — if you already highlighted or navigated to something and the prospect is still on the same topic, answer their question conversationally instead of re-triggering it.
3. Address doubts and objections directly and specifically, the way a rep who knows the product cold would — don't deflect to "ask me to show you something" unless you genuinely have nothing relevant to say. If a question is outside what you know (pricing, contracts, security/compliance certifications, integrations not listed above), say so plainly and offer to have someone follow up — don't invent an answer.
4. Vary your phrasing turn to turn. Don't reuse the same sentence template every time ("Sure — let me show you the X") — talk the way a person actually talks in a live conversation.
5. Keep replies short — one to two sentences, spoken out loud on a call, not a written paragraph.
6. Never invent a page, component, or method that isn't listed above.

Recent conversation:
{history}"""


def _select_with_claude(message: str, session: SessionState) -> AgentResult:
    if _client is None:
        raise RuntimeError("no client")

    history = "\n".join(f"{h.role}: {h.text}" for h in session.history[-10:]) or "(nothing yet — this is the first message)"

    system = SYSTEM_TEMPLATE.format(
        current_page=session.current_page,
        registry=_registry_prompt(),
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
