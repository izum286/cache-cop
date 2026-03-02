# Prompt-cache audit · openrouter (Chat Completions)

**Headline:** 3 requests, 43.04% cache hit, 1 finding (low). Cached_tokens absent on first routed call.

## Numbers

| | Value |
|---|---:|
| Records reviewed | 3 |
| Cache hit ratio | 43.04% |
| Output share | 3.09% |
| Measurement change | unknown |
| Prompt behavior change | unknown |
| Provider/routing change | unknown |
| Confidence | low |

## Issues

| Source | Severity | What's wrong | How to fix | How to verify |
|---|---|---|---|---|
| samples/usage/openrouter.jsonl:1 | low | cached_tokens absent on first routed call | pin provider.order or verify sticky-routing window | confirm cached_tokens increase on subsequent calls |

## Action items

- **Start with:** analyze usage logs and validate prefix stability
- **Hold off on:** make provider/routing changes without telemetry
- Rerun on warm repeated traffic.
- Cross-check cache-read counts against TTFT and dollar cost.
- Verify prefix, tool, and schema hashes don't drift.
