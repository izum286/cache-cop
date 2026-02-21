---
name: cache-cop
description: >
  Use when the user mentions LLM prompt/prefix cache misses,
  cached_tokens=0, cache_read_input_tokens/cache_creation_input_tokens,
  prompt_cache_key, cache_control placement, stable prefixes,
  tool/schema stability, OpenAI/Claude routing, TTFT/prefill latency,
  or LLM cost/speed regressions on repeated long prompts. Use when reviewing
  LLM request shape changes: prompt text, message order, request builders,
  tools, schemas, response_format, provider API surface, model settings,
  agent loop structure, or context compaction. Do not use for generic
  prompt writing, generic RAG design, or token counting.
---

# Prompt Cache Audit

Diagnose why repeated LLM prefixes stop reusing across requests, agent steps, or replicas — and decide whether prompt caching is the right lever at all before recommending changes.

## Trigger and Scope

Activate when one or more of these appear:

| Signal class | Examples |
|---|---|
| Cache telemetry | `cached_tokens=0`, `cache_read_input_tokens=0`, cache writes without reads, dropping hit ratio |
| Latency | TTFT or prefill regression on repeated long prompts |
| Cost | LLM bill jumped on a hot route |
| Request-shape change | new SDK, prompt builder, tool registry, `response_format` |
| API surface | OpenAI `prompt_cache_key`, Anthropic `cache_control` |
| Agent loops | tools mutate per step, compaction rewrites early turns |

Do **not** activate for: generic prompt editing without a caching concern, token counting only, response caching only, or non-LLM performance.

## Project Context Gate

Run these checks before assigning severity or proposing changes. Stop early when any check definitively rules caching out.

| # | Check | Question | Drop here if no |
|---|---|---|---|
| 1 | Reusable prefix | Is a static or semi-static prefix long enough to clear the provider threshold or matter for KV reuse? | Not the right lever; recommend prompt restructuring. |
| 2 | Repeat cadence | Does the same prefix recur within cache lifetime? | Once-daily route — note and skip. |
| 3 | Exact stability | Are tools, schemas, system text, early messages byte-stable across calls? | Stabilize first or rule out caching. |
| 4 | Telemetry visibility | Are cache-read/write fields available? | Add measurement before recommending edits. |
| 5 | Cost shape | Does input prefill matter, or do output/decode dominate? | Output-bound — say so. |

**Severity rule.** Severity follows the gate result, not the anti-pattern's name. A real prefix-stability bug on a cold, rare, output-bound route is `low`, not `high`.

## Provider Detection

Search SDK imports, base URLs, model names. Wrapper references take precedence over raw provider references when both signals appear.

| Signal | Detected | Load |
|---|---|---|
| `openai`, `responses.create`, `chat.completions`, `prompt_cache_key` | OpenAI | `references/openai.md` |
| `anthropic`, `Anthropic(`, `messages.create`, `cache_control` | Anthropic | `references/anthropic.md` |

More provider references are coming.

## Anti-Patterns (initial set)

### PS-01 — Volatile prefix

A timestamp, `request_id`, or other dynamic value sits ahead of the cacheable prefix. Every request renders a different first few tokens, so the cache lookup hashes differently every time. Cache hit ratio stays at zero or near-zero even on hot routes.

**Fix.** Push request IDs, timestamps, user-specific values past the static prefix. The cacheable bytes go first; the dynamic suffix goes last.

**Validation.** Render two repeated requests and confirm the cacheable prefix hash is stable. Run `scripts/diff_prefix.py` over two rendered payloads.

### PS-02 — Unstable tool/schema order

Tools or response-format schemas are emitted in registry order rather than sorted by name. Plugin load timing or import order changes the byte representation, fragmenting the cache.

**Fix.** Sort tool definitions by `function.name` before serialization. Canonicalize JSON for schemas (sorted keys).

**Validation.** Byte-diff two rendered requests across runs.

## Scripts

- `scripts/scan_repo.py` — grep a project tree for provider SDK calls.
- `scripts/lint_request.py` — flag layout anti-patterns in a rendered request.
- `scripts/diff_prefix.py` — find the byte offset where two rendered requests first diverge.
- `scripts/summarize_usage.py` — parse provider usage logs.
- `scripts/roi.py` — cost-delta math from token assumptions.
- `scripts/render_report.py` — assemble findings into a markdown audit card.

## References

- `references/openai.md`
- `references/anthropic.md`
