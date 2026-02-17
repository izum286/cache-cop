#!/usr/bin/env python3
"""Turn a usage log and a list of findings into a prompt-cache audit card."""

import argparse
import json
import sys
from pathlib import Path

import summarize_usage


SEVERITIES = {"critical", "high", "medium", "low"}
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}

SEVEN_FIELDS = (
    "severity",
    "provider",
    "issue",
    "cache_impact",
    "fix",
    "validation",
)
THIRTEEN_FIELDS = (
    "severity",
    "provider",
    "issue",
    "evidence",
    "evidence_type",
    "confidence",
    "impact_condition",
    "cache_impact",
    "safe_first_action",
    "fix",
    "validation",
    "do_not_do_yet",
)

DEFAULT_MEASUREMENT_CHANGE = "unknown"
DEFAULT_PROMPT_BEHAVIOR_CHANGE = "unknown"
DEFAULT_PROVIDER_ROUTING_CHANGE = "unknown"
DEFAULT_CONFIDENCE = "low"
DEFAULT_DO_FIRST = "analyze usage logs and validate prefix stability"
DEFAULT_DO_NOT_DO_YET = "make provider/routing changes without telemetry"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Turn a usage log and a list of findings into a prompt-cache audit card."
    )
    parser.add_argument("--usage-log", required=True, help="JSON, JSONL, or CSV usage log.")
    parser.add_argument("--provider", default="unknown")
    parser.add_argument("--engine", default="unknown")
    parser.add_argument("--measurement-change", default=DEFAULT_MEASUREMENT_CHANGE)
    parser.add_argument("--prompt-behavior-change", default=DEFAULT_PROMPT_BEHAVIOR_CHANGE)
    parser.add_argument("--provider-routing-change", default=DEFAULT_PROVIDER_ROUTING_CHANGE)
    parser.add_argument("--confidence", default=DEFAULT_CONFIDENCE)
    parser.add_argument("--do-first", default=DEFAULT_DO_FIRST)
    parser.add_argument("--do-not-do-yet", default=DEFAULT_DO_NOT_DO_YET)
    parser.add_argument(
        "--finding",
        action="append",
        default=[],
        help=(
            "Pipe-separated finding. 7-field shape: "
            "source | severity | provider | issue | impact | fix | validation. "
            "13-field extended evidence shape adds evidence and safe-action fields."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args(argv)

    report = build_report(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")
    return 0


def render_markdown(report):
    """Render the structured report as a compact markdown audit card."""
    u = report["usage"]
    hit = f"{u['cache_hit_ratio'] * 100:.2f}"
    out_share = f"{u['output_share'] * 100:.2f}"
    md = [
        f"# Prompt-cache audit · {report['provider']} ({report['engine']})",
        "",
        _build_headline(report),
        "",
        "## Numbers",
        "",
        "| | Value |",
        "|---|---:|",
        f"| Records reviewed | {u['records']} |",
        f"| Cache hit ratio | {hit}% |",
        f"| Output share | {out_share}% |",
        f"| Measurement change | {report['measurement_change']} |",
        f"| Prompt behavior change | {report['prompt_behavior_change']} |",
        f"| Provider/routing change | {report['provider_routing_change']} |",
        f"| Confidence | {report['confidence']} |",
        "",
        "## Issues",
        "",
    ]
    if report["findings"]:
        md.append("| Source | Severity | What's wrong | How to fix | How to verify |")
        md.append("|---|---|---|---|---|")
        for item in report["findings"]:
            loc = item["source"] or item["rule_id"] or "advisory"
            md.append(
                "| "
                + " | ".join(
                    _escape_cell(c)
                    for c in (
                        loc,
                        item["severity"],
                        item["issue"],
                        item["fix"],
                        item["validation"],
                    )
                )
                + " |"
            )
    else:
        md.append("_Nothing flagged._")
    md.extend(
        [
            "",
            "## Action items",
            "",
            f"- **Start with:** {report['do_first']}",
            f"- **Hold off on:** {report['do_not_do_yet']}",
            "- Rerun on warm repeated traffic.",
            "- Cross-check cache-read counts against TTFT and dollar cost.",
            "- Verify prefix, tool, and schema hashes don't drift.",
        ]
    )
    return "\n".join(md) + "\n"


def _build_headline(report):
    u = report["usage"]
    n = u["records"]
    hit = f"{u['cache_hit_ratio'] * 100:.2f}"
    items = report["findings"]
    match len(items):
        case 0:
            return f"**Headline:** {n} requests, {hit}% cache hit. No findings supplied."
        case 1:
            sev = items[0]["severity"]
            text = _capitalize_first(items[0]["issue"])
            return (
                f"**Headline:** {n} requests, {hit}% cache hit, "
                f"1 finding ({sev}). {text}."
            )
        case _:
            worst = max(items, key=lambda f: SEVERITY_RANK.get(f["severity"], 0))
            text = _capitalize_first(worst["issue"])
            return (
                f"**Headline:** {n} requests, {hit}% cache hit, "
                f"{len(items)} findings (worst: {worst['severity']}). Top issue: {text}."
            )


def build_report(args):
    """Assemble the structured report dict shared by JSON and markdown output."""
    usage = load_usage(args.usage_log)
    return {
        "provider": args.provider,
        "engine": args.engine,
        "measurement_change": args.measurement_change,
        "prompt_behavior_change": args.prompt_behavior_change,
        "provider_routing_change": args.provider_routing_change,
        "confidence": args.confidence,
        "do_first": args.do_first,
        "do_not_do_yet": args.do_not_do_yet,
        "usage": usage,
        "findings": [parse_finding(f) for f in args.finding],
        "expected_impact": expected_impact(usage),
    }


def parse_finding(text):
    """Parse a pipe-separated finding (7-field or 13-field) into a dict."""
    cols = [part.strip() for part in text.split("|")]
    out = {
        "raw": text,
        "source": None,
        "rule_id": None,
        "severity": "low",
        "provider": None,
        "issue": text,
        "evidence": "",
        "evidence_type": "",
        "confidence": "",
        "impact_condition": "",
        "cache_impact": "",
        "safe_first_action": "",
        "fix": "",
        "validation": "",
        "do_not_do_yet": "",
    }
    if len(cols) < 7 or cols[1].lower() not in SEVERITIES:
        return out

    head = cols[0]
    if head.startswith("AP-"):
        out["rule_id"] = head
    else:
        out["source"] = head

    fields = THIRTEEN_FIELDS if len(cols) >= 13 else SEVEN_FIELDS
    out.update(dict(zip(fields, cols[1:])))
    out["severity"] = out["severity"].lower()
    return out


def has_extended_fields(finding):
    return any(
        finding.get(key)
        for key in (
            "evidence",
            "evidence_type",
            "confidence",
            "impact_condition",
            "safe_first_action",
            "do_not_do_yet",
        )
    )


def load_usage(path):
    return summarize_usage.summarize(summarize_usage.read_records(Path(path)))


def expected_impact(usage):
    hit_ratio = usage.get("cache_hit_ratio", 0)
    if hit_ratio:
        return (
            f"Cache benefit covers {hit_ratio:.4f} of input tokens. "
            "Confirm TTFT and dollar cost moved before declaring a win."
        )
    return (
        "Zero cache benefit observed. Check prefix stability, provider support, "
        "routing, and cache read/write telemetry."
    )


def _escape_cell(text):
    return str(text).replace("|", "\\|")


def _capitalize_first(text):
    if not text:
        return text
    return text[0].upper() + text[1:]


if __name__ == "__main__":
    sys.exit(main())
