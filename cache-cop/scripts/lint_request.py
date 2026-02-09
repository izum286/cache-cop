#!/usr/bin/env python3
"""Flag prompt-cache layout anti-patterns in a rendered LLM request."""

import argparse
import json
import re
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Flag prompt-cache layout anti-patterns in a rendered LLM request."
    )
    parser.add_argument("path", help="JSON request payload to inspect.")
    args = parser.parse_args(argv)
    payload = json.loads(Path(args.path).read_text())
    result = lint(payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["findings"] else 0


def lint(payload):
    """Run every rule and return findings + IDs of rules that passed."""
    hits = [
        item
        for item in (
            lint_volatile_prefix(payload),
            lint_tool_order(payload),
            lint_dynamic_schema(payload),
        )
        if item
    ]
    fired = {h["rule_id"] for h in hits}
    return {
        "status": "findings" if hits else "ok",
        "findings": hits,
        "clean_checks": [rid for rid in ("PS-01", "PS-02") if rid not in fired],
    }


def lint_volatile_prefix(payload):
    """PS-01: dynamic content sits ahead of the cacheable prefix."""
    parts = ordered_prompt_segments(payload)
    if not parts:
        return None

    volatile_at = next(
        ((i, label, text) for i, (label, text) in enumerate(parts) if VOLATILE_RE.search(text)),
        None,
    )
    if volatile_at is None:
        return None

    stable_at = next(
        (i for i, (_, text) in enumerate(parts) if STABLE_HINT_RE.search(text)),
        None,
    )
    v_idx, where_label, where_text = volatile_at
    if stable_at is not None and v_idx > stable_at:
        return None

    return finding(
        "PS-01",
        "high",
        "prefix-stability",
        "dynamic content sits ahead of the cacheable prefix",
        f"{where_label} contains {where_text[:160]!r}",
        "push request IDs, timestamps, and user-specific values past the static prefix",
        "render repeated requests and verify the cacheable prefix hash is stable",
    )


def lint_tool_order(payload):
    """PS-02: tool definitions are not in a stable name-sorted order."""
    tool_list = payload.get("tools", [])
    if not isinstance(tool_list, list) or len(tool_list) < 2:
        return None
    tool_names = [name for name in (tool_name(tool) for tool in tool_list) if name]
    if len(tool_names) < 2 or tool_names == sorted(tool_names):
        return None
    return finding(
        "PS-02",
        "high",
        "prefix-stability",
        "tools are listed in registry order rather than sorted by name",
        f"tools order is {tool_names}",
        "sort tool definitions by function/name before serializing the request",
        "diff rendered request bytes across two warm calls",
    )


def lint_dynamic_schema(payload):
    """PS-02: structured-output schema embeds dynamic request metadata."""
    response_format = payload.get("response_format")
    if response_format is None:
        return None
    for node in walk(response_format):
        for key, value in node.items():
            normalized = key.replace("-", "_").lower()
            text = value if isinstance(value, str) else ""
            if normalized in DYNAMIC_SCHEMA_KEYS or VOLATILE_RE.search(text):
                return finding(
                    "PS-02",
                    "high",
                    "prefix-stability",
                    "structured-output schema embeds dynamic request metadata",
                    f"response_format key/value {key!r}: {text!r}",
                    "strip request IDs, timestamps, and trace values out of cached schemas",
                    "render the same schema across repeated calls and confirm byte stability",
                )
    return None


def ordered_prompt_segments(payload):
    """Flatten Chat-style messages or Responses-style input into (label, text) pairs."""
    parts = []
    instructions = payload.get("instructions")
    if instructions is not None:
        parts.append(("instructions", serialized_text(instructions)))

    messages = payload.get("messages", [])
    if isinstance(messages, list):
        for index, message in enumerate(messages):
            if isinstance(message, dict):
                parts.append((f"messages[{index}]", message_text(message)))

    input_value = payload.get("input")
    if isinstance(input_value, list):
        for index, item in enumerate(input_value):
            parts.append((f"input[{index}]", input_text(item)))
    elif input_value is not None:
        parts.append(("input", input_text(input_value)))

    return parts


def finding(rule_id, severity, category, issue, evidence, fix, validation):
    return {
        "rule_id": rule_id,
        "severity": severity,
        "category": category,
        "issue": issue,
        "evidence": evidence,
        "fix": fix,
        "validation": validation,
    }


def serialized_text(value):
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def message_text(message):
    return serialized_text(message.get("content", ""))


def input_text(item):
    if isinstance(item, dict) and "content" in item:
        return serialized_text(item["content"])
    return serialized_text(item)


def tool_name(tool):
    if not isinstance(tool, dict):
        return ""
    function = tool.get("function")
    if isinstance(function, dict) and isinstance(function.get("name"), str):
        return function["name"]
    name = tool.get("name")
    return name if isinstance(name, str) else ""


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


VOLATILE_RE = re.compile(
    r"(today|timestamp|datetime|request[_ -]?id|trace[_ -]?id|run[_ -]?id|"
    r"session[_ -]?id|user[_ -]?id|tenant|company|\b20\d\d-\d\d-\d\d\b|"
    r"\breq_[A-Za-z0-9_-]+\b)",
    re.IGNORECASE,
)
STABLE_HINT_RE = re.compile(
    r"(stable|reusable|policy|few-shot|examples|shared|static)",
    re.IGNORECASE,
)
DYNAMIC_SCHEMA_KEYS = {
    "requestid",
    "request_id",
    "traceid",
    "trace_id",
    "runid",
    "run_id",
    "timestamp",
    "datetime",
    "tenant",
    "userid",
    "user_id",
}


if __name__ == "__main__":
    sys.exit(main())
