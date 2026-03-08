# judge — does cache-cop actually move the needle?

A small eval harness that compares Claude's behavior **with** the cache-cop skill loaded versus **without**, using the two bundled eval datasets. Three runnable modes, three different approaches — pick what's useful.

## Prerequisites

- **Claude Code CLI** on PATH (`claude --version` works). [Install guide](https://docs.claude.com/en/docs/claude-code).
- **`ANTHROPIC_API_KEY`** exported in the environment.
- **Node 18+** plus `promptfoo` for Mode 2 — either `npm install -g promptfoo` or invoke ad-hoc via `npx promptfoo@latest`.

Mode 1 doesn't need anything else — it provisions two temp working directories, drops `cache-cop/` into one of them under `.claude/skills/` (project-level skill discovery), and runs `claude -p` with `cwd` pointed at each. Your real `~/.claude/` is never touched; auth keeps working normally.

## The three modes

### Mode 1 — Binary eval (Python, stdlib only)

```bash
python3 judge/run.py binary --out results/binary.json
```

For each query in `datasets/binary.json`, runs `claude -p` **twice** — once with an isolated empty `HOME` (baseline) and once with an isolated `HOME` that contains `cache-cop/` under `.claude/skills/` (with-skill). Both invocations stream `--output-format stream-json`; the harness watches for `tool_use` blocks where the cache-cop skill fires. Binary classification: did it activate or not. **Real Claude Code matching** in both runs — no LLM-judge approximation, no manual mucking with your `~/.claude/skills/`.

The output JSON contains per-case results plus a `summary` with `baseline` metrics, `with_skill` metrics, and a `lift_pass_rate` showing how much pass rate the skill adds.

### Mode 2 — Semantic eval, side-by-side (promptfoo + llm-rubric)

```bash
python3 judge/run.py prepare                       # regenerate datasets/semantic.csv + prompts/with-skill.txt
cd judge && promptfoo eval -c promptfoo.yaml
promptfoo view                                      # opens browser, side-by-side per case
promptfoo export eval <eval-id> --output out.json  # extract per-prompt testPassCount/score for scripting
```

Sends each `prompt` from `datasets/semantic.json` through the same model twice — once with bare prompt (baseline), once with SKILL.md body prepended (with-skill). Each response is then scored 1–5 by `claude-haiku-4-5` against the row's `expected_output` rubric. promptfoo UI shows both columns per row with judge reasoning.

This mode **does not reproduce Claude Code's description-matching gate** — the skill body is always injected. Honest emulation of "if the skill were active, would its body help?".

### Mode 3 — Semantic eval, multi-axis with order-swap (Python, stdlib only)

```bash
python3 judge/run.py semantic --out results/semantic.json
```

Collects baseline + with-skill responses for each case in `datasets/semantic.json`, then has a stronger judge model score every pair on four axes:

- **routing** — picked the right provider / scenario reference, the right playbook entry, respected wrapper precedence
- **diagnosis** — named the right anti-pattern and applied severity logic that ties to route hotness and prefix stability
- **evidence** — asked for the telemetry the rubric needs, applied a freshness gate to provider facts, didn't fabricate numbers
- **verification** — proposed a falsifying check the user could actually run

Each axis is scored 1–100; `overall = mean of the four`. Cases run in sub-batches (default 5) and each sub-batch is judged twice with the two responses swapped, then averaged. The output JSON includes per-axis lift, the overall lift, and a `swap_delta` block that tells you whether the swap actually mattered.

**Subject defaults to `claude-haiku-4-5`, judge defaults to `claude-sonnet-4-6`** — judge is strictly stronger than subject, which is the rule for honest LLM-as-judge. Override either with `--model` / `--judge-model`. If you raise the subject (`--model claude-opus-4-7` for a production-strength run), raise the judge too (`--judge-model claude-opus-4-7`); never run with a judge weaker than the subject.

Override batching with `--judge-batch-size`. Disable the swap pass with `--no-swap` (cheaper, more biased).

## LLM-as-judge: the biases that bite, and what this harness does

LLM-as-judge swaps expensive human eval for another LLM grading the responses. Cheap and fast, but several known biases ruin a naive setup. Worth knowing what they are before reading the numbers:

- **Position bias.** Models systematically prefer the first (or last, depending on the model) option in pairwise comparisons. The cleanest fix is to run the same judgment twice with the responses swapped and average.
- **Self-preference / self-enhancement.** A model judging itself, or another model from the same family at the same size, tends to favor its own style. The mitigation is to use a judge from a different family, or at least a stronger model in the same family.
- **Verbosity bias.** Longer answers get higher scores even when they're worse, because length reads as confidence. The mitigation is to tell the judge explicitly in the prompt that length is not a quality signal.
- **Style bias.** Confident-sounding prose gets rewarded over correctly hedged prose. For a skill like cache-cop, which is *supposed* to say "verify against current docs before claiming an exact price", this matters a lot.
- **Pointwise noise.** Asking a model for an absolute 1–100 score is noisier than asking it to pick the better of two responses. A decomposed multi-axis rubric with explicit level descriptions is better than a single global number.
- **Chain-of-thought ordering.** If you ask the judge to emit `{score, reasoning}` in that order, the model picks a number and then rationalizes it. Asking for `{reasoning, scores}` puts the analysis first and lets the score follow from it.
- **Lost-in-the-middle.** Stuffing 30 cases into one judge prompt means the cases in the middle get less attention. Smaller batches help; per-case calls help more but cost more.

Mode 3 applies the cheap-but-effective subset of the above:

| Bias | What we do |
|---|---|
| Position | Two-pass swap. `swap_delta` in the output tells you how much the order actually mattered. |
| Self-preference | Default judge is Sonnet (or whatever you pass with `--judge-model`); the harness assumes you'll pick a judge at least as strong as the subject. |
| Verbosity | Judge prompt says length is not a quality signal. |
| Style | Judge prompt says hedging like "verify against current provider docs" is correct behavior, not weakness. |
| Pointwise noise | Four named axes with explicit per-level descriptions instead of one opaque 1–100. |
| CoT ordering | Judge writes one reasoning paragraph first, then the per-axis scores. |
| Lost-in-the-middle | Sub-batches of 5 cases by default. |

What we **don't** do (yet):

- **Cross-family judge.** Everything is Anthropic. A GPT-5 or Gemini judge would kill self-preference more thoroughly but adds a new SDK and new env vars — not worth it for a portfolio-grade harness.
- **Panel of judges.** Same trade-off, multiplied by N.
- **Human calibration.** No held-out human-rated subset; we don't know the absolute correlation between this judge and a domain expert. Numbers should be read as relative lift, not absolute quality.
- **Factual verification.** The judge can't look up current provider pricing. We lean on the rubric in `datasets/semantic.json` for ground truth instead — that's a reference-based eval, which is the right call when facts drift.

## Sample run

A 10-case slice from `datasets/semantic.json`, run on 2026-05-20:

```bash
python3 judge/run.py semantic --limit 10 --out results/semantic-10-v2.json
# subject: claude-haiku-4-5  (default)
# judge:   claude-sonnet-4-6 (default)
# swap on, sub-batch size 5
```

| Axis | Baseline mean | With-skill mean | Lift |
|---|---:|---:|---:|
| routing | 49.95 | 78.00 | +28.05 |
| diagnosis | 52.65 | 75.75 | +23.10 |
| evidence | 36.15 | 73.50 | +37.35 |
| verification | 39.40 | 77.70 | +38.30 |
| **overall** | **44.54** | **76.24** | **+31.70** |

`swap_delta`: baseline mean abs **7.53**, with-skill mean abs **5.47**, max case delta **15.0**. The harness flagged a swap warning — both means sit above the 5-point threshold and the worst case is at the 15-point ceiling. Translation: the two judge passes (baseline-first vs. with-skill-first) disagreed enough that order bias was not fully averaged out at this sample size. The +31.70 overall lift is directionally real but not a hard number on N=10.

Where the skill helps most: `evidence` (+37) and `verification` (+38). Without the skill body in the system prompt, Haiku tends to skip asking for telemetry, skip applying a freshness gate to provider facts, and skip proposing falsifying checks — exactly the behaviors the skill exists to inject. The smaller lifts on `routing` (+28) and `diagnosis` (+23) say Haiku already does decent provider routing and anti-pattern naming on its own; the skill polishes those axes rather than fixing them.

Next step for a tighter number: run the full 30 cases (the swap warning is partly small-N noise), or run with `--judge-batch-size 1` to remove cross-case interference entirely. Numbers in this section will be replaced once that run lands.

## Cost ballpark

Assuming default models — subject `claude-haiku-4-5`, judge `claude-sonnet-4-6`:

- **Mode 1 (binary)**: ~160 Claude Code invocations per run (80 baseline + 80 with-skill) on the subject. Detection terminates early — usually well under $1.
- **Mode 2 (promptfoo)**: ~60 subject calls + ~60 judge calls — typically $1–3 per full run.
- **Mode 3 (semantic)**: 60 subject calls + 12 judge calls on the full 30-case dataset (6 sub-batches × 2 swap passes). Each judge call carries 5 cases, so token usage is comparable to the older single-batch design. Typically $1–2 per full run; `--no-swap` halves the judge cost; `--limit 10` cuts the subject cost too.

If you raise the subject to Opus (`--model claude-opus-4-7`), raise the judge to Opus too — and expect the run to cost roughly an order of magnitude more.

## Interpreting results

Mode 1:
- Baseline (skill removed) should hit ~0% true-positive rate (the skill literally isn't there to fire) and 100% true-negative rate. With-skill should land near 90%+ on positives without losing too many negatives. A high false-positive rate on with-skill means the description is too broad.

Mode 3:
- **Per-axis lift** is more informative than the overall number. A skill that lifts `routing` by +30 but only nudges `verification` by +5 is doing a different job than one that lifts every axis equally.
- **`swap_delta`** is the run's self-check. If `max_case_delta > 15` or the mean swap delta is above ~5 points, the two orientations disagreed enough that order bias is leaking into the lift — read it with suspicion. The harness prints a warning in that case.
- **Per-case rows** carry both judge reasonings (`reasoning_pass_a`, `reasoning_pass_b`). Any case where baseline outscores with-skill is interesting to read — usually the skill body confused the agent or pulled it off task.

Sample sizes (80 binary, 30 semantic) give directional signal, not statistical certainty. Don't treat any single run's numbers as final, and re-run when the skill or the judge model changes.

## Known limitations

- **Modes 2 and 3 always inject the skill body.** They can't simulate Claude Code's description-matching, which is what decides activation in real usage. Only Mode 1 exercises real matching.
- **Anthropic-only.** No cross-family judge support. Self-preference is reduced (judge stronger than subject, neutral A/B labels in the prompt), not eliminated.
- **No human calibration.** Numbers are relative lift between two conditions on the same judge — they're not anchored to a human-rated ground truth. If you need absolute quality claims, you need a rated subset.
- **Snapshot and temperature drift.** Mode 2 pins temperature 0 in `promptfoo.yaml`; Modes 1 and 3 inherit whatever the `claude` CLI default is at the time of the run, which adds a little noise on top of the inevitable Anthropic snapshot updates. Each result file logs `model`, `judge_model`, and `run_at` so cross-run comparison stays honest.
