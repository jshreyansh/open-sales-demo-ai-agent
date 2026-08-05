import os
from typing import Optional, TypedDict

import anthropic

from ..context.store import SessionState, HistoryEntry
from .registry import UI_REGISTRY, flatten_registry, FlatAction

_api_key = os.environ.get("ANTHROPIC_API_KEY")
_client = anthropic.Anthropic(api_key=_api_key) if _api_key else None

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


def _select_with_claude(message: str, session: SessionState) -> AgentResult:
    if _client is None:
        raise RuntimeError("no client")

    history = "\n".join(f"{h.role}: {h.text}" for h in session.history[-6:])

    system = f"""You are Emma, a friendly AI sales demo agent driving a live product demo on a call. The prospect is currently on the "{session.current_page}" page.

Here is everything you're able to point at and do in the product right now:

{_registry_prompt()}

Only set "action" when the prospect's message clearly matches one of the components listed above — pick the single best match. Never invent a page, component, or method that isn't listed above. If nothing matches, reply conversationally and omit "action" entirely. Keep replies to one short sentence."""

    msg = _client.messages.create(
        model="claude-sonnet-5",
        max_tokens=300,
        system=system,
        messages=[{"role": "user", "content": f'Recent conversation:\n{history}\n\nProspect just said: "{message}"'}],
        tools=[
            {
                "name": TOOL_NAME,
                "description": "Reply to the prospect and, if relevant, trigger a UI action in the demo.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "reply": {"type": "string", "description": "One short sentence, spoken as Emma."},
                        "action": {
                            "type": "object",
                            "description": "Omit this field entirely if no listed component matches the request.",
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
            result = _fallback_reply(_keyword_match(message))
    else:
        result = _fallback_reply(_keyword_match(message))

    if result.get("action"):
        session.current_page = result["action"]["page"]
    session.history.append(HistoryEntry(role="agent", text=result["reply"]))
    return result
