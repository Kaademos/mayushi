# ADR-0001: Stack choices

- Status: Accepted
- Date: 2026-11-02

## Context

Mayushi models how a mid-size company ships an agentic AI support feature in 2026. The stack should be recognisable to engineers in that setting, run entirely on a developer laptop, and be reproducible from a fresh clone.

## Decision

| Concern | Choice |
|---|---|
| Frontend | Next.js (App Router, TypeScript), Tailwind |
| Gateway / BFF | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| Identity | Keycloak (OIDC), realm export committed |
| Business services | `orders-service` (FastAPI), own DB schema, service-to-service bearer tokens |
| Agent | Python agent loop with providers: `anthropic`, `openai_compatible`, `ollama`, `scripted` |
| Tools | MCP server on the official Python MCP SDK, streamable HTTP; agent is an MCP client |
| RAG | PostgreSQL 16 + pgvector; Redis-backed ingestion queue; local sentence-transformers embeddings |
| Memory | PostgreSQL table, accessed through agent tools |
| Email | Mailpit |
| Observability | OpenTelemetry SDK → OTel Collector → Jaeger; structured JSON logs |
| Packaging | Docker Compose, Make, `uv` (Python), `pnpm` (JS) |
| Tests | pytest + httpx; Playwright for E2E smoke |
| CI | CircleCI: ruff, eslint, mypy, tsc, tests, compose build (see ADR-0003) |

Model IDs are configured through environment variables, never hardcoded. The `scripted` provider makes the full test suite deterministic and offline.

## Consequences

- One Postgres instance serves several schemas, keeping the footprint small at the cost of weaker isolation between services.
- Python across all back-end services keeps tooling uniform (`uv`, ruff, mypy).
- Keycloak is heavy (~1 GB RAM) but gives a realistic OIDC flow with realm export for reproducibility.
- Running offline requires the embeddings model to be available locally (see ADR-0002).
