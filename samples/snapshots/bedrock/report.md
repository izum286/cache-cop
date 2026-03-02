# Prompt-cache audit · bedrock (Converse API)

**Headline:** 3 requests, 57.28% cache hit, 1 finding (low). CacheWriteInputTokens dominates first request.

## Numbers

| | Value |
|---|---:|
| Records reviewed | 3 |
| Cache hit ratio | 57.28% |
| Output share | 3.33% |
| Measurement change | unknown |
| Prompt behavior change | unknown |
| Provider/routing change | unknown |
| Confidence | low |

## Issues

| Source | Severity | What's wrong | How to fix | How to verify |
|---|---|---|---|---|
| samples/usage/bedrock.jsonl:1 | low | CacheWriteInputTokens dominates first request | reuse cachePoint across requests in same region | confirm CacheReadInputTokens rise on warm calls |

## Action items

- **Start with:** analyze usage logs and validate prefix stability
- **Hold off on:** make provider/routing changes without telemetry
- Rerun on warm repeated traffic.
- Cross-check cache-read counts against TTFT and dollar cost.
- Verify prefix, tool, and schema hashes don't drift.
