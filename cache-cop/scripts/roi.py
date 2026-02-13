#!/usr/bin/env python3
"""Project the dollar delta a prompt-cache hit rate buys you."""

import argparse
import json
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Project the dollar delta a prompt-cache hit rate buys you."
    )
    parser.add_argument("--requests", type=int, required=True)
    parser.add_argument("--static-tokens", type=float, required=True)
    parser.add_argument("--dynamic-tokens", type=float, required=True)
    parser.add_argument("--output-tokens", type=float, required=True)
    parser.add_argument("--hit-rate", type=float, required=True)
    parser.add_argument("--input-price-per-mtok", type=float, required=True)
    parser.add_argument("--cached-input-price-per-mtok", type=float, required=True)
    parser.add_argument("--output-price-per-mtok", type=float, required=True)
    args = parser.parse_args(argv)

    print(json.dumps(estimate(args), ensure_ascii=False, indent=2))
    return 0


def estimate(args):
    """Compare baseline vs cached cost given token volumes and pricing."""
    n = args.requests
    hit_rate = max(0.0, min(1.0, args.hit_rate))

    static = args.static_tokens * n
    dynamic = args.dynamic_tokens * n
    output = args.output_tokens * n
    cached = static * hit_rate
    uncached = static - cached

    baseline_in = cost(static + dynamic, args.input_price_per_mtok)
    cached_in = cost(uncached + dynamic, args.input_price_per_mtok) + cost(
        cached, args.cached_input_price_per_mtok
    )
    out = cost(output, args.output_price_per_mtok)
    baseline_total = baseline_in + out
    cached_total = cached_in + out

    delta_in = baseline_in - cached_in
    delta_total = baseline_total - cached_total

    return {
        "requests": n,
        "hit_rate": hit_rate,
        "input_baseline_cost": money(baseline_in),
        "input_with_cache_cost": money(cached_in),
        "output_cost": money(out),
        "total_baseline_cost": money(baseline_total),
        "total_with_cache_cost": money(cached_total),
        "input_savings": money(delta_in),
        "total_savings": money(delta_total),
        "input_savings_pct": safe_pct(delta_in, baseline_in),
        "total_savings_pct": safe_pct(delta_total, baseline_total),
        "output_share_of_baseline_cost": safe_pct(out, baseline_total),
    }


def cost(tokens, price_per_mtok):
    return tokens * price_per_mtok / 1_000_000


def money(value):
    return round(value, 6)


def pct(value):
    return round(value * 100, 2)


def safe_pct(numerator, denominator):
    return pct(numerator / denominator) if denominator else 0


if __name__ == "__main__":
    sys.exit(main())
