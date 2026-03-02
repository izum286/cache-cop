#!/usr/bin/env python3
"""Grep a project tree for LLM provider calls and prompt-cache signals."""

import argparse
import json
import re
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Grep a project tree for LLM provider calls and prompt-cache signals."
    )
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    print(json.dumps(find_matches(root), ensure_ascii=False, indent=2))
    return 0


def find_matches(root):
    """Walk the tree, regex every line, return a JSON-ready provider scan."""
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
    """Return (provider, pattern) for the first regex that fires, else None."""
    for provider, patterns in PROVIDER_RULES.items():
        for pattern in patterns:
            if re.search(pattern, line, flags=re.IGNORECASE):
                return provider, pattern
    return None


def iter_files(root):
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        if should_scan(path):
            yield path


def should_scan(path):
    return path.is_file() and (
        path.suffix.lower() in CODE_EXTS or path.name in CONFIG_FILENAMES
    )


IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
}

CODE_EXTS = {
    ".cjs",
    ".go",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".mjs",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}

CONFIG_FILENAMES = {
    "Dockerfile",
    "Containerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}

PROVIDER_RULES = {
    "openai": [
        r"\bfrom\s+openai\s+import\b",
        r"\bimport\s+openai\b",
        r"\bresponses\.create\s*\(",
        r"\bchat\.completions\.create\s*\(",
        r"\bprompt_cache_key\b",
        r"\bprompt_cache_retention\b",
    ],
    "anthropic": [
        r"\banthropic\b",
        r"\bAnthropic\s*\(",
        r"\bmessages\.create\s*\(",
        r"\bcache_control\b",
    ],
    "bedrock": [
        r"\bbedrock-runtime\b",
        r"\bBedrockRuntime\b",
        r"\bclient\.converse\b",
        r"\binvoke_model\b",
        r"\bcachePoint\b",
        r"\bCache(Read|Write)InputTokens\b",
    ],
    "openrouter": [
        r"\bopenrouter\b",
        r"\bopenrouter\.ai/api/v1\b",
        r"\bOPENROUTER_API_KEY\b",
        r"\bopenrouter/auto\b",
    ],
    "gemini": [
        r"\bgoogle\.genai\b",
        r"\bgoogle\.generativeai\b",
        r"\bCachedContent\b",
    ],
    "deepseek": [
        r"\bdeepseek\b",
        r"\bapi\.deepseek\.com\b",
        r"\bprompt_cache_hit_tokens\b",
    ],
    "qwen": [
        r"\bdashscope\b",
        r"\bqwen\b",
        r"\bbailian\b",
    ],
}


if __name__ == "__main__":
    sys.exit(main())
