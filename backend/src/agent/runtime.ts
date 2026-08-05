import Anthropic from "@anthropic-ai/sdk";
import type { SessionState } from "../context/store.js";

export interface AgentAction {
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

async function narrate(prompt: string, fallback: string): Promise<string> {
  if (!anthropic) return fallback;
  try {
    const msg = await anthropic.messages.create({
      model: "claude-sonnet-5",
      max_tokens: 200,
      messages: [{ role: "user", content: prompt }],
    });
    const block = msg.content[0];
    return block?.type === "text" ? block.text : fallback;
  } catch {
    return fallback;
  }
}

export async function runTurn(
  message: string,
  session: SessionState,
): Promise<AgentResult> {
  session.history.push({ role: "user", text: message });

  const wantsOverview = /dashboard|insight|overview|show me/i.test(message);

  if (session.step === 0 && wantsOverview) {
    session.step = 1;
    const reply = await narrate(
      `You are Emma, a friendly product demo agent on a live sales call. The prospect just asked to see the dashboard. In one short sentence, tell them you're highlighting the Insights panel now.`,
      "Sure — I'm highlighting the Insights panel now, that's your live program performance at a glance.",
    );
    session.history.push({ role: "agent", text: reply });
    return { reply, action: { component: "insights", method: "highlight" } };
  }

  const reply = await narrate(
    `You are Emma, a demo agent on a live sales call. Reply briefly and helpfully to: "${message}"`,
    "Ask me to show you the dashboard and I'll walk you through it.",
  );
  session.history.push({ role: "agent", text: reply });
  return { reply };
}
