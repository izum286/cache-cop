# Prompt Cache Runbook: Release, Incident, and Observability

Open this file for release reviews, incident triage, observability plans, and self-hosted deployment audits. It turns the anti-patterns into an operational flow.

## The Three Conditions

Prefix caching works only when all three are true at once:

1. The beginning of the request is token-identical enough for the provider or engine.
2. The request reaches a worker or cache domain where that prefix is warm.
3. The cache entry survives long enough to be reused.

Map every cache incident to one or more of these conditions before reaching for fixes.

## Blocking Pre-Deploy Checks

Block the deploy or require explicit signoff when a hot LLM path picks up any of these:

- dynamic or unordered `tools`
- timestamp, `request_id`, `run_id`, `trace_id`, user / company / tenant data landing in system prompt, tools, schema, or early messages
- Bedrock `cachePoint` / model-family cache-control placed after dynamic request content
- `response_format` or JSON schema containing per-request constants
- early-history summarization or truncation that rewrites the anchor
- mode switch implemented by changing the system prompt or tool list
- prompt A/B test or feature flag in front of the stable prefix
- OpenRouter provider/model routing changes on a cache-critical route without sticky-routing and fallback review
- `max_model_len` much larger than observed p99 without a KV-capacity review
- per-request or per-user cache salt or key that wasn't reviewed as a security trade-off
- context compression or message transforms enabled without prompt-prefix regression tests
- fan-out batch over a cold long prefix without a safe warm-up

## Release Checklist

### Prefix

- one canonical prompt renderer is used across all routes
- stable and shared content lives first
- dynamic user / session facts ride late or in provider-supported metadata
- the rendered prefix hash stays stable across users, timestamps, and equivalent requests

### API Envelope

- schema serialization is deterministic
- tools are stable in content and sorted order
- multimodal representation is stable, including image detail and URL / base64 strategy
- SDK or framework injection doesn't slip dynamic fields ahead of the prefix
- `response_format` carries no request-specific constants

### History

- compaction preserves the stable anchor
- conversation growth is append-only where possible
- truncation doesn't silently drop the stable anchor
- bulky tool results get compacted before any lossy summarization

### Routing

- self-hosted inference uses sticky, prefix-aware, or consistent-hash routing for long shared prefixes
- managed APIs use provider-supported cache keys or routing hints, after checking current docs
- OpenRouter routes get `provider.order`, `provider.only`, `provider.ignore`, fallback, `openrouter/auto`, ZDR / data filters, and first-message conversation identity reviewed
- cache salts or affinity keys line up with the intended trust boundary
- route keys don't over-fragment into per-user caches unless isolation actually requires it
- hot spots get monitored when routing by prefix family

### Lifetime and Capacity

- the prefix-family working set fits the KV / cache budget
- TTL or cache lifetime matches traffic cadence
- eviction and repeated warm-up are observable
- `max_model_len` is sized for the workload, not for the model's marketing context

## Incident Triage

Start with the timeline:
- prompt or template change
- deploy time
- tool or schema change
- SDK / model / provider change
- replica count or gateway change
- compaction or summarization rollout
- traffic shape or batch / fan-out change

Then isolate:
- Did the prefix hash change?
- Did requests move across replicas or routes?
- Did tool count or tool-name hash change?
- Did cache writes increase while reads stayed low?
- Did cache key, salt, `user`, or affinity cardinality change?
- Did output share dominate cost even though cache reads worked?
- Did TTFT rise only for long-prefix routes?

## Observability Dimensions

Track cache metrics by:
- prefix hash
- route or prompt family
- model and provider
- tool / schema hash
- region or endpoint
- prompt version
- cache key or prefix family
- deployment version
- cache salt / affinity key family
- agent step number
- replica or worker

Core metrics:
- TTFT or prefill latency
- cache read tokens
- cache creation / write tokens
- total input tokens
- output tokens
- cache ratio by cacheable route
- final-token latency or full streamed response duration
- cache writes without later reads
- KV block pressure and eviction metrics for self-hosted inference
- cache discount or effective cache savings when surfaced

## CI Smoke Tests

Add a synthetic prompt-prefix test for hot routes:

1. Render the same route across several users, timestamps, tenants, and trace IDs.
2. Extract canonical `system + tools + response_format + stable early messages`.
3. Hash with deterministic JSON serialization.
4. Fail when the hash changes unexpectedly.
5. Add a 3–5 step agent session if tools or compaction are in play.

Provider usage metadata stays the source of truth. Prefix hashes are release guardrails, not proof of provider cache hits.
