# cache-cop

Tooling for diagnosing why LLM prompt-cache reuse fails — across prefixes, telemetry, agent tools, and routing.

## Scripts

```bash
python3 cache-cop/scripts/scan_repo.py path/to/repo
python3 cache-cop/scripts/lint_request.py samples/requests/chat-good.json
python3 cache-cop/scripts/diff_prefix.py samples/requests/chat-good.json samples/requests/chat-bad.json
```

`scan_repo.py` grep-walks a tree for provider SDK calls. `lint_request.py` flags layout anti-patterns in a rendered request. `diff_prefix.py` finds the byte offset where two rendered requests first diverge — useful for catching prefix drift.

WIP — more scripts and a full skill writeup coming.
