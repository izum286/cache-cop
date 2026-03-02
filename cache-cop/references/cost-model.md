# Prompt Cache Cost Model

Use this file when comparing providers, planning a migration, decoding an unexpected invoice, or staring at a "hit rate is 90% but the bill isn't moving" report. Prices, model lineups, TTLs, cache discounts, write and storage premiums — all of these drift. Pull current numbers from the vendor before any exact math. For latency or throughput puzzles, `references/mechanics.md` is the companion file.

## The Cost Equation

The price page is a starting point, not the answer. Model each request by its shape:

- `S` — stable input tokens, the part of the prompt designed to repeat
- `D` — dynamic input tokens, unique per request
- `O` — output tokens
- `h` — observed cache hit rate on the stable prefix, from `0` to `1`
- `P_miss` — input price (or compute) for an uncached request
- `P_hit` — input price (or compute) for a cache read
- `P_write` — input price (or compute) when the cache entry is created, where the provider bills it separately
- `P_out` — output price

The averaged shape:

```text
C = S * ((1 - h) * P_miss + h * P_hit) + D * P_miss + O * P_out
```

For providers that expose explicit cache fields, drop the averages and use raw telemetry:

```text
C = input_uncached * P_miss
  + cache_read_tokens * P_hit
  + cache_write_tokens * P_write
  + output_tokens * P_out
  + storage_or_ttl_cost
```

Provider math doesn't port. What works on one bill breaks on another. And when output dominates the bill, caching can do its job perfectly and still barely move finance.

## What Telemetry You Need

Pull real usage records. Not remembered averages — memory rounds toward optimism.

Collect what's available:
- total input tokens
- output tokens
- dynamic uncached input tokens
- cached-read tokens (`cached_tokens`, `cache_read_input_tokens`)
- cache-creation / write tokens (`cache_creation_input_tokens`)
- Bedrock-style read/write fields (`CacheReadInputTokens`, `CacheWriteInputTokens`)
- timestamps to compare traffic cadence against TTL
- model, region, route, prompt version, cache key or prefix family

Anthropic-style math has a sharp edge: total input for hit-rate calculation must include cache reads, cache creation, *and* uncached input. Counting only `input_tokens` will overstate the hit rate.

## When Caching Disappoints

### Hit Rate Climbs, Bill Doesn't

Before swapping models, check output share. When output tokens drive most of the spend, even a real input-side win can register as nothing on finance.

Workflow:
- read p50/p95 output token counts per route
- split total cost across input misses, cache reads, cache writes, and output
- check whether a flagship model's output pricing is doing most of the damage
- touch output length, response compression, or model choice only after sanity-checking quality requirements

### Cache Hits Without TTFT Wins

Prompt caching pays out at prefill — the input side. If total response latency stays high, separate TTFT from decode:

- first-token latency / prefill time
- output tokens
- final-token latency
- provider streaming overhead
- tool execution time

A long final response isn't a prompt-cache failure unless TTFT or prefill regressed alongside it.

### The Sticker Price Lies

Migrations get sold on the price page. The price page lies. Run both providers through the same workload shape:

- output token count
- static token count
- dynamic token count
- minimum cacheable tokens and TTL
- real or conservative hit rate
- cache write / storage premium

For migration planning, compute two numbers:
- the target effective cost using a conservative hit rate and conservative prefill savings until the new provider proves itself on production traffic
- the current effective cost using the observed hit rate

### Write-Premium Trap

Explicit caching pays well when reuse is dense. It hurts when traffic is sparse — the cache write gets billed, then nothing comes back to read it.

Check:
- whether cache creation shows up separately from cache reads in telemetry
- how often the same stable prefix is reused before TTL expires
- whether the long-TTL tier adds storage or a higher write rate
- whether cache writes get re-paid after idle windows

If `cache_creation_input_tokens` is high and reads stay low, the diagnosis is prefix mismatch, TTL too short, model/region without support, route rewriting, or explicit-cache object lifecycle. Larger TTL is a last resort, not the first move.

### The Migration Tax

A 90% hit rate from the old provider does not transfer.

Common ways the migration tax shows up:
- different minimum-token thresholds or TTLs change which routes are cacheable at all
- exact-prefix providers can't reuse a static RAG block placed after dynamic user text
- implicit caching may be best-effort, not guaranteed
- explicit cache breakpoints don't map cleanly onto implicit prefix caching
- usage field names differ between providers, hiding write-without-read failures behind unfamiliar telemetry

### Isolation Costs

Per-user or per-request cache isolation can be the right security call *and* still cost reuse. Treat it as a policy decision, not a bug:

- estimate the cache reuse achievable at that boundary
- identify the trust boundary that compliance or side-channel concerns actually require
- broader sharing is only recommendable when the data and threat model permit it
- watch for accidental isolation from request IDs, session IDs, or per-request salts that no one meant to insert

## Self-Hosted Math

On self-hosted inference, cache savings don't show up as a discounted invoice. They appear as:
- faster TTFT
- lower prefill compute
- relieved GPU pressure
- higher throughput

Ask for:
- TTFT by route and prompt family
- prefix-cache hit / query metrics
- traffic volume and concurrency
- KV-block pressure and eviction metrics
- replica routing behavior

Managed-provider token discounts don't translate. The economic surface here is workload throughput and GPU capacity, not per-token price.

## Diagnostic Questions

1. Managed API billing or self-hosted compute?
2. What are p50/p95 `S`, `D`, and `O` per route?
3. What share of total cost is output?
4. Which cache read/write fields are visible in raw usage?
5. Is traffic steady enough to support the selected TTL or cache lifetime?
6. How many prompt variants or prefix families are splitting reuse?
7. Which hit rate is safe to assume during migration before production evidence exists?
