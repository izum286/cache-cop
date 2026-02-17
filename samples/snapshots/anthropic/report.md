# Prompt-cache audit · anthropic (Messages API)

**Headline:** 3 requests, 58.81% cache hit, 1 finding (low). Cache_creation paid once with two reads.

## Numbers

| | Value |
|---|---:|
| Records reviewed | 3 |
| Cache hit ratio | 58.81% |
| Output share | 3.47% |
| Measurement change | unknown |
| Prompt behavior change | unknown |
| Provider/routing change | unknown |
| Confidence | low |

## Issues

| Source | Severity | What's wrong | How to fix | How to verify |
|---|---|---|---|---|
| samples/usage/anthropic.jsonl:1 | low | cache_creation paid once with two reads | extend cache TTL to reduce future writes | confirm cache_read_input_tokens stay non-zero across replicas |

## Action items

- **Start with:** analyze usage logs and validate prefix stability
- **Hold off on:** make provider/routing changes without telemetry
- Rerun on warm repeated traffic.
- Cross-check cache-read counts against TTFT and dollar cost.
- Verify prefix, tool, and schema hashes don't drift.
