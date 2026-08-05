import "dotenv/config";
import Fastify from "fastify";
import cors from "@fastify/cors";
import { getSession, saveSession } from "./context/store.js";
import { runTurn } from "./agent/runtime.js";

const app = Fastify();
await app.register(cors, { origin: true });

app.post("/chat", async (request, reply) => {
  const { visitorId, message } = request.body as {
    visitorId?: string;
    message?: string;
  };
  if (!visitorId || !message) {
    return reply.code(400).send({ error: "visitorId and message are required" });
  }
  const session = getSession(visitorId);
  const result = await runTurn(message, session);
  saveSession(visitorId, session);
  return result;
});

app.get("/health", async () => ({ ok: true }));

const port = Number(process.env.PORT) || 8787;
app.listen({ port }, (err, address) => {
  if (err) {
    app.log.error(err);
    process.exit(1);
  }
  console.log(`backend listening on ${address}`);
});
