#!/usr/bin/env python3
"""Crunch provider usage logs into one cache-hit summary."""

import argparse
import csv
import json
import sys
from pathlib import Path


FIELD_ALIASES = {
    "input_tokens": (
        "input_tokens",
        "prompt_tokens",
        "InputTokens",
        "inputTokenCount",
    ),
    "cached_tokens": (
        "cached_tokens",
        "prompt_cache_hit_tokens",
    ),
    "cache_read_input_tokens": (
        "cache_read_input_tokens",
        "cache_read_tokens",
        "CacheReadInputTokens",
    ),
    "cache_creation_input_tokens": (
        "cache_creation_input_tokens",
        "cache_write_input_tokens",
        "cache_write_tokens",
        "CacheWriteInputTokens",
    ),
    "output_tokens": (
        "output_tokens",
        "completion_tokens",
        "OutputTokens",
        "outputTokenCount",
    ),
}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Crunch provider usage logs into one cache-hit summary."
    )
    parser.add_argument("path", help="Path to a JSON, JSONL, or CSV usage log.")
    parser.add_argument(
        "--jsonl-normalized",
        action="store_true",
        help="Stream one normalized event per record as JSONL instead of the summary.",
    )
    args = parser.parse_args(argv)
    records = read_records(Path(args.path))
    if args.jsonl_normalized:
        for event in normalized_events(records):
            print(json.dumps(event, ensure_ascii=False, sort_keys=True))
        return 0
    print(json.dumps(summarize(records), ensure_ascii=False, indent=2))
    return 0


def summarize(records):
    """Roll a list of provider usage records into one cache-hit report."""
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
    aggregated["cache_write_read_ratio"] = ratio(
        aggregated["cache_creation_input_tokens"],
        aggregated["cache_read_input_tokens"],
        default=None,
    )
    aggregated["output_share"] = ratio(
        aggregated["output_tokens"],
        aggregated["total_input_tokens"] + aggregated["output_tokens"],
    )
    return aggregated


def normalize_record(record):
    """Pull token counts out of a raw provider record via FIELD_ALIASES."""
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


def normalize_event(record, index):
    """Pair token counts with identifying metadata for JSONL streaming."""
    counts = normalize_record(record)
    return {
        "index": index,
        "provider": infer_provider(record),
        "model": metadata_value(record, "model"),
        "route": metadata_value(record, "route"),
        "request_id": metadata_value(record, "request_id"),
        "prefix_hash": metadata_value(record, "prefix_hash"),
        "input_tokens": counts["input_tokens"],
        "cached_tokens": counts["cached_tokens"],
        "cache_read_input_tokens": counts["cache_read_input_tokens"],
        "cache_creation_input_tokens": counts["cache_creation_input_tokens"],
        "cache_benefit_tokens": counts["cached_tokens"]
        + counts["cache_read_input_tokens"],
        "total_input_tokens": counts["total_input_tokens"],
        "output_tokens": counts["output_tokens"],
    }


def normalized_events(records):
    return [normalize_event(entry, idx) for idx, entry in enumerate(records)]


def read_records(path):
    """Read records from .csv, .json, or .jsonl. Returns a list of dicts."""
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
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return payload["data"]
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


def metadata_value(record, name):
    if not isinstance(record, dict):
        return None
    value = record.get(name)
    if isinstance(value, (str, int, float)):
        return value
    return None


def infer_provider(record):
    """Guess provider name from explicit field or telltale token-field names."""
    provider = record.get("provider") if isinstance(record, dict) else None
    if isinstance(provider, str) and provider:
        return provider
    text = json.dumps(record, ensure_ascii=False)
    if "CacheReadInputTokens" in text or "CacheWriteInputTokens" in text:
        return "bedrock"
    if "cache_read_input_tokens" in text or "cache_creation_input_tokens" in text:
        return "anthropic-compatible"
    if "prompt_cache_hit_tokens" in text:
        return "deepseek-compatible"
    if "cached_tokens" in text:
        return "openai-compatible"
    return "unknown"


if __name__ == "__main__":
    sys.exit(main())
