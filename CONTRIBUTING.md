# Contributing

Welcome fren! Please, read this before you touch anything.

## Ground rules

- **Stdlib only inside the skill.** No third-party dependencies in `cache-cop/scripts/`. If you think you need one, think again. The `judge/` harness is exempt — it pulls Claude Code CLI and promptfoo (npm) on demand.
- **Snapshots are the contract.** Files under `samples/snapshots/{provider}/` get diffed byte-for-byte. Change the output, regenerate the snapshot — same commit.
- **Provider lore lives in `cache-cop/references/`.** Not in scripts. Not in SKILL.md. Learned something new about Bedrock cachePoint? It goes in `bedrock.md`.
- **Real telemetry doesn't enter the repo.** Ever. Everything in `samples/` is synthetic. Got production data? Redact => reshape => then maybe.

## Running things

```bash
python3 -m unittest tests.test_scripts        # 25 unit + snapshot tests
python3 tests/validate_skill.py cache-cop     # SKILL.md + trigger eval coverage
```

Both green or it doesn't ship. CI runs the same two, plus whitespace and syntax.

## Changing a script

1. Test first. Behavior without a test in `tests/test_scripts.py` doesn't exist.
2. Output drifts? Regenerate the snapshot:
   ```bash
   python3 cache-cop/scripts/summarize_usage.py samples/usage/<provider>.jsonl \
     > samples/snapshots/<provider>/usage-summary.json
   ```
   Same for `render_report.py` → `samples/snapshots/<provider>/report.md`. Re-run the suite.
3. Renamed a CLI flag? Hunt the callers in README, SKILL.md, and the test file. There are no others. Miss one and CI will tell on you.

## Changing the skill itself

`cache-cop/SKILL.md` is what Claude Code reads on activation. Two things:

- The `description:` frontmatter decides **when** the skill fires. Edit it like you mean it — every installed session sees the change. Don't touch it for prose polish.
- `judge/datasets/binary.json` is the activation safety net. New trigger phrase? Add a positive case. Narrowed the description? Add the now-excluded phrasing as a negative. One of each, minimum. Run `python3 judge/run.py binary` to measure the diff.

## Stays out of the repo

`__pycache__/`, `*.pyc`, `*.pyo` — `.gitignore` handles them, don't fight it. Anything from `~/Downloads/` exports? Redact into `samples/` shape first or don't commit it.
