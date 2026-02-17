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
PROVIDERS = ("openai", "anthropic")


@contextmanager
def workspace():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def usage_log(provider):
    return USAGE_DIR / f"{provider}.jsonl"


def snapshot_file(provider, name):
    return SNAPSHOT_DIR / provider / name


class ScriptCase(unittest.TestCase):
    def invoke(self, script, *args):
        cmd = [sys.executable, str(SCRIPT_DIR / script), *map(str, args)]
        return subprocess.run(
            cmd, cwd=REPO, text=True, capture_output=True, check=False
        )

    def expect_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def expect_exit(self, result, code):
        self.assertEqual(result.returncode, code, result.stderr or result.stdout)


class FixturePackTest(ScriptCase):
    def test_every_sample_path_exists(self):
        required = []
        for provider in PROVIDERS:
            required.append(usage_log(provider))
            required.append(snapshot_file(provider, "usage-summary.json"))
            required.append(snapshot_file(provider, "report.md"))
        for path in required:
            self.assertTrue(path.exists(), f"missing: {path}")

    def test_summarize_usage_matches_each_provider_snapshot(self):
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                expected = json.loads(snapshot_file(provider, "usage-summary.json").read_text())
                actual = self.expect_ok(self.invoke("summarize_usage.py", usage_log(provider)))
                self.assertEqual(actual, expected)


class DiffPrefixTest(ScriptCase):
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
                {"tools": [{"name": "lookup"}, {"name": "write"}]},
                {"tools": [{"name": "write"}, {"name": "lookup"}]},
            )
            result = self.invoke("diff_prefix.py", first, second)
        self.expect_exit(result, 1)
        self.assertIn("first_difference", result.stdout)


class SummarizeUsageTest(ScriptCase):
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
        self.assertEqual(summary["cached_tokens"], 1500)
        self.assertEqual(summary["cache_read_input_tokens"], 300)

    def test_csv_usage_columns_round_trip(self):
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
        self.assertEqual(summary["cached_tokens"], 1400)


class RoiTest(ScriptCase):
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
        self.assertEqual(payload["input_baseline_cost"], 1.86)
        self.assertEqual(payload["total_savings_pct"], 37.46)


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
)


class RenderReportTest(ScriptCase):
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


class ScanRepoTest(ScriptCase):
    def test_openai_sdk_calls_are_picked_up(self):
        with workspace() as ws:
            (ws / "src").mkdir()
            (ws / "src" / "llm.py").write_text("\n".join([
                "from openai import OpenAI",
                "client = OpenAI()",
            ]))
            payload = self.expect_ok(self.invoke("scan_repo.py", ws))
        self.assertEqual(payload["providers"].get("openai", 0), 1)


class LintRequestTest(ScriptCase):
    def test_bad_chat_fixture_emits_findings(self):
        result = self.invoke("lint_request.py", REQUEST_DIR / "chat-bad.json")
        self.expect_exit(result, 1)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "findings")

    def test_good_chat_fixture_is_clean(self):
        payload = self.expect_ok(self.invoke("lint_request.py", REQUEST_DIR / "chat-good.json"))
        self.assertEqual(payload["status"], "ok")


if __name__ == "__main__":
    unittest.main()
