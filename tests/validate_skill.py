#!/usr/bin/env python3
"""Sanity-check a skill package: SKILL.md shape, referenced files, scripts directory."""

import argparse
import json
import re
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Sanity-check a skill package: SKILL.md shape, referenced files, scripts directory."
    )
    parser.add_argument("skill_dir", nargs="?", default="cache-cop")
    args = parser.parse_args(argv)

    validation = validate_package(args.skill_dir)
    overall = validation["status"]

    print(
        json.dumps(
            {"status": overall, "validation": validation},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if overall == "ok" else 1


def validate_package(skill_dir):
    """Inspect SKILL.md frontmatter, referenced files, and the scripts directory."""
    skill_dir = Path(skill_dir)
    errors = []
    warnings = []
    checks = {}

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        errors.append("SKILL.md not found in skill directory")
        return {"status": "error", "checks": checks, "errors": errors, "warnings": warnings}

    skill_text = skill_md.read_text()
    meta, frontmatter_err = parse_frontmatter(skill_text)
    if frontmatter_err:
        errors.append(frontmatter_err)
    for key in ("name", "description"):
        if not meta.get(key):
            errors.append(f"SKILL.md frontmatter is missing required key: {key}")
    checks["SKILL.md"] = "ok" if not frontmatter_err else "error"

    def check_refs():
        for rel_path in sorted(set(REFERENCE_PATTERN.findall(skill_text))):
            target = skill_dir / rel_path
            if not target.exists():
                errors.append(f"referenced file does not exist: {rel_path}")

    gate("references", errors, checks, check_refs)

    scripts_dir = skill_dir / "scripts"
    if scripts_dir.exists():
        gate(
            "scripts",
            errors,
            checks,
            lambda: [_check_python(p, errors) for p in sorted(scripts_dir.glob("*.py"))],
        )
    else:
        warnings.append("scripts directory not found")

    return {
        "status": "error" if errors else "ok",
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
    }


def gate(name, errors, checks, action):
    """Run `action`, then mark `checks[name]` ok or error based on the error delta."""
    before = len(errors)
    action()
    checks[name] = "error" if len(errors) > before else "ok"


def parse_frontmatter(text):
    """Parse minimal YAML-ish frontmatter from SKILL.md. Returns (meta, error_or_None)."""
    if not text.startswith("---\n"):
        return {}, "SKILL.md does not start with --- frontmatter delimiter"
    sections = text.split("---\n", 2)
    if len(sections) < 3:
        return {}, "SKILL.md frontmatter block is not closed"
    meta = {}
    last_key = None
    for line in sections[1].splitlines():
        if not line.strip():
            continue
        if line.startswith(" ") and last_key:
            meta[last_key] += " " + line.strip()
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        last_key = key.strip()
        meta[last_key] = value.strip().strip('"')
    return meta, None


def _check_python(path, errors):
    try:
        compile(path.read_text(), str(path), "exec")
    except (OSError, SyntaxError) as exc:
        errors.append(f"{path}: invalid Python: {exc}")


REFERENCE_PATTERN = re.compile(r"`((?:references|scripts|evals)/[^`\s]+)`")


if __name__ == "__main__":
    sys.exit(main())
