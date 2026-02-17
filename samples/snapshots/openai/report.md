# Prompt-cache audit · openai (Responses API)

**Headline:** 4 requests, 67.36% cache hit, 1 finding (low). Cold request has zero cached tokens.

## Numbers

| | Value |
|---|---:|
| Records reviewed | 4 |
| Cache hit ratio | 67.36% |
| Output share | 6.92% |
| Measurement change | unknown |
| Prompt behavior change | unknown |
| Provider/routing change | unknown |
| Confidence | low |

## Issues

| Source | Severity | What's wrong | How to fix | How to verify |
|---|---|---|---|---|
| samples/usage/openai.jsonl:1 | low | cold request has zero cached tokens | warm repeated prefix before measuring steady state | confirm warm cached_tokens increase |

## Action items

- **Start with:** analyze usage logs and validate prefix stability
- **Hold off on:** make provider/routing changes without telemetry
- Rerun on warm repeated traffic.
- Cross-check cache-read counts against TTFT and dollar cost.
- Verify prefix, tool, and schema hashes don't drift.
