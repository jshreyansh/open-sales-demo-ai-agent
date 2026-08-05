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

  const wantsVideo = /video/i.test(message);

  if (session.step === 0 && wantsVideo) {
    session.step = 1;
    const reply = await narrate(
      `You are Emma, a friendly product demo agent on a live sales call. The prospect just asked about creating a video. In one short sentence, tell them you'll show them how, and mention you're highlighting the "Create Video" button now.`,
      "Let me show you — I'm highlighting the Create Video button now.",
    );
    session.history.push({ role: "agent", text: reply });
    return { reply, action: { component: "create-video", method: "highlight" } };
  }

  if (session.step === 1) {
    session.step = 2;
    const reply = await narrate(
      `You are Emma, a demo agent on a live sales call. In one short sentence, tell the prospect you're clicking Create Video to open the editor.`,
      "Clicking it now — this opens straight into the editor.",
    );
    session.history.push({ role: "agent", text: reply });
    return { reply, action: { component: "create-video", method: "click" } };
  }

  const reply = await narrate(
    `You are Emma, a demo agent on a live sales call. Reply briefly and helpfully to: "${message}"`,
    "Ask me to show you how to create a video and I'll walk you through it.",
  );
  session.history.push({ role: "agent", text: reply });
  return { reply };
}
