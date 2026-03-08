#!/usr/bin/env python3
"""cache-cop eval harness: prepare promptfoo artifacts, run binary eval, run semantic eval.

Three subcommands:

  prepare    Regenerate datasets/semantic.csv and prompts/with-skill.txt from sources.
  binary     Real Claude Code activation detection across datasets/binary.json.
  semantic   Multi-axis semantic eval: a stronger judge model scores baseline and
             with-skill responses on four axes (routing, diagnosis, evidence,
             verification). Cases run in sub-batches with a swapped-order second pass
             to neutralize position bias.

stdlib only. Requires the `claude` CLI on PATH for `binary` and `semantic` modes.
"""

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "cache-cop"
HERE = Path(__file__).resolve().parent
SKILL_NAME = "cache-cop"


def cmd_prepare(args):
    """Generate datasets/semantic.csv and prompts/with-skill.txt."""
    semantic_path = HERE / "datasets" / "semantic.json"
    csv_path = HERE / "datasets" / "semantic.csv"
    with_skill_path = HERE / "prompts" / "with-skill.txt"

    data = json.loads(semantic_path.read_text())
    rows = data["evals"] if isinstance(data, dict) else data
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "prompt", "expected_output"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "id": row["id"],
                    "prompt": row["prompt"],
                    "expected_output": row["expected_output"],
                }
            )

    skill_md = (SKILL / "SKILL.md").read_text()
    body = strip_frontmatter(skill_md)
    with_skill_path.write_text(f"{body.rstrip()}\n\n{{{{prompt}}}}\n")

    print(f"wrote {csv_path.relative_to(ROOT)} ({len(rows)} rows)")
    print(f"wrote {with_skill_path.relative_to(ROOT)} ({len(body)} chars of SKILL body)")
    return 0


def cmd_binary(args):
    """Provision two cwds (with and without project-level skill), run both per query, emit diff."""
    cases = json.loads((HERE / "datasets" / "binary.json").read_text())

    with tempfile.TemporaryDirectory(prefix="judge-baseline-") as baseline_cwd, \
         tempfile.TemporaryDirectory(prefix="judge-with-skill-") as skill_cwd:
        (Path(skill_cwd) / ".claude" / "skills").mkdir(parents=True)
        shutil.copytree(SKILL, Path(skill_cwd) / ".claude" / "skills" / SKILL_NAME)

        results = []
        for i, case in enumerate(cases, 1):
            sys.stderr.write(f"\r[binary] {i}/{len(cases)}")
            sys.stderr.flush()
            baseline_trig = invoke_and_detect_skill(case["query"], args.model, baseline_cwd)
            with_skill_trig = invoke_and_detect_skill(case["query"], args.model, skill_cwd)
            results.append(
                {
                    "query": case["query"],
                    "should_trigger": case["should_trigger"],
                    "baseline_triggered": baseline_trig,
                    "with_skill_triggered": with_skill_trig,
                    "baseline_pass": baseline_trig == case["should_trigger"],
                    "with_skill_pass": with_skill_trig == case["should_trigger"],
                }
            )
        sys.stderr.write("\n")

    summary = summarize_binary_results(results)
    payload = {
        "mode": "binary",
        "model": args.model,
        "skill": SKILL_NAME,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary,
        "cases": results,
    }
    write_output(args.out, payload)
    print(json.dumps(summary, indent=2))
    return 0


def cmd_semantic(args):
    """Collect baseline+with-skill responses, then judge them per axis in sub-batches with optional order-swap."""
    data = json.loads((HERE / "datasets" / "semantic.json").read_text())
    rows = data["evals"] if isinstance(data, dict) else data
    if args.limit:
        rows = rows[: args.limit]
    skill_body = strip_frontmatter((SKILL / "SKILL.md").read_text()).rstrip()

    responses = []
    for i, row in enumerate(rows, 1):
        sys.stderr.write(f"\r[semantic] response {i}/{len(rows)}")
        sys.stderr.flush()
        baseline = invoke_claude(row["prompt"], args.model, system_prompt=None)
        with_skill = invoke_claude(row["prompt"], args.model, system_prompt=skill_body)
        responses.append(
            {
                "id": row["id"],
                "prompt": row["prompt"],
                "expected_output": row["expected_output"],
                "baseline_response": baseline,
                "with_skill_response": with_skill,
            }
        )
    sys.stderr.write("\n")

    swap = not args.no_swap
    passes_per_batch = 2 if swap else 1
    num_batches = (len(responses) + args.judge_batch_size - 1) // args.judge_batch_size
    sys.stderr.write(
        f"[semantic] judging: {num_batches} batch(es) × {passes_per_batch} pass(es) "
        f"on {args.judge_model}...\n"
    )
    scored = batch_judge(
        responses,
        args.judge_model,
        batch_size=args.judge_batch_size,
        swap=swap,
    )

    summary = summarize_semantic_scores(scored)
    payload = {
        "mode": "semantic",
        "model": args.model,
        "judge_model": args.judge_model,
        "judge_batch_size": args.judge_batch_size,
        "judge_swap": swap,
        "skill": SKILL_NAME,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary,
        "cases": scored,
    }
    write_output(args.out, payload)
    print(json.dumps(summary, indent=2))

    delta = summary.get("swap_delta")
    if delta and (delta["max_case_delta"] > 15 or
                  delta["baseline_overall_mean_abs"] > 5 or
                  delta["with_skill_overall_mean_abs"] > 5):
        sys.stderr.write(
            "[semantic] WARNING: swap_delta is large — the judge's two passes disagreed by more "
            "than the threshold. Order bias is not fully averaged out and the lift number is suspect.\n"
        )
    return 0


def invoke_and_detect_skill(query, model, cwd):
    """Run `claude -p` inside a cwd (with or without a project-level skill) and detect activation."""
    cmd = [
        "claude",
        "-p",
        query,
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--model",
        model,
    ]
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd=cwd
    )
    for line in process.stdout:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if detect_skill_in_event(event):
            process.terminate()
            return True
    process.wait()
    return False


def detect_skill_in_event(event):
    """Inspect a stream-json event for cache-cop skill activation."""
    if event.get("type") == "content_block_start":
        cb = event.get("content_block", {})
        if cb.get("type") == "tool_use" and cb.get("name") in ("Skill", "Read"):
            text = json.dumps(cb.get("input", {}))
            if SKILL_NAME in text:
                return True
    if event.get("type") == "assistant":
        for item in event.get("message", {}).get("content", []):
            if item.get("type") == "tool_use" and item.get("name") in ("Skill", "Read"):
                if SKILL_NAME in json.dumps(item.get("input", {})):
                    return True
    return False


def invoke_claude(prompt, model, system_prompt=None):
    """Run `claude -p` in an isolated tempdir so any files Claude writes don't pollute the repo."""
    cmd = ["claude", "-p", prompt, "--model", model]
    sp_path = None
    if system_prompt is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(system_prompt)
            sp_path = f.name
        cmd.extend(["--system-prompt-file", sp_path])
    try:
        with tempfile.TemporaryDirectory(prefix="judge-claude-") as cwd:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=cwd)
            return result.stdout.strip()
    finally:
        if sp_path is not None:
            Path(sp_path).unlink(missing_ok=True)


AXES = ("routing", "diagnosis", "evidence", "verification")


JUDGE_PROMPT_HEADER = """\
You are scoring LLM responses on prompt-cache audit tasks. Each case has the original prompt, the expected behavior (rubric), and two candidate responses labeled response_A and response_B. Score each response independently against the rubric — do not try to guess what produced either response or anchor one score against the other.

Score each response on four axes, 1-100:

  routing      — did the response pick the right provider / scenario reference, the right playbook entry, and respect wrapper precedence (e.g. an OpenAI SDK with a custom base_url is treated as the wrapper provider, not raw OpenAI)?
  diagnosis    — did the response name the right anti-pattern(s) and apply severity logic that ties to route hotness, prefix stability, and cost shape rather than the rule name alone?
  evidence     — did the response ask for the telemetry the rubric calls for, apply a freshness gate to provider facts (verify against current docs, mark unverified), and avoid fabricating numbers, prices, or model behavior?
  verification — did the response propose a falsifying check the user could actually run (prefix fingerprint diff, provider usage field that should move, route-level metric, cost / latency split)?

Per-axis level guide:
  90-100  covers the rubric point in full with correct technical content
  70-89   mostly correct, small omission or imprecision
  40-69   partially correct, meaningful gaps
  10-39   misses the rubric point, recovers with a tangential answer
  1-9     irrelevant or wrong

Calibration rules:
- Length is not a quality signal. A short answer that gets the rubric right scores higher than a long answer that misses it.
- Do not reward confident-sounding prose. Reward responses that match the rubric. Hedging like "verify against current provider docs before exact claims" is correct cache-cop behavior, not a weakness.
- Score response_A and response_B independently. Do not anchor on the other response when scoring.
- Write reasoning before scores. Reasoning explains what each response did and didn't cover; scores follow.

Return a JSON array, one object per case, in this exact shape:

[
  {
    "id": <int>,
    "reasoning": "<one short paragraph covering both responses>",
    "response_A": {"routing": <int>, "diagnosis": <int>, "evidence": <int>, "verification": <int>},
    "response_B": {"routing": <int>, "diagnosis": <int>, "evidence": <int>, "verification": <int>}
  }
]

Return ONLY the JSON array, no prose around it.
"""


def batch_judge(responses, judge_model, batch_size=5, swap=True):
    """Score each pair (baseline, with-skill) on four axes, in sub-batches, optionally with swapped order."""
    scored_by_id = {r["id"]: {"id": r["id"]} for r in responses}

    for chunk in _chunks(responses, batch_size):
        pass_a = _judge_pass(chunk, judge_model, swap_order=False)
        pass_b = _judge_pass(chunk, judge_model, swap_order=True) if swap else None
        for case in chunk:
            scored_by_id[case["id"]] = _merge_passes(case, pass_a, pass_b)

    return [{**r, **scored_by_id[r["id"]]} for r in responses]


def _chunks(items, size):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _judge_pass(chunk, judge_model, swap_order):
    """Run one judge call. swap_order=False maps baseline→A, with_skill→B; True does the opposite."""
    blocks = []
    for r in chunk:
        if swap_order:
            response_a, response_b = r["with_skill_response"], r["baseline_response"]
        else:
            response_a, response_b = r["baseline_response"], r["with_skill_response"]
        blocks.append(
            f"--- case {r['id']} ---\n"
            f"prompt: {r['prompt']}\n\n"
            f"expected rubric: {r['expected_output']}\n\n"
            f"response_A:\n{response_a}\n\n"
            f"response_B:\n{response_b}\n"
        )
    raw = invoke_claude(JUDGE_PROMPT_HEADER + "\n" + "\n".join(blocks), judge_model)
    try:
        parsed = json.loads(_extract_json_array(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        return {"error": f"judge parse failed: {exc}", "raw": raw}

    by_id = {}
    for entry in parsed:
        try:
            scores_a = _coerce_axes(entry["response_A"])
            scores_b = _coerce_axes(entry["response_B"])
        except (KeyError, TypeError, ValueError) as exc:
            by_id[entry.get("id")] = {"error": f"missing/invalid axes: {exc}"}
            continue
        baseline_scores = scores_b if swap_order else scores_a
        with_skill_scores = scores_a if swap_order else scores_b
        by_id[entry["id"]] = {
            "reasoning": entry.get("reasoning", ""),
            "baseline": baseline_scores,
            "with_skill": with_skill_scores,
        }
    return by_id


def _coerce_axes(raw_axes):
    """Pull the four named axes out of a dict and average them into 'overall'."""
    scores = {axis: int(raw_axes[axis]) for axis in AXES}
    scores["overall"] = round(sum(scores[axis] for axis in AXES) / len(AXES), 2)
    return scores


def _merge_passes(case, pass_a, pass_b):
    """Average pass_a and pass_b per axis. If only one pass succeeded, use it and skip swap_delta."""
    base = {"id": case["id"]}

    if isinstance(pass_a, dict) and "error" in pass_a:
        a_entry = pass_a
    else:
        a_entry = pass_a.get(case["id"]) if pass_a else None

    if pass_b is None:
        b_entry = None
    elif isinstance(pass_b, dict) and "error" in pass_b:
        b_entry = pass_b
    else:
        b_entry = pass_b.get(case["id"]) if pass_b else None

    a_ok = a_entry and "baseline" in a_entry
    b_ok = b_entry and "baseline" in b_entry

    if not a_ok and not b_ok:
        return {**base, "error": (a_entry or b_entry or {"error": "no judge output"}).get("error", "no judge output")}

    if a_ok and b_ok:
        base["baseline"] = _avg_scores(a_entry["baseline"], b_entry["baseline"])
        base["with_skill"] = _avg_scores(a_entry["with_skill"], b_entry["with_skill"])
        base["swap_delta"] = {
            "baseline_overall": round(abs(a_entry["baseline"]["overall"] - b_entry["baseline"]["overall"]), 2),
            "with_skill_overall": round(abs(a_entry["with_skill"]["overall"] - b_entry["with_skill"]["overall"]), 2),
        }
        base["reasoning_pass_a"] = a_entry.get("reasoning", "")
        base["reasoning_pass_b"] = b_entry.get("reasoning", "")
    else:
        only = a_entry if a_ok else b_entry
        base["baseline"] = only["baseline"]
        base["with_skill"] = only["with_skill"]
        base["reasoning"] = only.get("reasoning", "")
        base["swap_delta"] = None
        base["note"] = "single-pass result; the other pass failed to parse"

    return base


def _avg_scores(a, b):
    out = {axis: round((a[axis] + b[axis]) / 2, 2) for axis in AXES}
    out["overall"] = round((a["overall"] + b["overall"]) / 2, 2)
    return out


def _extract_json_array(text):
    """Pull the first [...] block out of a string. Tolerates pre/post chatter from the judge."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON array found in judge output")
    return text[start : end + 1]


def summarize_binary_results(results):
    return {
        "total": len(results),
        "baseline": condition_metrics(results, "baseline"),
        "with_skill": condition_metrics(results, "with_skill"),
        "lift_pass_rate": round(
            pass_rate(results, "with_skill") - pass_rate(results, "baseline"), 4
        ) if results else 0,
    }


def condition_metrics(results, condition):
    positives = [r for r in results if r["should_trigger"]]
    negatives = [r for r in results if not r["should_trigger"]]
    trig_key = f"{condition}_triggered"
    pass_key = f"{condition}_pass"
    passed = sum(1 for r in results if r[pass_key])
    return {
        "passed": passed,
        "pass_rate": round(passed / len(results), 4) if results else 0,
        "true_positives": sum(1 for r in positives if r[trig_key]),
        "false_negatives": sum(1 for r in positives if not r[trig_key]),
        "true_negatives": sum(1 for r in negatives if not r[trig_key]),
        "false_positives": sum(1 for r in negatives if r[trig_key]),
    }


def pass_rate(results, condition):
    pass_key = f"{condition}_pass"
    return sum(1 for r in results if r[pass_key]) / len(results) if results else 0


def summarize_semantic_scores(cases):
    """Per-axis means + lift, plus overall + swap_delta sanity check."""
    scored = [c for c in cases if "baseline" in c and "with_skill" in c]
    summary = {
        "total": len(cases),
        "scored": len(scored),
        "errors": sum(1 for c in cases if "error" in c),
    }
    if not scored:
        summary["axes"] = None
        summary["overall"] = None
        summary["swap_delta"] = None
        return summary

    axes_summary = {}
    for axis in AXES + ("overall",):
        baseline_axis = [c["baseline"][axis] for c in scored]
        with_skill_axis = [c["with_skill"][axis] for c in scored]
        baseline_mean = round(sum(baseline_axis) / len(baseline_axis), 2)
        with_skill_mean = round(sum(with_skill_axis) / len(with_skill_axis), 2)
        axes_summary[axis] = {
            "baseline_mean": baseline_mean,
            "with_skill_mean": with_skill_mean,
            "lift": round(with_skill_mean - baseline_mean, 2),
        }

    summary["axes"] = {axis: axes_summary[axis] for axis in AXES}
    summary["overall"] = axes_summary["overall"]

    swap_pairs = [c.get("swap_delta") for c in scored if c.get("swap_delta")]
    if swap_pairs:
        baseline_deltas = [p["baseline_overall"] for p in swap_pairs]
        with_skill_deltas = [p["with_skill_overall"] for p in swap_pairs]
        summary["swap_delta"] = {
            "cases_with_swap": len(swap_pairs),
            "baseline_overall_mean_abs": round(sum(baseline_deltas) / len(baseline_deltas), 2),
            "with_skill_overall_mean_abs": round(sum(with_skill_deltas) / len(with_skill_deltas), 2),
            "max_case_delta": round(max(baseline_deltas + with_skill_deltas), 2),
        }
    else:
        summary["swap_delta"] = None
    return summary


def strip_frontmatter(text):
    if not text.startswith("---\n"):
        return text
    parts = text.split("---\n", 2)
    return parts[2] if len(parts) >= 3 else text


def write_output(out_path, payload):
    path = Path(out_path)
    if not path.is_absolute():
        path = HERE / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.stderr.write(f"wrote {path}\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="mode", required=True)

    sub.add_parser("prepare", help="Regenerate datasets/semantic.csv and prompts/with-skill.txt.")

    binary = sub.add_parser("binary", help="Run binary activation eval via `claude -p` stream-json.")
    binary.add_argument("--out", default="results/binary.json")
    binary.add_argument("--model", default="claude-haiku-4-5")

    semantic = sub.add_parser(
        "semantic",
        help="Run multi-axis semantic eval with sub-batches and order-swap.",
    )
    semantic.add_argument("--out", default="results/semantic.json")
    semantic.add_argument(
        "--model",
        default="claude-haiku-4-5",
        help="Subject model. Default Haiku to keep the judge (Sonnet) strictly stronger than the subject.",
    )
    semantic.add_argument(
        "--judge-model",
        default="claude-sonnet-4-6",
        help="Judge model. Best practice: the judge should be at least as strong as the subject model.",
    )
    semantic.add_argument(
        "--judge-batch-size",
        type=int,
        default=5,
        help="Cases per judge call. Smaller batches reduce lost-in-the-middle bias; larger batches let the judge calibrate across cases.",
    )
    semantic.add_argument(
        "--no-swap",
        action="store_true",
        help="Skip the second swapped-order pass. Halves judge cost but leaves position bias unaveraged.",
    )
    semantic.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Run only the first N cases (0 = all).",
    )

    args = parser.parse_args()
    return {"prepare": cmd_prepare, "binary": cmd_binary, "semantic": cmd_semantic}[args.mode](args)


if __name__ == "__main__":
    sys.exit(main())
