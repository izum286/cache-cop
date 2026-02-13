#!/usr/bin/env python3
"""Crunch provider usage logs into one cache-hit summary.

Early version: OpenAI + Anthropic field aliases only.
"""

import argparse
import csv
import json
import sys
from pathlib import Path


FIELD_ALIASES = {
    "input_tokens": (
        "input_tokens",
        "prompt_tokens",
    ),
    "cached_tokens": (
        "cached_tokens",
    ),
    "cache_read_input_tokens": (
        "cache_read_input_tokens",
    ),
    "cache_creation_input_tokens": (
        "cache_creation_input_tokens",
    ),
    "output_tokens": (
        "output_tokens",
        "completion_tokens",
    ),
}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Crunch provider usage logs into one cache-hit summary."
    )
    parser.add_argument("path", help="Path to a JSON, JSONL, or CSV usage log.")
    args = parser.parse_args(argv)
    records = read_records(Path(args.path))
    print(json.dumps(summarize(records), ensure_ascii=False, indent=2))
    return 0


def summarize(records):
    rows = [normalize_record(entry) for entry in records]
    aggregated = {
        "records": len(rows),
        "input_tokens": sum(r["input_tokens"] for r in rows),
        "cached_tokens": sum(r["cached_tokens"] for r in rows),
        "cache_read_input_tokens": sum(r["cache_read_input_tokens"] for r in rows),
        "cache_creation_input_tokens": sum(
            r["cache_creation_input_tokens"] for r in rows
        ),
        "total_input_tokens": sum(r["total_input_tokens"] for r in rows),
        "output_tokens": sum(r["output_tokens"] for r in rows),
    }
    reuse_tokens = aggregated["cached_tokens"] + aggregated["cache_read_input_tokens"]
    aggregated["cache_hit_ratio"] = ratio(reuse_tokens, aggregated["total_input_tokens"])
    aggregated["output_share"] = ratio(
        aggregated["output_tokens"],
        aggregated["total_input_tokens"] + aggregated["output_tokens"],
    )
    return aggregated


def normalize_record(record):
    counts = {
        metric: find_first_number(record, aliases)
        for metric, aliases in FIELD_ALIASES.items()
    }
    has_explicit_read_write = (
        counts["cache_read_input_tokens"] or counts["cache_creation_input_tokens"]
    )
    if has_explicit_read_write and not counts["cached_tokens"]:
        counts["total_input_tokens"] = (
            counts["input_tokens"]
            + counts["cache_read_input_tokens"]
            + counts["cache_creation_input_tokens"]
        )
    else:
        counts["total_input_tokens"] = counts["input_tokens"]
    return counts


def read_records(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="") as handle:
            return list(csv.DictReader(handle))
    text = path.read_text().strip()
    if not text:
        return []
    if suffix == ".jsonl":
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    payload = json.loads(text)
    if isinstance(payload, list):
        return payload
    return [payload]


def ratio(numerator, denominator, default=0):
    if not denominator:
        return default
    return round(numerator / denominator, 4)


def find_first_number(record, aliases):
    for node in walk(record):
        for alias in aliases:
            if alias in node:
                value = number(node[alias])
                if value:
                    return value
    return 0


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def number(value):
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


if __name__ == "__main__":
    sys.exit(main())
