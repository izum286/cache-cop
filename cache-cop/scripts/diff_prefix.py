#!/usr/bin/env python3
"""Diff two rendered prompts at byte level and locate where the prefix breaks."""

import argparse
import difflib
import json
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Diff two rendered prompts at byte level and locate where the prefix breaks."
    )
    parser.add_argument("first")
    parser.add_argument("second")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Skip the unified-diff context; emit JSON only.",
    )
    parser.add_argument(
        "--canonical-json",
        action="store_true",
        help="Parse both files as JSON and compare in sorted-key canonical form.",
    )
    args = parser.parse_args(argv)

    a = load_payload(args.first, args.canonical_json)
    b = load_payload(args.second, args.canonical_json)
    offset = first_difference(a, b)

    if offset is None:
        result = {
            "stable": True,
            "stable_prefix_bytes": len(a.encode()),
            "first_difference": None,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    result = {
        "stable": False,
        "stable_prefix_bytes": len(a[:offset].encode()),
        "first_difference": {
            "byte_offset": offset,
            "near": json_pointer_for_difference(args.first, offset),
            "first_char": a[offset : offset + 40],
            "second_char": b[offset : offset + 40],
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.json:
        print()
        print(unified_context(a, b, (args.first, args.second)))
    return 1


def first_difference(a, b):
    """Return the index of the first differing character, or None if identical."""
    diff = next(
        ((i, ai, bi) for i, (ai, bi) in enumerate(zip(a, b)) if ai != bi),
        None,
    )
    if diff is not None:
        return diff[0]
    if len(a) != len(b):
        return min(len(a), len(b))
    return None


def json_pointer_for_difference(path, byte_index):
    """Best-effort breadcrumb naming the nearest JSON key before byte_index."""
    try:
        data = json.loads(Path(path).read_text())
    except json.JSONDecodeError:
        return ""
    pretty = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)
    head = pretty[:byte_index]
    quoted = list(reversed(head.split('"')))
    for idx in range(1, len(quoted), 2):
        key = quoted[idx]
        if key and key not in "{}[],: ":
            return key
    return ""


def unified_context(a, b, names):
    return "\n".join(
        difflib.unified_diff(
            a.splitlines(),
            b.splitlines(),
            fromfile=names[0],
            tofile=names[1],
            n=3,
            lineterm="",
        )
    )


def load_payload(path, canonical_json=False):
    """Read a file as raw text or as canonical sorted-key JSON."""
    text = Path(path).read_text()
    if not canonical_json:
        return text
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)


if __name__ == "__main__":
    sys.exit(main())
