#!/usr/bin/env python3
"""Grep a project tree for LLM provider calls.

Early version: only OpenAI and Anthropic detection.
"""

import argparse
import json
import re
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Grep a project tree for LLM provider calls."
    )
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    print(json.dumps(find_matches(root), ensure_ascii=False, indent=2))
    return 0


def find_matches(root):
    hits = []
    counts = {}
    n_files = 0
    for path in iter_files(root):
        n_files += 1
        try:
            text_lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(text_lines, 1):
            hit = match_line(line)
            if hit is None:
                continue
            provider, pattern = hit
            counts[provider] = counts.get(provider, 0) + 1
            hits.append(
                {
                    "path": str(path.relative_to(root)),
                    "line": lineno,
                    "provider": provider,
                    "pattern": pattern,
                    "text": line.strip()[:200],
                }
            )
    return {
        "root": str(root),
        "files_scanned": n_files,
        "matches": len(hits),
        "providers": counts,
        "findings": hits,
    }


def match_line(line):
    for provider, patterns in PROVIDER_RULES.items():
        for pattern in patterns:
            if re.search(pattern, line, flags=re.IGNORECASE):
                return provider, pattern
    return None


def iter_files(root):
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix.lower() in CODE_EXTS:
            yield path


IGNORED_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}

CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml"}

PROVIDER_RULES = {
    "openai": [
        r"\bfrom\s+openai\s+import\b",
        r"\bimport\s+openai\b",
        r"\bchat\.completions\.create\s*\(",
    ],
    "anthropic": [
        r"\banthropic\b",
        r"\bAnthropic\s*\(",
        r"\bmessages\.create\s*\(",
    ],
}


if __name__ == "__main__":
    sys.exit(main())
