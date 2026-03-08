---
name: cache-cop
description: >
  Use when the user mentions LLM prompt/prefix cache misses,
  cached_tokens=0, cache_read_input_tokens/cache_creation_input_tokens,
  prompt_cache_key, cache_control/cachePoint placement, stable prefixes,
  tool/schema stability, OpenAI/Claude/Bedrock/OpenRouter
  routing, TTFT/prefill latency, or LLM cost/speed regressions on repeated long
  prompts. Use when reviewing LLM request shape changes: prompt text, message
  order, request builders, tools, schemas, response_format, provider API
  surface, model/router settings, agent loop structure, context compaction, or
  inference deployment. Use for speeding up agents only when prompt-cache
  stability, TTFT, or cache cost is central. Do not use for generic prompt
  writing, generic RAG design, token counting, or non-LLM performance.
---

# Prompt Cache Audit

Diagnose why repeated LLM prefixes stop reusing across requests, agent steps, or replicas — and decide whether prompt caching is the right lever at all before recommending changes.

## Trigger and Scope

Activate when one or more of these appear:

| Signal class | Examples |
|---|---|
| Cache telemetry | `cached_tokens=0`, `cache_read_input_tokens=0`, cache writes without reads, dropping hit ratio |
| Latency | TTFT or prefill regression on repeated long prompts; cache hits without TTFT wins |
| Cost | LLM bill jumped on a hot route; per-step agent cost rising while tools shrink |
| Request-shape change | new SDK, prompt builder, tool registry, `response_format`, image strategy, OpenRouter routing block |
| API surface | OpenAI `prompt_cache_key`, Anthropic `cache_control`, Bedrock `cachePoint`, Gemini / Qwen / DeepSeek cache fields, Azure cached-token telemetry |
| Agent loops | tools mutate per step, compaction rewrites early turns, mode switches swap system prompts |
| Self-hosted inference | multi-replica routing, KV pressure, tokenizer / chat-template drift, `max_model_len` mismatch |

Do **not** activate for: generic prompt editing without a caching concern, token counting only, response caching only (unless compared to prefix caching), RAG design without a placement question, or non-LLM frontend / backend / Kubernetes performance.

When the user says only "review" after explicitly invoking this skill, default to a cache-focused review of the available diff or repo — not a general code review.

When the user asks whether bundled samples are required, the answer is no — the skill audits project code and configs first, and the scripts accept ordinary JSON / JSONL / CSV usage logs or JSON request payloads directly.

Operating modes (auto-detect from artifacts):

- **Code audit** — repo or diff available; inspect builders, tools, schemas, history, SDK calls, routing, engine config.
- **Advisory** — no code; ask targeted diagnostics, give provider-verified guidance.
- **Agent audit** — tools, MCP, agent loop, compaction, multi-step trajectory; always add the agent stability checks.
- **Deployment audit** — self-hosted inference, Kubernetes, Docker Compose, gateways, multi-replica.

## Use-Case Map

Classify the work before auditing so you inspect the right artifacts. For a deeper role / artifact matrix, load `references/scenarios.md`.

| Scenario | Common triggers | Inspect first |
|---|---|---|
| Cost or migration audit | bill increased, provider comparison, cache discount not visible | usage logs, billing export, static / dynamic / output token estimates, provider reference |
| Prompt / code audit | `cached_tokens=0`, prompt builder changed, schema drift | prompt renderers, SDK calls, `tools`, `response_format`, JSON / schema serialization |
| Mechanics / latency audit | cache hit did not reduce cost / latency, decode dominates, unclear prefill vs. output | `references/mechanics.md`, token / TTFT traces, output length, streaming timestamps |
| Managed-router audit | OpenRouter cache writes without reads, provider fallback, sticky routing, `openrouter/auto` | OpenRouter request body, `provider` routing fields, model(s), plugins, usage metadata |
| Agent / coding-assistant audit | agent got more expensive, dynamic tools, MCP routing, compaction | agent loop, tool registry, tool selection, history compaction, per-step cache logs |
| Deployment audit | self-hosted cache misses, TTFT after scaling, multi-replica routing | `docker-compose.yml`, Helm values, Kubernetes manifests, gateway config, engine flags |
| Observability / CI audit | need cache dashboard, release guardrail, prefix smoke test | traces, dashboards, rendered prompt snapshots, prefix / tool / schema hashes |

## Project Context Gate

Run six checks before assigning severity or proposing changes. Stop early when any check definitively rules caching out.

| # | Check | Question | Drop here if no |
|---|---|---|---|
| 1 | Reusable prefix | Is a static or semi-static prefix long enough to clear the provider threshold or matter for KV reuse? | Not the right lever; recommend prompt restructuring or measurement. |
| 2 | Repeat cadence | Does the same prefix recur within cache lifetime? | Once-daily route — note and skip. |
| 3 | Exact stability | Are tools, schemas, system text, examples, images, early messages byte / token stable across target calls? | Stabilize first or rule out caching. |
| 4 | Telemetry visibility | Are cache-read / write fields, input / output tokens, TTFT, route, prompt version available? | Add measurement before recommending edits. |
| 5 | Cost shape | Does input prefill matter, or do output / decode / tool latency dominate? | Output-bound — say so; caching can't save what isn't being spent on input. |
| 6 | Safety boundary | Would broader reuse violate tenant / privacy / data residency / ZDR / side-channel rules? | Per-user isolation is the right answer; quantify the reuse cost as a trade-off. |

**Severity rule.** Severity follows the gate result, not the anti-pattern's name. A real prefix-stability bug on a cold, rare, output-bound route is `low` or `not applicable`, not `high`. Use `medium` plus an escalation condition when hotness / repeat / cost shape is unknown.

```text
critical — confirmed metric drop on a large shared prefix, expensive model, hot path
high     — likely cache killer in a hot path with partial telemetry evidence
medium   — pattern can fragment cache; impact depends on traffic shape
low      — defensive cleanup, observability addition, documentation
```

### Inputs

The repository, prompt code, and deployment configuration are the primary audit inputs. Evidence artifacts — provider usage logs, billing exports, rendered JSON request payloads, prompt snapshots, per-step agent traces, gateway route logs, latency traces — are supporting inputs for confirmation and measurement.

Bundled samples in `samples/` are demo and regression-test data only. Do not require users to convert production data into the repository's sample layout before auditing. Scripts also accept ordinary JSON / JSONL / CSV usage logs or JSON request payloads directly.

This skill does not capture or intercept live traffic by itself. If telemetry is needed, ask the user to export or redact representative records from their own logging, tracing, provider dashboard, or billing pipeline.

## Provider Detection

Search SDK imports, base URLs, model names, deploy manifests, engine flags. Wrapper / router references take precedence over raw provider references when both signals appear.

| Signal | Detected | Load |
|---|---|---|
| `openrouter`, `openrouter.ai/api/v1`, `OPENROUTER_API_KEY`, `openrouter/auto` | OpenRouter | `references/openrouter.md` |
| `AzureOpenAI`, `AZURE_OPENAI_ENDPOINT`, `api-version` | Azure OpenAI | `references/azure-openai.md` |
| `openai`, `responses.create`, `chat.completions`, `prompt_cache_key`, `prompt_cache_retention` | OpenAI | `references/openai.md` |
| `bedrock-runtime`, `Converse`, `InvokeModel`, `cachePoint`, `CacheReadInputTokens`, `CacheWriteInputTokens` | Amazon Bedrock | `references/bedrock.md` |
| `anthropic`, `messages.create`, `cache_control` | Anthropic | `references/anthropic.md` |
| `deepseek`, `api.deepseek.com`, `prompt_cache_hit_tokens` | DeepSeek | `references/deepseek.md` |
| `google.genai`, `vertexai`, `CachedContent` | Gemini | `references/gemini.md` |


Ambiguous OpenAI SDK + custom `base_url`? Treat as a wrapper (Azure, OpenRouter, Bedrock proxy etc.) and load the wrapper reference first. Ask which provider when detection fails outright.

## Audit Workflow

Code and config first; telemetry second.

1. Scan the repo for provider calls, cache controls, routing hints, prompt builders, tool registries, structured-output schemas, history management, and self-hosted engine signals — `scripts/scan_repo.py` when useful.
2. Map prompt families, hot routes, agent loops, deployment paths; separate hot repeated paths from rare / one-off / output-bound ones.
3. Inspect the request path in code: rendering, system / developer messages, tool ordering, schema serialization, compaction, SDK params.
4. Inspect config / deploy artifacts: env defaults, feature flags, routers, Docker Compose, Kubernetes, Helm, engine flags, replica topology.
5. Run the Project Context Gate per route.
6. Apply the **Freshness Gate** before any exact provider claim — open the loaded provider reference, verify official docs when browsing is available. Treat bundled references as heuristics. If browsing isn't available, mark provider facts unverified and avoid exact numbers.
7. Walk anti-patterns (next section). Mark each as applicable / conditional / not applicable.
8. Ask for usage logs, rendered payloads, traces only after code / config context shows what evidence is needed next.
9. Produce findings using the Output Contract.
10. Verify before claiming a fix works (see Verification).

## Anti-Patterns

Eleven rules organized into five domains. Every rule shares the same compact template:

> **XX-NN — short name**
> Symptom · Search · Fix · Verify

### Prefix Stability (PS-01 .. PS-04)

The cacheable anchor — `system + tools + response_format + first stable messages` — must render identically across users, timestamps, and equivalent requests. Most cache misses on managed APIs trace back here.

**PS-01 — Volatile data in the prefix**
Symptom: dynamic values render before the cacheable anchor; every request looks unique to the provider.
Search: `datetime`, `time`, `uuid`, `session_id`, `request_id`, `trace_id`, `run_id`, `user.name`, `user_id`, `tenant`, `company`, `cwd`, `git status`, `platform` inside `system`, tool schemas, or first user message.
Fix: keep the prefix per-render identical; push the dynamic surface into a later user message or provider-supported metadata.

```python
# wrong — prefix differs by user and by the second
def render_system(user, base):
    return f"Today: {datetime.now()}. You help {user.name}. {base}"

# right — anchor never changes; dynamic context is appended downstream
def render_system(base):
    return base

def render_user(query, user):
    ctx = f"[ctx: time={datetime.now()}, user={user.name}]"
    return f"{ctx} {query}"
```

Verify: render the anchor for N distinct users / timestamps, hash, expect one fingerprint.

**PS-02 — Non-deterministic tools, schemas, or JSON serialization**
Symptom: tool list ordering or schema text changes between requests; `cached_tokens` stays low despite a long prefix.
Search: `json.dumps` without `sort_keys=True`; dict / set iteration into tool arrays; registry order tied to import timing; dynamic `request_id` or timestamps inside `response_format` or JSON schema constants.
Fix: sort tools by stable name; serialize schemas with a canonical key order; keep request-scoped metadata out of cacheable schemas.

```python
tool_list = [registry[name] for name in sorted(registry)]
schema_text = json.dumps(response_format, ensure_ascii=False, sort_keys=True)
```

Verify: byte-compare the rendered `tools` and `response_format` across three requests; cached-token fields should climb after the second.

**PS-03 — Template, whitespace, media, or SDK drift**
Symptom: two code paths render the "same" prompt with different bytes; cache hits regress after an SDK or template change.
Search: duplicated system templates, hand-rolled string concatenation alongside a templated renderer, inconsistent `.strip()`, different markdown wrappers, varying image `detail`, signed URLs with rotating query strings, URL-vs-base64 differences.
Fix: one canonical render function for the cacheable anchor; normalize whitespace; pin image representation and detail level.
Verify: `scripts/diff_prefix.py` between two recent rendered requests on the same route; expect no early-prefix divergence.

**PS-04 — History mutation instead of append-only growth**
Symptom: an early message changes mid-session; the prefix chain shatters; cached tokens reset after summarization or pop.
Search: `summarize`, `compaction`, `truncate`, `messages.pop`, `del messages`, replacement of early turns, system prompt mutation mid-session.
Fix: preserve a head anchor; mutate the tail only. If the anchor alone overruns the budget, fail closed or split the route — never silently drop it.

```python
def trim_to_budget(messages, budget, count_tokens):
    head = messages[:2]                       # system + first stable turn
    tail = list(messages[2:])
    while tail and count_tokens(head + tail) > budget:
        tail.pop(0)
    if count_tokens(head + tail) > budget:
        raise ValueError("stable anchor exceeds context budget")
    return head + tail
```

Verify: simulate N steps of history growth; the first-two-message hash must stay constant.

### Agent Loop (AG-01, AG-02)

Long agent trajectories are most vulnerable to prefix invalidation. Stable early tokens matter more than shaving a few tools off the current request.

**AG-01 — Dynamic tool set inside an agent loop**
Symptom: `tools_count` shifts most steps; `prefix_hash` flips when the tool set changes; the agent got more expensive after selecting fewer tools.
Search: per-step tool retrieval, `get_active_tools`, `select_tools`, dynamic MCP listing, feature-flagged tool inclusion, subagent / tool descriptions in non-deterministic order.
Fix options: keep a compact stable tool list sorted by name; route to fixed tool bundles before the loop; use provider-supported `allowed_tools` / tool search / deferred loading (after checking current docs); self-hosted masking or constrained decoding. Don't move tool definitions into user messages as a cache workaround unless current docs explicitly support it.
Verify: per-step log shows constant tool-name hash; cached-token fields rise as the trajectory grows.

**AG-02 — Mode switching or framework injection rewrites the prefix**
Symptom: plan / debug / read-only modes swap the system prompt or strip write tools; framework metadata (`run_id`, `trace_id`, `cwd`, platform, timestamps, git status) lands before the cacheable anchor.
Search: `PLAN_SYSTEM_PROMPT`, `DEBUG_SYSTEM_PROMPT`, role-specific system replacements, framework code that injects environment metadata at the top of messages.
Fix: keep base instructions and tool definitions stable; carry mode state and dynamic environment facts in later messages or in provider-supported metadata.
Verify: render two consecutive steps with the same mode and a third with a switched mode — only the mode-marker bytes change; the rest stays byte-identical.

### Routing (RT-01, RT-02)

Stable prompts can still miss if requests land where the cache doesn't live, or if fan-out beats cache creation to the worker.

**RT-01 — Cache-blind routing across replicas or providers**
Symptom: identical workloads behave differently by pod or route; TTFT spikes after replica scale; OpenRouter cache writes without reads.
Search: round-robin gateways, autoscaling LLM pods without sticky routing, multiple inference replicas with no prefix-aware hashing, OpenRouter `provider.order` / fallback / `openrouter/auto` reshuffling on a hot route.
Fix: managed APIs — use provider-supported cache key or routing hint (verify current docs); OpenRouter — review sticky routing, `provider.order`, `provider.only`, `provider.ignore`, fallback policy, first-message conversation identity; self-hosted — prefix-aware routing, consistent hashing, or gateway that hashes the stable prefix; route by prefix family while watching hot spots.

**RT-02 — Parallel fan-out on a cold prefix**
Symptom: a concurrent batch on a shared prefix all pays full prefill; the first cache read shows up only after the wave clears.
Search: `asyncio.gather`, `Promise.all`, `ThreadPoolExecutor`, map / reduce fan-out on a shared prefix without warm-up.
Fix: warm the cache with one safe call before the batch (tools disabled or constrained to no-op behavior, no external side effects), then fan out. If no safe warm call exists, skip the warm step and document the trade-off.

```python
async def fanout(prefix, queries):
    await warm_cache(prefix, max_tokens=1, tools=[])   # one cheap call, no side effects
    return await asyncio.gather(*(call(prefix, q) for q in queries))
```

Verify: usage metadata on the second wave shows cached tokens > 0; don't infer from latency alone.

### Cache Lifetime (CL-01, CL-02)

Stable prefixes still fail when they expire, get evicted, or get over-isolated.

**CL-01 — Lifetime, KV budget, or eviction mismatch**
Symptom: prefix is stable, hit rate still low; sparse traffic between calls; many prefix families; low KV capacity; eviction metrics climbing.
Search: long pauses between calls vs. configured TTL; oversized `max_model_len` against observed p99; large number of distinct prefix families on a self-hosted engine.
Fix: managed APIs — align TTL / retention to traffic cadence; self-hosted — size KV cache for the working set, not the model's advertised context; reduce prefix families if reuse is being split too thin.
Verify: cache writes vs. reads converge after the adjustment; eviction or block-pressure metrics drop on self-hosted.

**CL-02 — Over-isolation fragments shareable prefixes**
Symptom: a per-user or per-request cache key fragments reuse that the trust boundary doesn't actually require.
Search: per-request `cache_salt`, per-user cache keys, `user_id` in cache key, tenant-specific routing keys, cache namespace by session, full isolation flags added defensively.
Fix: pick the coarsest safe trust boundary; prefer route / team / tenant prefixes when the data model permits; use per-user isolation when compliance or side-channel risk requires it. Report the expected reuse loss as a trade-off, not a bug.
Verify: re-check whether the boundary is truly required, not assumed; if isolation must stay, quantify the cache-efficiency cost in the finding.

### Experiments (EX-01)

**EX-01 — A/B tests, variants, or settings fragment reuse**
Symptom: many small caches instead of one big one; per-variant hit rates look acceptable but the aggregate doesn't move.
Search: `variant`, `experiment`, `feature_flag`, prompt-version-per-request, varying reasoning effort, varying tool choice, randomized few-shot examples, `openrouter/auto`, multiple `models`, `provider.order` changes per request.
Fix: test sequentially where possible; move differences after the stable prefix; bucket by stable route / version and measure each bucket separately rather than mixing into one cache family.
Verify: each bucket shows its own healthy hit rate; aggregate hit rate makes sense as a weighted sum.

## Audit Playbooks

Use these as starting paths for common support and review requests. Still run Provider Detection and the Freshness Gate before exact claims.

- **OpenAI `cached_tokens=0`**: check prompt length / threshold, first-prefix drift, `responses.create` vs. Chat usage fields, `prompt_cache_key` granularity, `prompt_cache_retention`, output-token dominance, and whether an OpenAI-compatible wrapper is actually in use.
- **Claude / Bedrock / OpenRouter writes without reads**: distinguish cache creation / write fields from read / hit fields, then inspect cache breakpoint placement, dynamic content before the breakpoint, TTL / retention, model / region / API support, fallback routing, and actual routed provider / model.
- **Dynamic tools in long agent loops**: compare `tools_count`, sorted tool-name hash, `prefix_hash`, mode state, and cache fields per step. Prefer stable route-level tool bundles, sorted schemas, provider-supported allowed tools / tool search / deferred loading, or self-hosted masking after checking current docs.
- **High hit rate but no savings**: separate input savings from total cost and final latency. Check output-token share, decode time, external tool time, TPM / rate-limit behavior, and cache read / write pricing assumptions before changing prompt layout.
- **OpenAI-compatible wrapper ambiguity**: if `base_url`, Azure, OpenRouter, Bedrock, DashScope / Qwen, or another gateway wraps an OpenAI SDK, load the wrapper reference first and do not recommend direct OpenAI-only parameters until the wrapper docs support them.
- **Self-hosted multi-replica miss**: inspect gateway / service routing, prefix-aware hashing, tokenizer / chat-template drift, `max_model_len`, KV block pressure, eviction metrics, and route / replica-level hit metrics.
- **New provider docs project-change audit**: compare the new provider facts against current code, references, evals, and tests. Recommend no code change when the project already encodes the behavior or when the fact is not applicable to this provider path.

## Agent Tool Stability

Run these whenever the app is an agent, coding assistant, MCP client, or multi-step workflow.

Per-step logging (minimum):

- `prefix_hash` of canonical `system + tools + response_format + first stable messages`
- provider cache-read field (`cached_tokens`, `cache_read_input_tokens`)
- cache creation / write field where available
- `tools_count` and a sorted tool-name hash
- prompt version and route
- TTFT / prefill latency
- mode state
- compaction event and strategy
- output tokens and final-token latency when latency is the symptom

Alert when TTFT climbs on late steps, the prefix hash changes unexpectedly, the tool count shifts inside a long trajectory, or cached tokens reset right after tool selection or compaction.

Diagnostic helper (use HMAC for any fingerprint that escapes the process — production telemetry, tenant-derived hashes):

```python
import hashlib
import hmac
import json

def anchor_digest(*, system, tools=None, response_format=None, early_messages=None, key=b""):
    """Return a short HMAC-SHA256 fingerprint of the cacheable anchor.

    Pass `key=b""` only for ad-hoc local diagnostics; supply a real key for telemetry.
    """
    payload = json.dumps(
        {
            "system": system,
            "tools": tools or [],
            "response_format": response_format,
            "early_messages": early_messages or [],
        },
        ensure_ascii=False,
        sort_keys=True,
    ).encode()
    mac = hmac.new(key, payload, hashlib.sha256) if key else hashlib.sha256(payload)
    return mac.hexdigest()[:12]
```

Its only guardrail, not a provider tokenizer. Provider usage metadata stays authoritative.

## Output Contract

Pick the smallest contract that answers the user's actual question. Don't bury the decision under generic prompt-cache advice.

### Named Contracts

Pick one before writing the answer:

- **Quick triage** — use when artifacts are incomplete. Answer with provider / engine guess, most likely cache blocker, evidence needed next, and one safe next command or artifact request.
- **Code audit findings** — use when code is available. Lead with a decision summary, then file-line findings in the report format, then clean checks, then verification commands.
- **Provider migration risk** — use when moving between OpenAI, Anthropic, Bedrock, OpenRouter, Azure OpenAI, Gemini, Qwen, DeepSeek, or self-hosted engines. Compare cache semantics, usage fields, prefix layout risk, routing risk, and cost assumptions before recommending edits.
- **Agent loop audit** — use for coding assistants, MCP clients, tool-using agents, compaction, mode switching, or long multi-step workflows. Always inspect stable tools, early messages, per-step prefix hashes, cache fields, output tokens, and compaction events.
- **Deployment audit** — use for self-hosted inference, Kubernetes, Docker Compose, gateways, autoscaling, or multi-replica inference. Treat routing locality and KV budget as first-class causes, not secondary deployment details.
- **Not worth caching** — use when the Project Context Gate fails or the evidence shows output decode, external tool latency, rate limits, or privacy isolation dominate. Say what should change instead and what evidence would reopen prompt-cache work.

### Decision Summary Block

Use whenever recommending project work:

```text
Measurement change:
Prompt behavior change:
Provider/routing change:
Confidence:
Do first:
Do not do yet:
```

Prefer split decisions over a blanket "yes" when the safe next step is measurement (e.g., `Measurement change: yes`, `Prompt behavior change: pilot only after telemetry`, `Provider/routing change: no, not yet`). For "do we need to change the project?" questions, lead with `Change needed: yes`, `Change needed: no`, or `Change needed: unknown until <specific evidence>`.

### Evidence-Bearing Finding

Every actionable finding makes uncertainty visible:

```text
source | severity | provider/engine | issue | evidence | evidence_type | confidence | impact_condition | cache impact | safe_first_action | fix | validation | do_not_do_yet
```

Use evidence types: `confirmed from code`, `confirmed from telemetry`, `provider-doc hypothesis`, or `needs validation`. State impact as a condition ("matters if this route is hot, repeated, and has a long stable prefix") instead of asserting guaranteed savings.

Compact alternative when prose around it carries evidence and uncertainty:

```text
file:line | severity | provider/engine | issue | cache impact | fix | validation
```

### Three-Bucket Result Split

Keep findings organized so the user can act on them:

1. **Confirmed** — supported by code / config / telemetry and applicable to the route under review.
2. **Hypotheses** — plausible risks needing usage logs, rendered payloads, route metrics, or docs before severity rises.
3. **Not applicable** — generic cache advice the project context rules out (rare route, no shared prefix, output-bound).

When structure is the issue, include compact before / after prompt layout in the report. For a full reusable handoff, load `references/report-template.md`.

### Output Language

Answer in the user's language. Keep API / field names verbatim (`cached_tokens`, `cache_control`, `cachePoint`, `prompt_cache_key`, `response_format`, `TTFT`); explain meaning in their language.

### Quality Bar

Before sending the response:

- The decision the user asked for is answered (change / no change / evidence missing).
- Wrapper / router references take precedence over raw provider references when both apply.
- No exact provider claims without the relevant reference loaded and the Freshness Gate cleared.
- Cache miss, cache-write-without-read, uneconomic cache hit, decode-bound latency, rate-limit pressure, and privacy-driven isolation are distinguished — not conflated.
- Every recommendation carries a falsifying check (prefix fingerprint diff, provider usage field, route metric, cost / latency split).
- No cache controls / keys / routing hints proposed when the Project Context Gate ruled caching out.

## Verification

A fix isn't done until one of these is true:

| Fix class | Pass condition |
|---|---|
| Prefix stability | Anchor fingerprint stable across users / timestamps / equivalent requests |
| Provider semantics | Repeated calls show cache-read / cached-token fields climbing per the provider reference |
| Routing | Repeated prefix families land on the intended route and cache metrics improve by route |
| Self-hosted | Prefix-cache hit metrics rise and KV-block pressure drops under a representative workload |

Recommend a CI / smoke check that renders representative prompts and fails when the cacheable prefix changes unexpectedly.

The audit itself is complete when:

- Each applicable anti-pattern has been classified as confirmed / hypothesis / not applicable for the routes under review.
- Every confirmed or hypothesis finding carries an evidence type and a falsifying validation step.
- The decision summary block answers the user's actual question, or explicitly names the missing evidence that would unlock the answer.
- For agent audits, per-step `prefix_hash`, `tools_count`, and cache fields are accounted for on the critical trajectory.
- For deployment audits, routing locality and KV-budget have been treated as first-class causes — not deferred to "infra".

When none of these can be satisfied with the available artifacts, deliver the Quick triage contract and name the next evidence the user should produce.

## Advisory Questions

When no codebase is available, ask only the missing questions needed to diagnose:

1. Which provider or inference engine?
2. Is this a cost / migration, prompt / code, agent, deployment, or observability / CI audit?
3. What artifacts are available: request code, rendered prompts, usage logs, deployment config, dashboards, evals?
4. What are median / p95 input tokens, static prefix tokens, output tokens, and agent steps?
5. What cache usage fields are visible in responses?
6. Are there multiple replicas or gateways?
7. Are tools / schemas stable across requests and agent steps?
8. Is history append-only, compacted, or summarized?
9. Are cache keys, salts, or routing hints per-user / per-request or shared by prefix family?
10. What changed before the cache hit rate or TTFT regressed?

## References and Scripts

**Load only the reference the detected scenario needs.**

| Scenario | Reference |
|---|---|
| Cost, migration, output-share, TTL / write-premium | `references/cost-model.md` |
| Prefill vs. decode, KV reuse, latency mechanics | `references/mechanics.md` |
| Release, incident, deploy, monitoring | `references/runbook.md` |
| OpenRouter or managed router routing / cache | `references/openrouter.md` |
| Agents, coding assistants, MCP, dynamic tools | `references/agent-loop.md` |
| Full role / artifact matrix when scope is unclear | `references/scenarios.md` |
| Reusable handoff deliverable | `references/report-template.md` |
| Machine-readable rule catalog | `references/antipatterns.json` |

Provider files are in `references/anthropic.md`, `references/openai.md`, `references/bedrock.md`, `references/azure-openai.md`, `references/deepseek.md`, `references/gemini.md`. Use only the one the Provider Detection table picks.

**Bundled scripts** — small, stdlib-only, no network. Explain what each reads / writes before running, choose a targeted scan when the repo is large, and ask before pointing them at secrets, env files, or production exports.

| Script | Purpose |
|---|---|
| `scripts/scan_repo.py` | Find provider calls, cache-control hints, routing signals, self-hosted engine flags before choosing references. |
| `scripts/lint_request.py` | Inspect rendered JSON request payloads (Chat-style `messages`, Responses-style `input`/`instructions`) for volatile early content, unsorted tools, dynamic schema fields. |
| `scripts/diff_prefix.py` | Byte-level diff of two rendered request payloads; finds first divergent prefix location. Use `--canonical-json` only when sorted-key normalization is intentional. |
| `scripts/summarize_usage.py` | Aggregate JSON / JSONL / CSV usage logs across OpenAI, Anthropic-compatible, Bedrock-style, OpenAI-compatible cache fields. `--jsonl-normalized` for downstream dashboards. |
| `scripts/roi.py` | Input-only and total-cost estimates from static / dynamic / output tokens, hit rate, request count, and explicit prices. |
| `scripts/render_report.py` | Combine usage summary and one-line findings into a Markdown or JSON audit report. |

These scripts are audit aids, not provider tokenizers or billing truth — provider usage and billing exports stay authoritative.

**Freshness Gate.** Provider facts (prices, cache discounts, write premiums, minimum cacheable tokens, TTLs, usage field names, model availability, cache-control semantics) drift. Before asserting any exact number, open the loaded provider reference and verify the official source. When browsing isn't available, mark the claim unverified and drop exact figures. Never copy prices or model names from articles or blog posts as current truth.
