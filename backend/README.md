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
separate service to bridge them.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add ANTHROPIC_API_KEY to get live Claude narration
python -m src.server    # http://localhost:8787
```

Without `ANTHROPIC_API_KEY` set, the agent still works — it falls back to a
dependency-free keyword matcher against the same registry (`src/agent/registry.py`)
instead of calling Claude.
