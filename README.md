# cache-cop

Tooling for diagnosing why LLM prompt-cache reuse fails — across prefixes, telemetry, agent tools, and routing.

## Scripts

```bash
python3 cache-cop/scripts/scan_repo.py path/to/repo
python3 cache-cop/scripts/lint_request.py samples/requests/chat-good.json
python3 cache-cop/scripts/diff_prefix.py samples/requests/chat-good.json samples/requests/chat-bad.json
python3 cache-cop/scripts/summarize_usage.py samples/usage/openai.jsonl
python3 cache-cop/scripts/roi.py \
  --requests 1000 --static-tokens 5000 --dynamic-tokens 400 --output-tokens 200 \
  --hit-rate 0.9 --input-price-per-mtok 3 --cached-input-price-per-mtok 0.3 --output-price-per-mtok 15
```

| Script | Purpose |
|---|---|
| `scan_repo.py` | Grep-walk a project tree for provider SDK calls. |
| `lint_request.py` | Flag layout anti-patterns in a rendered request. |
| `diff_prefix.py` | Find the byte offset where two rendered requests first diverge. |
| `summarize_usage.py` | Parse provider usage logs and compute cache-hit ratio. |
| `roi.py` | Cost-delta math from static/dynamic/output token assumptions. |

Still a WIP. Skill writeup, tests, and provider references coming next.
