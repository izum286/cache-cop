# cache-cop

Tooling for diagnosing why LLM prompt-cache reuse fails — across prefixes, telemetry, agent tools, and routing.

Right now this is just a scanner that grep-walks a project tree and tells you which provider SDKs you're touching. More to come.

## Usage

```bash
python3 cache-cop/scripts/scan_repo.py path/to/repo
```

Output is JSON. Pipe it into `jq` or eyeball it.
