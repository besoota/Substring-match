"""Measure ONFA matching time for text a^n, n=1000,...,20000."""

from __future__ import annotations

import argparse
import csv
import gc
import importlib.metadata
import json
import platform
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from onfa_regex import build_ast, evaluate_ast


TEXT_LENGTHS = list(range(1_000, 20_001, 1_000))

PATTERNS = {
    "nested_star_with_lookahead": "(a*)*(?=.*b.*)",
    "star_with_lookahead": "a*(?=.*b.*)",
    "two_lookaheads": "(?=.*a.*)(?=.*b.*)",
}

# Notation used in the prior study.  The matcher itself accepts PCRE-style
# (?=...) syntax, while the source uses its own (?>...) syntax.
SOURCE_PATTERNS = {
    "nested_star_with_lookahead": "(a*)*(?>.*b.*)",
    "star_with_lookahead": "a*(?>.*b.*)",
    "two_lookaheads": "(?>.*a.*)(?>.*b.*)",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark ONFA matching on text a^n.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=21,
        help="Number of measured executions for each condition.",
    )
    parser.add_argument(
        "--warmups",
        type=int,
        default=3,
        help="Number of unmeasured warm-up executions.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/linear_scaling"),
        help="Directory for CSV and metadata files.",
    )
    parser.add_argument(
        "--patterns",
        nargs="+",
        choices=tuple(PATTERNS),
        default=list(PATTERNS),
        help="Pattern groups to measure.",
    )
    return parser.parse_args()


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def git_commit() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def write_metadata(
    output_dir: Path,
    repetitions: int,
    warmups: int,
    selected_patterns: list[str],
) -> None:
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "git_commit": git_commit(),
        "text_lengths": TEXT_LENGTHS,
        "repetitions": repetitions,
        "warmups": warmups,
        "patterns": {
            name: {
                "engine_regex": PATTERNS[name],
                "source_regex": SOURCE_PATTERNS[name],
            }
            for name in selected_patterns
        },
        "measurement_scope": (
            "Context construction, recursive lookaround evaluation, "
            "Thompson construction, and ONFA simulation. "
            "Lark parsing and text construction are excluded."
        ),
        "package_versions": {
            name: package_version(name)
            for name in ("lark", "numpy", "pandas", "matplotlib")
        },
    }
    path = output_dir / "metadata.json"
    path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def benchmark(
    selected_patterns: list[str],
    repetitions: int,
    warmups: int,
) -> tuple[list[dict], list[dict]]:
    raw_rows: list[dict] = []
    summary_rows: list[dict] = []

    for pattern_name in selected_patterns:
        regex = PATTERNS[pattern_name]
        source_regex = SOURCE_PATTERNS[pattern_name]
        ast = build_ast(regex)

        for n in TEXT_LENGTHS:
            text = "a" * n

            for _ in range(warmups):
                evaluate_ast(ast, text)

            samples: list[int] = []
            expected_match_count: int | None = None

            for repetition in range(repetitions):
                gc.collect()

                started_at = time.perf_counter_ns()
                tape = evaluate_ast(ast, text)
                elapsed_ns = time.perf_counter_ns() - started_at

                match_count = sum(tape)
                if expected_match_count is None:
                    expected_match_count = match_count
                elif match_count != expected_match_count:
                    raise RuntimeError(
                        "The same condition produced different match counts"
                    )

                samples.append(elapsed_ns)
                raw_rows.append(
                    {
                        "pattern_name": pattern_name,
                        "regex": regex,
                        "source_regex": source_regex,
                        "text_length": n,
                        "repetition": repetition,
                        "elapsed_ns": elapsed_ns,
                        "match_count": match_count,
                    }
                )

            quartiles = statistics.quantiles(
                samples,
                n=4,
                method="inclusive",
            )
            median_ns = statistics.median(samples)

            summary_rows.append(
                {
                    "pattern_name": pattern_name,
                    "regex": regex,
                    "source_regex": source_regex,
                    "text_length": n,
                    "repetitions": repetitions,
                    "median_ns": median_ns,
                    "median_ms": median_ns / 1_000_000,
                    "ns_per_character": median_ns / n,
                    "q1_ns": quartiles[0],
                    "q3_ns": quartiles[2],
                    "min_ns": min(samples),
                    "max_ns": max(samples),
                    "match_count": expected_match_count,
                }
            )

            print(
                f"{pattern_name:24s} n={n:5d} "
                f"median={median_ns / 1_000_000:10.3f} ms"
            )

    return raw_rows, summary_rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError("No experiment rows were generated")
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    if args.repetitions < 2:
        raise ValueError("--repetitions must be at least 2")
    if args.warmups < 0:
        raise ValueError("--warmups must be non-negative")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_metadata(
        args.output_dir,
        args.repetitions,
        args.warmups,
        args.patterns,
    )

    raw_rows, summary_rows = benchmark(
        args.patterns,
        args.repetitions,
        args.warmups,
    )
    write_csv(args.output_dir / "raw_timings.csv", raw_rows)
    write_csv(args.output_dir / "summary.csv", summary_rows)

    print(f"Results written to: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()

