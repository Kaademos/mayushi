# ADR-0002: Bake the embeddings model into the ingest-worker image

- Status: Accepted
- Date: 2026-11-02

## Context

The RAG pipeline embeds documents locally with sentence-transformers so the stack can run offline. By default the library downloads model weights from the Hugging Face Hub on first use, which would make runtime depend on network access and make first-run timing unpredictable.

## Decision

Download the embeddings model during `docker build` of `services/ingest-worker` (and any image that embeds queries) and store it in the image. At runtime set `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` so the library never reaches the network. The model name and revision are pinned as build args.

## Consequences

- **One-time download at build time.** Building the image needs internet access once (roughly 100–500 MB depending on the model). After that, `make up` and all runtime behaviour are offline.
- Images are larger; rebuilds reuse the cached layer unless the model pin changes.
- Changing the model requires a rebuild and re-embedding the knowledge base.
