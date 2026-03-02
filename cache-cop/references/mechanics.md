# Prompt Cache Mechanics

Open this file when the symptom is latency, throughput, self-hosted compute, or "cache hits work but cost and latency didn't move enough."

## Two Phases, Different Bills

LLM inference runs in two phases that bill and limit differently:

- **Prefill** — the model digests the prompt and builds KV tensors for every input token.
- **Decode** — the model emits new tokens one at a time, riding on the existing KV state.

Prompt and prefix caching saves prefill work for the stable part of the prompt. It doesn't make output tokens cheaper, and it usually doesn't shorten decode for a long generated answer.

## What Cache Hits Actually Move

When cache hits show up but the user still sees high cost or latency, split the request:

```text
cache_hit_latency  ~= cache_lookup_or_read + dynamic_tail_prefill + decode + tools/network
cache_miss_latency ~= full_prefill + decode + tools/network
total_cost         ~= input_miss + cache_write + cache_read + output
```

Then inspect:
- TTFT or prefill latency
- static input tokens
- dynamic input tokens after the cached prefix
- whether output tokens dominate cost
- output tokens
- cache read/write fields
- time between first token and final token

## Common Pitfalls

### High Hit Rate, Low Savings

If output tokens dominate the bill, input-cache savings can be real and still register as nothing. Load `references/cost-model.md` and calculate cost share before touching the cache strategy.

### TTFT Dropped, Total Latency Didn't

When cache hits cut TTFT but the final response still arrives slowly, the rest of the budget lives elsewhere — output length, streaming cadence, tool execution time, decode bottlenecks. The cache is doing its job; something downstream isn't.

### Total Prompt Tokens Look High

Some providers still roll cached tokens into the total prompt/input fields. Don't read "high total input" as proof of a cache miss — check the provider-specific cache-read fields directly.

### Self-Hosted Hit Rate Looks Good, Throughput Still Bad

For self-hosted engines, a prefix hit doesn't guarantee throughput. Dynamic prefill, decode, KV memory pressure, replica routing, CPU/GPU transfers, and scheduler behavior each carry their own ceiling. Inspect TTFT, decode throughput, KV block pressure, and per-route concurrency together — not in isolation.

## Observability

For latency audits, collect:
- provider first-token timestamp or TTFT
- `request_start`
- final-token timestamp
- prefix family / route / model / provider
- input tokens, cached-read tokens, cache-write tokens, output tokens
- network or provider overhead when measurable
- tool execution timing for agents
- worker or replica for self-hosted inference

For cost audits, pull raw usage records. Averages hide the gap between routes with long static prefixes and routes with unique-per-request prompts.
