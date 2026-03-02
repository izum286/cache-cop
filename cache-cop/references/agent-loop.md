# Agent Loop Cache Strategy

Open this file when auditing agents, coding assistants, MCP clients, dynamic tool selection, mode switching, or context compaction.

## The Core Rule

Don't optimize one agent step in isolation. In long trajectories, stable early tokens matter more than shaving a few tool definitions off the current request.

Before changing tool strategy, estimate the cost of a late-step cache miss:

```text
late_step_miss_cost ~= late_input_tokens * uncached_input_price
late_step_hit_cost  ~= late_input_tokens * cached_input_price
```

Use provider docs for current prices and cache semantics. For self-hosted inference, translate miss cost into prefill compute, TTFT, and throughput.

## Strategy Table

| Situation | Prefer | Watch for |
|---|---|---|
| Up to 10 compact tools | stable full tool list | sort tools and schema keys |
| 10–50 tools, self-hosted decoding control | stable tools plus masking / constrained decoding | mask only at tool-name selection positions |
| Many tools, managed API | provider-supported `allowed_tools`, `tool_search`, or deferred loading | verify current provider semantics before claiming cache safety |
| Independent product domains | route before the agent loop to fixed tool bundles | define a fallback for cross-domain tasks |
| Prototype, short agent, cheap model | dynamic tool selection can be acceptable | keep monitoring so it doesn't quietly ship into long trajectories |
| Per-step RAG over tool docs | avoid if it rewrites early `tools` | safe only when retrieved tools are appended or provider-supported |

## Dynamic Tool Selection Smell

Symptoms:
- raw prompt tokens went down but total cost or TTFT went up
- `tools_count` shifts on most steps
- `prefix_hash` changes when the tool set changes
- tool calls in history refer to tools that later disappear
- the agent has 15+ steps or a high input/output ratio

Safer alternatives:
- route-level fixed tool bundles selected before the agent loop
- stable compact tool list sorted by name
- provider-supported tool search or deferred loading
- provider-supported allowed tools, separate from the full tool list
- self-hosted masking / constrained decoding

Don't move tool definitions into user messages as a cache workaround unless current provider docs explicitly support the pattern.

## Mode Switching

Plan / debug / read-only modes shouldn't swap the base system prompt or rewrite the tool list.

Safer patterns:
- keep base instructions stable
- use allowed-tools or masking for dynamic permissions
- express mode state in a later message or supported metadata
- add mode-enter / mode-exit tools when that preserves the stable prefix

Audit for:
- injected `cwd`, `platform`, date, git status, run IDs, or trace IDs landing before the cacheable prefix
- read-only mode implemented by removing write tools from `tools`
- `PLAN_SYSTEM_PROMPT`, `DEBUG_SYSTEM_PROMPT`, or role-specific system replacements

## History and Compaction

Climb this ladder, in order:

1. Raw append-only history while it fits.
2. Compact bulky tool results — keep paths, IDs, URLs, checksums, and small structured facts.
3. Summarize only when compaction can't do the job.

Keep intact:
- tool definitions or provider-supported tool references
- `system`
- route and mode identity, if stable
- first stable user / assistant messages

Don't:
- mutate previous tool calls
- delete evidence later tool calls might need
- replace early turns with a summary
- treat summarization as a free cache optimization

If the stable anchor alone overruns the context budget, fail closed or split the route / tool bundle. Silent dropping is worse than an explicit error.

## Required Agent Logs

Log per step:
- `prefix_hash`
- provider cache read field (`cached_tokens`, `cache_read_input_tokens`)
- cache creation / write field when available
- sorted tool-name hash
- `tools_count`
- prompt version and route
- TTFT / prefill latency
- mode state
- compaction event and compaction strategy
- output tokens and final-token latency when latency is the symptom

Alert when:
- TTFT climbs on late steps
- the prefix hash changes unexpectedly
- tool count shifts inside a long trajectory
- cached tokens reset after tool selection or compaction

## Synthetic Agent Eval

Add a 3–5 step smoke test:

1. Render step 1 with the full stable system / tools.
2. Append a tool call and result.
3. Render step 2 and confirm the stable prefix hash didn't change.
4. Trigger a mode switch or compaction and confirm only allowed late content changed.
5. Fail when dynamic tool retrieval, framework metadata, or early summarization mutates the stable prefix.

## Advanced Serving Note

Reach for this only when the user owns self-hosted serving infrastructure for many concurrent agent workflows.

Classic LRU eviction fits agents poorly because future reuse is determined by the workflow graph, not recent access. Research systems like KVFlow apply workflow-aware eviction and KV prefetching to preserve prefixes likely to come back soon.

Audit questions:
- Are useful agent prefixes evicted shortly before the agent resumes?
- Are many agent workflows paused on tools while their KV blocks occupy memory?
- Are CPU / GPU KV transfers visible in traces?
- Does the scheduler know about future agent steps, or only recent KV access?

Report this as an advanced serving-design opportunity, not an app-level fix. Try prompt stability, routing locality, and KV capacity first.
