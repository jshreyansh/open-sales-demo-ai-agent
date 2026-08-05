import "dotenv/config";
import Fastify from "fastify";
import cors from "@fastify/cors";
import { getSession, saveSession } from "./context/store.js";
import { runTurn } from "./agent/runtime.js";
import { dashboardData } from "./data/dashboard.js";
import { analyticsOverview } from "./data/analytics.js";
import { brandKitData } from "./data/brandKit.js";

const app = Fastify();
await app.register(cors, { origin: true });

app.post("/chat", async (request, reply) => {
  const { visitorId, message, currentPage } = request.body as {
    visitorId?: string;
    message?: string;
    currentPage?: string;
  };
  if (!visitorId || !message) {
    return reply.code(400).send({ error: "visitorId and message are required" });
  }
  const session = getSession(visitorId);
  if (currentPage) session.currentPage = currentPage;
  const result = await runTurn(message, session);
  saveSession(visitorId, session);
  return result;
});

app.get("/health", async () => ({ ok: true }));

app.get("/api/dashboard", async () => dashboardData);
app.get("/api/analytics/overview", async () => analyticsOverview);

let brandKitState = { ...brandKitData };
app.get("/api/brand-kit", async () => brandKitState);
app.put("/api/brand-kit", async (request) => {
  brandKitState = { ...brandKitState, ...(request.body as object) };
  return brandKitState;
});

const port = Number(process.env.PORT) || 8787;
app.listen({ port }, (err, address) => {
  if (err) {
    app.log.error(err);
    process.exit(1);
  }
  console.log(`backend listening on ${address}`);
});
