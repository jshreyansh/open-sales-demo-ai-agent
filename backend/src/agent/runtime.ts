import Anthropic from "@anthropic-ai/sdk";
import type { SessionState } from "../context/store.js";
import { UI_REGISTRY, flattenRegistry, type FlatAction } from "./registry.js";

export interface AgentAction {
  page: string;
  component: string;
  method: string;
}

export interface AgentResult {
  reply: string;
  action?: AgentAction;
}

const anthropic = process.env.ANTHROPIC_API_KEY
  ? new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY })
  : null;

const FLAT_ACTIONS = flattenRegistry(UI_REGISTRY);
const TOOL_NAME = "demo_action";

function keywordMatch(message: string): FlatAction | null {
  const tokens = message.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
  let best: FlatAction | null = null;
  let bestScore = 0;
  for (const action of FLAT_ACTIONS) {
    const score = tokens.filter((t) => action.keywords.includes(t)).length;
    if (score > bestScore) {
      bestScore = score;
      best = action;
    }
  }
  return bestScore > 0 ? best : null;
}

function fallbackReply(action: FlatAction | null): AgentResult {
  if (!action) {
    return {
      reply: "Ask me to show you something — the dashboard, content studio, or brand kit — and I'll walk you through it.",
    };
  }
  return {
    reply: `Sure — let me show you the ${action.componentLabel}.`,
    action: { page: action.page, component: action.component, method: action.method },
  };
}

function registryPrompt(): string {
  return UI_REGISTRY.map(
    (page) =>
      `Page "${page.id}" (${page.label}):\n` +
      page.components
        .map(
          (c) =>
            `  - component "${c.id}" (${c.label}): ${c.description} — actions: ${c.actions.map((a) => a.id).join(", ")}`,
        )
        .join("\n"),
  ).join("\n\n");
}

function isValidAction(action: AgentAction): boolean {
  return FLAT_ACTIONS.some((a) => a.page === action.page && a.component === action.component && a.method === action.method);
}

async function selectWithClaude(message: string, session: SessionState): Promise<AgentResult> {
  if (!anthropic) throw new Error("no client");
  const history = session.history
    .slice(-6)
    .map((h) => `${h.role}: ${h.text}`)
    .join("\n");

  const msg = await anthropic.messages.create({
    model: "claude-sonnet-5",
    max_tokens: 300,
    system: `You are Emma, a friendly AI sales demo agent driving a live product demo on a call. The prospect is currently on the "${session.currentPage}" page.

Here is everything you're able to point at and do in the product right now:

${registryPrompt()}

Only set "action" when the prospect's message clearly matches one of the components listed above — pick the single best match. Never invent a page, component, or method that isn't listed above. If nothing matches, reply conversationally and omit "action" entirely. Keep replies to one short sentence.`,
    messages: [{ role: "user", content: `Recent conversation:\n${history}\n\nProspect just said: "${message}"` }],
    tools: [
      {
        name: TOOL_NAME,
        description: "Reply to the prospect and, if relevant, trigger a UI action in the demo.",
        input_schema: {
          type: "object",
          properties: {
            reply: { type: "string", description: "One short sentence, spoken as Emma." },
            action: {
              type: "object",
              description: "Omit this field entirely if no listed component matches the request.",
              properties: {
                page: { type: "string" },
                component: { type: "string" },
                method: { type: "string" },
              },
              required: ["page", "component", "method"],
            },
          },
          required: ["reply"],
        },
      },
    ],
    tool_choice: { type: "tool", name: TOOL_NAME },
  });

  const toolUse = msg.content.find((b) => b.type === "tool_use") as
    | Extract<(typeof msg.content)[number], { type: "tool_use" }>
    | undefined;
  if (!toolUse) throw new Error("no tool use in response");

  const input = toolUse.input as { reply: string; action?: AgentAction };
  if (input.action && !isValidAction(input.action)) {
    return { reply: input.reply };
  }
  return input.action ? { reply: input.reply, action: input.action } : { reply: input.reply };
}

export async function runTurn(message: string, session: SessionState): Promise<AgentResult> {
  session.history.push({ role: "user", text: message });

  let result: AgentResult;
  if (anthropic) {
    try {
      result = await selectWithClaude(message, session);
    } catch {
      result = fallbackReply(keywordMatch(message));
    }
  } else {
    result = fallbackReply(keywordMatch(message));
  }

  if (result.action) session.currentPage = result.action.page;
  session.history.push({ role: "agent", text: result.reply });
  return result;
}
