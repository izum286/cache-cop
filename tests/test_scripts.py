"""Subprocess-driven coverage for the cache-cop bundled scripts."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path


HERE = Path(__file__).resolve()
REPO = HERE.parents[1]
SCRIPT_DIR = REPO / "cache-cop" / "scripts"
SAMPLE_DIR = REPO / "samples"
USAGE_DIR = SAMPLE_DIR / "usage"
REQUEST_DIR = SAMPLE_DIR / "requests"
SNAPSHOT_DIR = SAMPLE_DIR / "snapshots"
VALIDATOR = HERE.parent / "validate_skill.py"
PROVIDERS = ("openai", "anthropic", "bedrock", "openrouter")


@contextmanager
def workspace():
    """Yield a fresh temporary directory as a Path; cleaned on exit."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def usage_log(provider):
    return USAGE_DIR / f"{provider}.jsonl"


def snapshot_file(provider, name):
    return SNAPSHOT_DIR / provider / name


class ScriptCase(unittest.TestCase):
    """Base: invoke bundled scripts via subprocess and decode JSON output."""

    def invoke(self, script, *args):
        cmd = [sys.executable, str(SCRIPT_DIR / script), *map(str, args)]
        return subprocess.run(
            cmd, cwd=REPO, text=True, capture_output=True, check=False
        )

    def invoke_validator(self, target):
        cmd = [sys.executable, str(VALIDATOR), str(target)]
        return subprocess.run(
            cmd, cwd=REPO, text=True, capture_output=True, check=False
        )

    def expect_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def expect_exit(self, result, code):
        self.assertEqual(result.returncode, code, result.stderr or result.stdout)


# --------------------------------------------------------------------------- #
# Fixture pack
# --------------------------------------------------------------------------- #


class FixturePackTest(ScriptCase):
    """Bundled samples and snapshots load cleanly and stay byte-stable."""

    def test_every_sample_path_exists(self):
        required = []
        for provider in PROVIDERS:
            required.append(usage_log(provider))
            required.append(snapshot_file(provider, "usage-summary.json"))
            required.append(snapshot_file(provider, "report.md"))
        for path in required:
            self.assertTrue(path.exists(), f"missing: {path}")

    def test_provider_records_carry_expected_telemetry(self):
        openai_records = read_jsonl(usage_log("openai"))
        self.assertEqual(len(openai_records), 4)
        self.assertEqual(openai_records[0]["provider"], "openai")
        self.assertIn("cached_tokens", openai_records[1]["usage"]["input_tokens_details"])

        anthropic_records = read_jsonl(usage_log("anthropic"))
        self.assertEqual(anthropic_records[0]["provider"], "anthropic")
        self.assertIn("cache_creation_input_tokens", anthropic_records[0]["usage"])
        self.assertIn("cache_read_input_tokens", anthropic_records[1]["usage"])

        bedrock_records = read_jsonl(usage_log("bedrock"))
        self.assertEqual(bedrock_records[0]["provider"], "bedrock")
        self.assertIn("CacheWriteInputTokens", bedrock_records[0]["metrics"])
        self.assertIn("CacheReadInputTokens", bedrock_records[1]["metrics"])

        openrouter_records = read_jsonl(usage_log("openrouter"))
        self.assertEqual(openrouter_records[0]["provider"], "openrouter")
        self.assertIn("cache_write_tokens", openrouter_records[0]["usage"])
        self.assertIn("route", openrouter_records[0])

    def test_summarize_usage_matches_each_provider_snapshot(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                expected = json.loads(snapshot_file(provider, "usage-summary.json").read_text())
                actual = self.expect_ok(self.invoke("summarize_usage.py", usage_log(provider)))
                self.assertEqual(actual, expected)

    def test_openai_snapshot_carries_expected_title(self):
        report = snapshot_file("openai", "report.md").read_text()
        self.assertIn("# Prompt-cache audit · openai (Responses API)", report)


# --------------------------------------------------------------------------- #
# diff_prefix
# --------------------------------------------------------------------------- #


class DiffPrefixTest(ScriptCase):
    """diff_prefix reports prefix drift between two rendered requests."""

    def _write_pair(self, ws, first_payload, second_payload):
        first = ws / "first.json"
        second = ws / "second.json"
        first.write_text(
            first_payload if isinstance(first_payload, str) else json.dumps(first_payload)
        )
        second.write_text(
            second_payload if isinstance(second_payload, str) else json.dumps(second_payload)
        )
        return first, second

    def test_first_difference_in_tool_order_is_reported(self):
        with workspace() as ws:
            first, second = self._write_pair(
                ws,
                {
                    "system": "Stable instructions",
                    "tools": [{"name": "lookup"}, {"name": "write"}],
                    "input": "Question A",
                },
                {
                    "system": "Stable instructions",
                    "tools": [{"name": "write"}, {"name": "lookup"}],
                    "input": "Question B",
                },
            )
            result = self.invoke("diff_prefix.py", first, second)

        self.expect_exit(result, 1)
        self.assertIn("stable_prefix_bytes", result.stdout)
        self.assertIn("first_difference", result.stdout)
        self.assertIn("tools", result.stdout)

    def test_raw_json_key_order_is_preserved_by_default(self):
        with workspace() as ws:
            first, second = self._write_pair(
                ws,
                '{"schema":{"type":"object","properties":{"a":{"type":"string"}}}}',
                '{"schema":{"properties":{"a":{"type":"string"}},"type":"object"}}',
            )
            result = self.invoke("diff_prefix.py", first, second)

        self.expect_exit(result, 1)
        envelope = json.loads(result.stdout.split("\n\n", 1)[0])
        self.assertFalse(envelope["stable"])
        self.assertIn("byte_offset", envelope["first_difference"])

    def test_canonical_json_flag_normalizes_key_order(self):
        with workspace() as ws:
            first, second = self._write_pair(
                ws,
                '{"schema":{"type":"object","properties":{"a":{"type":"string"}}}}',
                '{"schema":{"properties":{"a":{"type":"string"}},"type":"object"}}',
            )
            payload = self.expect_ok(
                self.invoke("diff_prefix.py", "--canonical-json", first, second)
            )
        self.assertTrue(payload["stable"])


# --------------------------------------------------------------------------- #
# summarize_usage
# --------------------------------------------------------------------------- #


class SummarizeUsageTest(ScriptCase):
    """summarize_usage handles JSONL/CSV and provider-specific token fields."""

    def test_mixed_openai_and_anthropic_jsonl_produce_combined_summary(self):
        with workspace() as ws:
            log = ws / "usage.jsonl"
            log.write_text("\n".join([
                json.dumps({"usage": {
                    "input_tokens": 2000,
                    "input_tokens_details": {"cached_tokens": 1500},
                    "output_tokens": 250,
                }}),
                json.dumps({"usage": {
                    "input_tokens": 500,
                    "cache_read_input_tokens": 300,
                    "cache_creation_input_tokens": 100,
                    "output_tokens": 50,
                }}),
            ]))
            summary = self.expect_ok(self.invoke("summarize_usage.py", log))

        self.assertEqual(summary["records"], 2)
        self.assertEqual(summary["input_tokens"], 2500)
        self.assertEqual(summary["total_input_tokens"], 2900)
        self.assertEqual(summary["cached_tokens"], 1500)
        self.assertEqual(summary["cache_read_input_tokens"], 300)
        self.assertEqual(summary["cache_creation_input_tokens"], 100)
        self.assertEqual(summary["cache_hit_ratio"], 0.6207)

    def test_normalized_jsonl_emits_one_event_per_record(self):
        result = self.invoke(
            "summarize_usage.py",
            "--jsonl-normalized",
            usage_log("openai"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        self.assertEqual(len(events), 4)
        self.assertEqual(events[0]["provider"], "openai")
        self.assertEqual(events[0]["model"], "gpt-5.2")
        self.assertEqual(events[0]["route"], "responses-api")
        self.assertEqual(events[0]["input_tokens"], 5400)
        self.assertEqual(events[0]["cache_read_input_tokens"], 0)
        self.assertEqual(events[0]["cache_creation_input_tokens"], 0)
        self.assertEqual(events[1]["cache_benefit_tokens"], 4800)
        self.assertEqual(events[1]["total_input_tokens"], 5400)
        self.assertEqual(events[2]["output_tokens"], 395)

    def test_anthropic_denominator_includes_cache_reads_and_creation(self):
        with workspace() as ws:
            log = ws / "anthropic.jsonl"
            log.write_text(json.dumps({"usage": {
                "input_tokens": 500,
                "cache_read_input_tokens": 300,
                "cache_creation_input_tokens": 200,
                "output_tokens": 50,
            }}))
            summary = self.expect_ok(self.invoke("summarize_usage.py", log))

        self.assertEqual(summary["input_tokens"], 500)
        self.assertEqual(summary["total_input_tokens"], 1000)
        self.assertEqual(summary["cache_hit_ratio"], 0.3)

    def test_csv_usage_columns_round_trip_through_summarizer(self):
        with workspace() as ws:
            log = ws / "usage.csv"
            with log.open("w", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["input_tokens", "cached_tokens", "output_tokens"],
                )
                writer.writeheader()
                for cached in ("600", "800"):
                    writer.writerow({
                        "input_tokens": "1000",
                        "cached_tokens": cached,
                        "output_tokens": "100",
                    })
            summary = self.expect_ok(self.invoke("summarize_usage.py", log))

        self.assertEqual(summary["records"], 2)
        self.assertEqual(summary["input_tokens"], 2000)
        self.assertEqual(summary["cached_tokens"], 1400)
        self.assertEqual(summary["cache_hit_ratio"], 0.7)

    def test_bedrock_read_field_does_not_inflate_cached_tokens(self):
        with workspace() as ws:
            log = ws / "bedrock.jsonl"
            log.write_text(json.dumps({"metrics": {
                "InputTokens": 1000,
                "CacheReadInputTokens": 400,
                "CacheWriteInputTokens": 200,
                "OutputTokens": 100,
            }}))
            summary = self.expect_ok(self.invoke("summarize_usage.py", log))

        self.assertEqual(summary["cached_tokens"], 0)
        self.assertEqual(summary["cache_read_input_tokens"], 400)
        self.assertEqual(summary["total_input_tokens"], 1600)
        self.assertEqual(summary["cache_hit_ratio"], 0.25)


# --------------------------------------------------------------------------- #
# roi
# --------------------------------------------------------------------------- #


class RoiTest(ScriptCase):
    """roi.py computes a cost delta from explicit token assumptions."""

    def test_cost_delta_matches_explicit_baseline(self):
        args = [
            "--static-tokens", "9000",
            "--dynamic-tokens", "300",
            "--output-tokens", "2000",
            "--requests", "100",
            "--hit-rate", "0.8",
            "--input-price-per-mtok", "2.0",
            "--cached-input-price-per-mtok", "0.2",
            "--output-price-per-mtok", "8.0",
        ]
        payload = self.expect_ok(self.invoke("roi.py", *args))

        expected = {
            "requests": 100,
            "input_baseline_cost": 1.86,
            "input_with_cache_cost": 0.564,
            "output_cost": 1.6,
            "total_baseline_cost": 3.46,
            "total_with_cache_cost": 2.164,
            "input_savings": 1.296,
            "total_savings_pct": 37.46,
        }
        for key, want in expected.items():
            self.assertEqual(payload[key], want, key)


# --------------------------------------------------------------------------- #
# render_report
# --------------------------------------------------------------------------- #


SNAPSHOT_CASES = (
    (
        "openai",
        "Responses API",
        "samples/usage/openai.jsonl:1 | low | openai | cold request has zero cached tokens | first request pays full prefill | warm repeated prefix before measuring steady state | confirm warm cached_tokens increase",
    ),
    (
        "anthropic",
        "Messages API",
        "samples/usage/anthropic.jsonl:1 | low | anthropic | cache_creation paid once with two reads | one write amortized across reads | extend cache TTL to reduce future writes | confirm cache_read_input_tokens stay non-zero across replicas",
    ),
    (
        "bedrock",
        "Converse API",
        "samples/usage/bedrock.jsonl:1 | low | bedrock | CacheWriteInputTokens dominates first request | first call pays full write | reuse cachePoint across requests in same region | confirm CacheReadInputTokens rise on warm calls",
    ),
    (
        "openrouter",
        "Chat Completions",
        "samples/usage/openrouter.jsonl:1 | low | openrouter | cached_tokens absent on first routed call | first call to routed_provider pays full prefill | pin provider.order or verify sticky-routing window | confirm cached_tokens increase on subsequent calls",
    ),
)


class RenderReportTest(ScriptCase):
    """render_report turns a usage log + finding tuple into markdown/JSON."""

    def test_markdown_output_contains_expected_headers_and_action_items(self):
        finding = (
            "samples/usage/openai.jsonl:1 | low | openai | "
            "cold request has zero cached tokens | first request pays full prefill | "
            "warm repeated prefix before measuring steady state | "
            "confirm warm cached_tokens increase"
        )
        result = self.invoke(
            "render_report.py",
            "--usage-log", usage_log("openai"),
            "--provider", "openai",
            "--engine", "Responses API",
            "--finding", finding,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout

        expected_substrings = [
            "# Prompt-cache audit · openai (Responses API)",
            "**Headline:** 4 requests, 67.36% cache hit, 1 finding (low).",
            "## Numbers",
            "## Issues",
            "## Action items",
            "| Cache hit ratio | 67.36% |",
            "| Measurement change | unknown |",
            "| Prompt behavior change | unknown |",
            "| Provider/routing change | unknown |",
            "| Confidence | low |",
            "- **Start with:** analyze usage logs and validate prefix stability",
            "- **Hold off on:** make provider/routing changes without telemetry",
            "cold request has zero cached tokens",
        ]
        for fragment in expected_substrings:
            self.assertIn(fragment, out)

    def test_json_output_carries_structured_audit_fields(self):
        finding = "PS-01 | low | openai | fixture finding | impact | fix | validation"
        payload = self.expect_ok(self.invoke(
            "render_report.py",
            "--json",
            "--usage-log", usage_log("openai"),
            "--provider", "openai",
            "--engine", "Responses API",
            "--finding", finding,
        ))

        self.assertEqual(payload["provider"], "openai")
        self.assertEqual(payload["engine"], "Responses API")
        self.assertEqual(payload["measurement_change"], "unknown")
        self.assertEqual(payload["prompt_behavior_change"], "unknown")
        self.assertEqual(payload["provider_routing_change"], "unknown")
        self.assertEqual(payload["confidence"], "low")
        self.assertEqual(
            payload["do_first"],
            "analyze usage logs and validate prefix stability",
        )
        self.assertEqual(
            payload["do_not_do_yet"],
            "make provider/routing changes without telemetry",
        )
        self.assertEqual(payload["usage"]["cache_hit_ratio"], 0.6736)
        self.assertEqual(payload["findings"][0]["severity"], "low")

    def test_extended_finding_columns_survive_round_trip(self):
        columns = [
            "app/services/llm/client.py:124",
            "medium",
            "openrouter",
            "dynamic opening message fragments route locality",
            "code shows session_id in the first user message",
            "confirmed from code",
            "medium",
            "matters when the operation has repeated long prefixes",
            "can split sticky-route cache families",
            "add observability without changing prompt behavior",
            "test a stable operation anchor on one hot path",
            "compare routed provider/model, cached_tokens, and cache_write_tokens",
            "do not add cache_control or pin providers yet",
        ]
        finding = " | ".join(columns)
        payload = self.expect_ok(self.invoke(
            "render_report.py",
            "--json",
            "--usage-log", usage_log("openai"),
            "--provider", "openrouter",
            "--engine", "Chat Completions",
            "--finding", finding,
        ))
        parsed = payload["findings"][0]
        self.assertEqual(parsed["source"], "app/services/llm/client.py:124")
        self.assertEqual(parsed["evidence"], "code shows session_id in the first user message")
        self.assertEqual(parsed["evidence_type"], "confirmed from code")
        self.assertEqual(parsed["confidence"], "medium")
        self.assertEqual(
            parsed["impact_condition"],
            "matters when the operation has repeated long prefixes",
        )
        self.assertEqual(
            parsed["safe_first_action"],
            "add observability without changing prompt behavior",
        )
        self.assertEqual(
            parsed["do_not_do_yet"],
            "do not add cache_control or pin providers yet",
        )

    def test_rendered_reports_match_provider_snapshots(self):
        for provider, engine, finding in SNAPSHOT_CASES:
            with self.subTest(provider=provider):
                result = self.invoke(
                    "render_report.py",
                    "--usage-log", usage_log(provider),
                    "--provider", provider,
                    "--engine", engine,
                    "--finding", finding,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    result.stdout,
                    snapshot_file(provider, "report.md").read_text(),
                )


# --------------------------------------------------------------------------- #
# scan_repo
# --------------------------------------------------------------------------- #


class ScanRepoTest(ScriptCase):
    """scan_repo walks a tree and identifies provider SDK signatures."""

    def test_openai_sdk_calls_in_src_are_picked_up_and_dotgit_ignored(self):
        with workspace() as ws:
            (ws / "src").mkdir()
            (ws / "src" / "llm.py").write_text("\n".join([
                "from openai import OpenAI",
                "client = OpenAI()",
                "def call(messages):",
                "    return client.responses.create(model='gpt-5.4', input=messages)",
            ]))
            (ws / ".git").mkdir()
            (ws / ".git" / "ignored.py").write_text(
                "client.responses.create(model='gpt-5.4', input='x')"
            )
            payload = self.expect_ok(self.invoke("scan_repo.py", ws))

        self.assertEqual(payload["files_scanned"], 1)
        self.assertEqual(payload["matches"], 2)
        self.assertEqual(payload["providers"]["openai"], 2)
        self.assertEqual(payload["findings"][0]["path"], "src/llm.py")

    def test_prompt_cache_retention_config_is_flagged_as_openai_signal(self):
        with workspace() as ws:
            (ws / "llm-config.json").write_text('{"prompt_cache_retention": "24h"}')
            payload = self.expect_ok(self.invoke("scan_repo.py", ws))

        self.assertEqual(payload["files_scanned"], 1)
        self.assertEqual(payload["providers"]["openai"], 1)
        self.assertEqual(payload["findings"][0]["path"], "llm-config.json")


# --------------------------------------------------------------------------- #
# validate_skill
# --------------------------------------------------------------------------- #


class ValidateSkillTest(ScriptCase):
    """tests/validate_skill.py runs structural checks on a skill package."""

    def test_real_cache_cop_package_passes_all_checks(self):
        payload = self.expect_ok(self.invoke_validator(REPO / "cache-cop"))

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["validation"]["status"], "ok")
        self.assertIn("SKILL.md", payload["validation"]["checks"])
        self.assertIn("scripts", payload["validation"]["checks"])
        self.assertEqual(payload["validation"]["errors"], [])

    def test_missing_reference_path_in_skill_md_raises_error(self):
        with workspace() as ws:
            skill = ws / "bad-skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text("\n".join([
                "---",
                "name: bad-skill",
                "description: Use when testing bad references",
                "---",
                "",
                "Load `references/missing.md`.",
            ]))
            result = self.invoke_validator(skill)

        self.expect_exit(result, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["validation"]["checks"]["references"], "error")
        self.assertTrue(
            any("references/missing.md" in err for err in payload["validation"]["errors"])
        )

    def test_broken_script_syntax_is_marked_as_script_check_error(self):
        with workspace() as ws:
            skill = ws / "bad-skill"
            (skill / "scripts").mkdir(parents=True)
            (skill / "SKILL.md").write_text("\n".join([
                "---",
                "name: bad-skill",
                "description: Use when testing bad package",
                "---",
            ]))
            (skill / "scripts" / "broken.py").write_text("def nope(:\n")
            result = self.invoke_validator(skill)

        self.expect_exit(result, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["validation"]["checks"]["scripts"], "error")


# --------------------------------------------------------------------------- #
# antipatterns.json schema
# --------------------------------------------------------------------------- #


class AntipatternsRefTest(unittest.TestCase):
    """The machine-readable antipattern catalog stays loadable and well-shaped."""

    def test_catalog_loads_with_expected_fields_and_severities(self):
        path = REPO / "cache-cop" / "references" / "antipatterns.json"
        self.assertTrue(path.exists(), "missing machine-readable antipatterns.json")

        data = json.loads(path.read_text())
        rules = {entry["ruleId"]: entry for entry in data["antipatterns"]}

        for required_id in ("PS-01", "PS-02", "RT-01"):
            self.assertIn(required_id, rules)

        required_keys = {"ruleId", "domain", "severity", "description", "detection"}
        allowed_severities = {"critical", "high", "medium", "low"}
        for entry in data["antipatterns"]:
            self.assertTrue(required_keys.issubset(entry.keys()))
            self.assertIn(entry["severity"], allowed_severities)


# --------------------------------------------------------------------------- #
# lint_request (parameterized)
# --------------------------------------------------------------------------- #


BAD_LINT_FIXTURES = (
    ("chat-bad.json", {"PS-01", "PS-02"}),
    ("responses-bad.json", {"PS-01"}),
)

GOOD_LINT_FIXTURES = (
    ("chat-good.json", {"PS-01", "PS-02"}),
    ("responses-good.json", {"PS-01"}),
)


class LintRequestTest(ScriptCase):
    """lint_request flags volatile content and confirms clean fixtures pass."""

    def test_bad_fixtures_emit_findings_for_expected_rules(self):
        for fixture, expected_ids in BAD_LINT_FIXTURES:
            with self.subTest(fixture=fixture):
                result = self.invoke("lint_request.py", REQUEST_DIR / fixture)
                self.expect_exit(result, 1)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["status"], "findings")
                hit_ids = {entry["rule_id"] for entry in payload["findings"]}
                self.assertTrue(
                    expected_ids.issubset(hit_ids),
                    f"{fixture}: expected {expected_ids} ⊂ {hit_ids}",
                )

    def test_good_fixtures_report_clean_checks(self):
        for fixture, clean_ids in GOOD_LINT_FIXTURES:
            with self.subTest(fixture=fixture):
                payload = self.expect_ok(
                    self.invoke("lint_request.py", REQUEST_DIR / fixture)
                )
                self.assertEqual(payload["status"], "ok")
                self.assertEqual(payload["findings"], [])
                self.assertTrue(clean_ids.issubset(set(payload["clean_checks"])))

    def test_string_input_payload_flags_volatile_prefix_data(self):
        body = {
            "model": "gpt-5.4",
            "input": (
                "Today is 2026-05-02. request_id=req_string_123. "
                "Stable reusable policy: apply the same compliance "
                "taxonomy for every request."
            ),
        }
        with workspace() as ws:
            target = ws / "responses-string.json"
            target.write_text(json.dumps(body))
            result = self.invoke("lint_request.py", target)

        self.expect_exit(result, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "findings")
        self.assertEqual(payload["findings"][0]["rule_id"], "PS-01")
        self.assertIn("input contains", payload["findings"][0]["evidence"])


if __name__ == "__main__":
    unittest.main()
