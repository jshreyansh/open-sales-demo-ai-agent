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

## Status

Not yet scaffolded — Phase 0 (see `ARCHITECTURE.md`).

## Run

TBD once the service is scaffolded.
