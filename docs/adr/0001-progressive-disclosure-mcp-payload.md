# ADR 0001: Progressive Disclosure MCP Payload & Fail-Soft Status Architecture

## Status
Accepted

## Context
When AI coding agents (e.g. Cursor, Antigravity) perform batch citation audits via Model Context Protocol (MCP), returning raw full-text abstracts and complete candidate scores across 30+ citations consumes upwards of 15,000+ LLM context tokens. Conversely, over-pruning payloads prevents agents from diagnosing ambiguous or mismatched citations. Simultaneously, infrastructure failures (timeouts, rate limits) must not be misinterpreted as hallucinated citations.

## Decision
We adopt a **Progressive Disclosure Payload Contract** governed by `detail: "compact" | "detailed" | "debug"`:
1. **Compact (Default)**: Returns minimal sufficient evidence (`citation_id`, `status`, `risk_level`, `title`, `doi`, `evidence_text`, `evidence_granularity`, `evidence_status`).
2. **Detailed**: Exposes 5-score resolution breakdowns (`resolution_metadata`), score margin, and `full_abstract` for single-citation deep dives.
3. **Debug**: Discloses provider diagnostic traces and candidate pool logs. Never returns raw embedding vectors.

For infrastructure failures, we enforce a **Fail-Closed Safety / Fail-Soft Availability** model: return `UNVERIFIED` + `evidence_status: PROVIDER_UNAVAILABLE` with a specific failure reason (`TIMEOUT`, `RATE_LIMITED`, `PROXY_ERROR`).

## Consequences
- Batch audits reduce context token consumption by ~85% (from ~15k to ~2.4k tokens).
- Upstream AI agents are explicitly prevented from falsely accusing authentic literature of being fake due to transient network timeouts.
