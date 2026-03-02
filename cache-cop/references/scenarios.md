# Prompt Cache Audit Scenarios

Open this file when the user asks how the skill applies in practice, when the codebase mixes many artifact types, or when the audit scope isn't obvious yet.

## Cost and Migration

Load `references/cost-model.md`.

Who's asking:
- AI engineer estimating production cost
- AI platform lead choosing providers or models
- team migrating between managed APIs or to self-hosted inference
- FinOps or backend lead investigating an LLM bill

Symptoms:
- cache hit rate is high, total cost stays high
- price-list comparison doesn't match the bill
- static prompt is large, output share unknown, or traffic is bursty
- provider migration changed cache behavior

Inspect:
- `cached_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, output tokens
- API usage responses and billing exports
- prompt layout before and after migration
- estimates for static tokens, dynamic tokens, output tokens, hit rate, TTL, write premium
- `references/mechanics.md` when latency or throughput is in scope
- provider references, verified against official docs before exact claims

## Managed Router and OpenRouter

Load `references/openrouter.md`. When the symptom is financial, load `references/cost-model.md` too.

Who's asking:
- backend engineer configuring model/provider fallback
- AI engineer using OpenRouter as an OpenAI-compatible gateway
- agent developer using `openrouter/auto` or model fallbacks
- platform lead balancing cache locality, price, latency, and privacy policy

Symptoms:
- OpenRouter shows cache writes but few cache reads
- `cache_control` works direct-to-provider but behaves differently through OpenRouter
- `provider.order`, `provider.only`, `provider.ignore`, ZDR, or account provider settings were added
- provider or model fallback shifts cache hit rate
- `openrouter/auto` or `models` routing lands repeated prompts on different routes

Inspect:
- `provider` routing object, account provider preferences, fallback policy
- OpenRouter base URL, SDK, request body, model slug
- `cache_control` placement and provider-specific compatibility
- `messages`, especially first system/developer and first non-system message
- `cached_tokens`, `cache_write_tokens`, cache discount, response model/provider metadata
- `plugins`, especially context compression

## Prompt and Request Code

Start from `SKILL.md` anti-patterns. For release gates or incidents, also load `references/runbook.md`.

Who's asking:
- prompt engineer maintaining templates
- backend engineer building LLM requests
- release engineer reviewing prompt-affecting changes
- SDK/integration engineer

Symptoms:
- the request looks identical to a human but not to the provider
- `cached_tokens` stays zero on repeated calls
- hit rate dropped after an SDK, template, or schema change
- structured output or tool definitions are large

Inspect:
- canonical render functions and whitespace normalization
- prompt builders and template files
- tool registry and tool serialization
- SDK client calls and request wrappers
- `response_format`, JSON schema, Pydantic/dataclass serialization
- multimodal input representation, image detail, signed URLs
- Bedrock `cachePoint` / model-family cache-control placement

## Agent and Coding Assistant

Load `references/agent-loop.md`.

Who's asking:
- coding-assistant developer
- agent developer
- MCP/tooling engineer
- AI engineer designing tool routing
- framework engineer owning compaction or summarization

Symptoms:
- `tools_count` or `prefix_hash` changes on every step
- the agent got more expensive after selecting fewer tools
- long trajectories see rising TTFT or repeated prefill
- plan/debug/read-only modes swap the system prompt or tool list
- compaction rewrites early messages
- many concurrent agent workflows evict useful KV blocks before reuse

Inspect:
- per-step `cached_tokens` / cache-read fields, `prefix_hash`, `tools_count`, tool-name hash
- agent loop and per-step request construction
- MCP registry and tool descriptions
- dynamic tool retrieval, semantic routing, allowed tools, tool search, deferred loading
- subagent / tool bundle routing
- history truncation, tool-result compaction, summarization
- serving scheduler / KV traces for self-hosted multi-agent workloads

## Deployment and Self-Hosted Inference

Load `references/runbook.md` and the relevant engine/provider reference.

Who's asking:
- inference engineer tuning KV cache capacity
- platform / SRE engineer running self-hosted inference
- team scaling from one model replica to many

Symptoms:
- TTFT spikes after changing replica count or gateway routing
- stable prompts still miss after scaling replicas
- KV cache evicts hot prefixes
- identical workloads behave differently by pod or route
- `max_model_len` is much larger than real p99 input length

Inspect:
- KV block pressure, eviction metrics, prefix-cache hit/query metrics, TTFT by route
- `docker-compose.yml`, `Dockerfile`, Helm values
- inference engine arguments: prefix caching, max model length, GPU memory utilization, tensor/pipeline parallel settings
- Kubernetes `Deployment`, `Service`, `Ingress`, HPA, gateway, service mesh config
- load balancer routing policy, sticky routing, prefix-aware routing, consistent hashing
- tokenizer and chat-template stability for self-hosted models
- prefill vs decode split from `references/mechanics.md`
- cache salt, cache namespace, user/tenant isolation policy

## Observability and CI

Load `references/runbook.md`.

Who's asking:
- release engineer
- observability engineer
- platform owner adding cache guardrails
- QA engineer

Symptoms:
- a release changed prompt behavior without an explicit prompt diff
- cache regressions show up only after the bill or latency alert
- no test protects the stable prefix
- no dashboard separates cacheable traffic from unique traffic

Inspect or add:
- prefix fingerprint for `system + tools + stable early messages`
- rendered prompt snapshots for representative routes
- cache ratio, cache writes vs reads, TTFT / prefill latency, output-token cost share
- tool/schema hash and prompt version dimensions
- first-token and final-token timestamps
- CI smoke test that fails when the cacheable prefix changes unexpectedly
- deploy, SDK, model, prompt version, route, replica, region dimensions

## Source Map

- Cost article → cost comparison, provider migration, effective cost, output share, TTL / write premium, hidden migration tax.
- Mechanics article → KV reuse, prefill vs decode, saved compute vs output/decode limits.
- Anti-patterns article → volatile prefix data, template drift, schema/tool serialization, append-only history, routing, parallel fan-out, cache lifetime.
- Agents article → dynamic tool selection, stable tool bundles, masking / allowed tools / tool search / deferred loading, compaction, per-step diagnostics.

## Triage Shortcut

When the user offers a single symptom:

- **`cached_tokens=0`** → start with prompt prefix and tool/schema stability.
- **Cost increased** → start with usage fields and output share, then prompt stability.
- **TTFT after scaling** → start with routing and KV-cache capacity.
- **Agent got expensive** → start with dynamic tools and history mutation.
- **Cache hit but latency still high** → split TTFT/prefill from decode/output and tool time.
- **OpenRouter cache miss** → start with provider sticky routing, first-message identity, fallback/model routing, and cache read/write usage fields.
- **Self-hosted engine config** → start with deployment files, replica routing, `max_model_len`, and KV metrics.
