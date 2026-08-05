# backend

The backend for **Open Sales Demo AI Agent** — part of the `open-sales-demo-ai-agent`
monorepo, sibling to `../frontend`.

This is the **Agent Runtime**: it decides what to say, what to click, and what
flow to run. It owns the Context Store, Flow Engine, Knowledge Base, Dummy
Backend, and voice glue. It never renders anything — it tells `../frontend`
what to do and `../frontend` executes it.

For the full concept and system-level architecture, see the root
[`globalplan.md`](../globalplan.md). This repo's own north star and near-term
plan live in [`VISION.md`](./VISION.md) and [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## Stack

Python + FastAPI. Chosen so the voice layer (Pipecat, which is Python-core)
can sit in the same runtime as the Agent Runtime instead of needing a
separate service to bridge them. **Requires Python 3.11+** (Pipecat's
requirement) — on macOS, `brew install python@3.11` if your system Python is
older.

## Run

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys — see below
python -m src.server    # REST API: http://localhost:8787
```

Keys needed in `.env`:

- `ANTHROPIC_API_KEY` — optional. Without it, the agent still works, falling
  back to a dependency-free keyword matcher against the registry
  (`src/agent/registry.py`) instead of calling Claude.
- `GROQ_API_KEY` — for voice (STT). Free tier, no card required:
  [groq.com](https://groq.com) → Start Building → API Keys.
- `CARTESIA_API_KEY` / `CARTESIA_VOICE_ID` — for voice (TTS).

### Voice

Voice runs as a **separate process** from the REST API (see `ARCHITECTURE.md`
for why):

```bash
python -m src.voice.bot    # prints a URL, default http://localhost:7860/client/
```

That URL opens Pipecat's own prebuilt WebRTC test page — talk to it directly
to verify STT → Agent Runtime → TTS works before it's wired into the actual
product frontend.
