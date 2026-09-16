#!/usr/bin/env python3
"""Scale timing harness for snapshot / compare / offline probes (#100).

Informational only — timings are host-dependent and not gated in PR CI.

  python scripts/bench_scale.py
  python scripts/bench_scale.py --sizes 10,100,500
"""

from __future__ import annotations

import argparse
import json
import sys

from tool_semantics.benchmarks import (
    DEFAULT_SCALE_SIZES,
    render_scale_benchmark_markdown,
    run_scale_benchmark,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sizes",
        default=",".join(str(size) for size in DEFAULT_SCALE_SIZES),
        help="Comma-separated tool counts (default: 10,100,500,1000,5000)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of Markdown",
    )
    parser.add_argument(
        "--no-probes",
        action="store_true",
        help="Skip offline probe timings",
    )
    args = parser.parse_args(argv)
    sizes = tuple(int(part.strip()) for part in args.sizes.split(",") if part.strip())
    if not sizes or any(size < 1 for size in sizes):
        print("--sizes must be comma-separated integers >= 1", file=sys.stderr)
        return 2
    rows = run_scale_benchmark(sizes, include_probes=not args.no_probes)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(render_scale_benchmark_markdown(rows), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
