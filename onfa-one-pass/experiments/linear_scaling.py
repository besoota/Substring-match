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
from collections.abc import Callable
from datetime import datetime, timezone
from functools import partial
from inspect import signature
from pathlib import Path

# Direct script execution puts experiments/, rather than the project's src/,
# on sys.path. Prefer the engine shipped with this checkout.
SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"
if (SOURCE_DIR / "onfa_regex" / "engine.py").is_file():
    sys.path.insert(0, str(SOURCE_DIR))

try:
    from onfa_regex import engine
except ModuleNotFoundError as exc:
    if exc.name == "lark":
        raise SystemExit("Missing dependency 'lark'. Run python -m pip install -e . "
                         "from the project root with the same Python.") from None
    if exc.name == "onfa_regex":
        raise SystemExit("Cannot find onfa_regex. Place this script in the project's "
                         "experiments/ directory alongside ../src/onfa_regex/engine.py.") from None
    raise


TEXT_LENGTHS = list(range(1_000, 20_001, 1_000))
DEFAULT_STRATEGY = "prepared"
HAS_STRATEGY_ARG = "strategy" in signature(engine.evaluate_ast).parameters
FULL_STRATEGIES = ("auto", "baseline", "one_pass") if HAS_STRATEGY_ARG else ("baseline",)

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


def prepare_scan(ast: engine.AstNode, text: str) -> Callable[[], list[bool]]:
    """Prepare one input and return a callable that computes a fresh start tape."""
    if hasattr(engine, "prepare_match"):
        return engine.prepare_match(ast, text).start_tape

    # Earlier engines provide the same operations as separate functions.
    context = engine.Context()
    main = engine.EvalAux(ast, text, context)
    nfa = engine.ThompsonConstruction(engine.reverse_ast(main)).construct()
    return partial(engine.SimulateR2L, nfa, text, context.tapes)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark ONFA matching on text a^n.",
    )
    parser.add_argument(
        "--strategy",
        choices=(*FULL_STRATEGIES, "prepared"),
        default=DEFAULT_STRATEGY,
        help="Select the evaluation strategy (default: %(default)s). "
             "prepared times only the main scan with precomputed inner oracle tapes.",
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
        help="Default: results/prepared for prepared, results/linear_scaling otherwise.",
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
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def write_metadata(
    output_dir: Path,
    repetitions: int,
    warmups: int,
    selected_patterns: list[str],
    strategy: str = DEFAULT_STRATEGY,
) -> None:
    metadata = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "git_commit": git_commit(),
        "engine_file": str(Path(engine.__file__).resolve()),
        "text_lengths": TEXT_LENGTHS,
        "repetitions": repetitions,
        "warmups": warmups,
        "strategy": strategy,
        "patterns": {
            name: {
                "engine_regex": PATTERNS[name],
                "source_regex": SOURCE_PATTERNS[name],
            }
            for name in selected_patterns
        },
        "measurement_scope": (
            "One right-to-left scan of the compiled main ONFA (SimulateR2L), "
            "reading the inner oracle matrix and allocating/filling a fresh "
            "output tape for (?=r). Inner tapes and the main ONFA are prepared "
            "once per (regex, text) before warmups. Reference evaluation, "
            "validation, counting, explicit garbage collection, and file output are untimed."
            if strategy == "prepared" else
            "One evaluate_ast call, including lookaround lowering, Thompson "
            "construction, ONFA simulation, and the output tape. Parsing, "
            "text construction, garbage collection before each timed call, "
            "match counting, and file output are excluded."
        ),
        "package_versions": {
            name: package_version(name)
            for name in ("lark", "numpy", "pandas", "matplotlib")
        },
    }
    metadata["input"] = "a repeated text_length times"
    metadata["timer"] = "time.perf_counter_ns"
    path = output_dir / "metadata.json"
    path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def benchmark(
    selected_patterns: list[str],
    repetitions: int,
    warmups: int,
    strategy: str = DEFAULT_STRATEGY,
) -> tuple[list[dict], list[dict]]:
    raw_rows: list[dict] = []
    summary_rows: list[dict] = []
    if strategy not in (*FULL_STRATEGIES, "prepared"):
        raise ValueError(f"The selected engine does not support strategy {strategy!r}")
    strategy_args = {"strategy": strategy} if HAS_STRATEGY_ARG else {}

    for pattern_name in selected_patterns:
        regex = PATTERNS[pattern_name]
        source_regex = SOURCE_PATTERNS[pattern_name]
        ast = engine.build_ast(regex)

        for n in TEXT_LENGTHS:
            text = "a" * n
            setup_ns = None
            reference = None
            if strategy == "prepared":
                setup_started = time.perf_counter_ns()
                run = prepare_scan(ast, text)
                setup_ns = time.perf_counter_ns() - setup_started
                reference = engine.evaluate_ast(ast, text)
            else:
                run = partial(engine.evaluate_ast, ast, text, **strategy_args)
            for _ in range(warmups):
                run()

            samples: list[int] = []
            expected_match_count: int | None = None

            for repetition in range(repetitions):
                gc.collect()

                started_at = time.perf_counter_ns()
                tape = run()
                elapsed_ns = time.perf_counter_ns() - started_at

                if reference is not None and tape != reference:
                    raise RuntimeError(f"Incorrect start tape for {regex!r}, n={n}")
                match_count = sum(tape)
                del tape
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
                        "strategy": strategy,
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
                    "strategy": strategy,
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
            if setup_ns is not None:
                summary_rows[-1]["prepare_once_ns"] = setup_ns

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


def timing_slopes(summary: list[dict], selected_patterns: list[str]) -> list[dict]:
    """Fit median_ms = intercept_ms + slope * text_length for each pattern."""
    fits = []
    for name in selected_patterns:
        rows = [row for row in summary if row["pattern_name"] == name]
        fit = statistics.linear_regression(
            [row["text_length"] for row in rows],
            [row["median_ms"] for row in rows],
        )
        fits.append({
            "strategy": rows[0]["strategy"],
            "regex": PATTERNS[name],
            "slope_us_per_character": fit.slope * 1000,
            "intercept_ms": fit.intercept,
            "length_count": len(rows),
        })
    return fits


def main() -> None:
    args = parse_args()
    if args.repetitions < 2:
        raise ValueError("--repetitions must be at least 2")
    if args.warmups < 0:
        raise ValueError("--warmups must be non-negative")

    if args.output_dir is None:
        args.output_dir = Path("results/prepared" if args.strategy == "prepared"
                               else "results/linear_scaling")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_metadata(
        args.output_dir,
        args.repetitions,
        args.warmups,
        args.patterns,
        args.strategy,
    )

    raw_rows, summary_rows = benchmark(
        args.patterns,
        args.repetitions,
        args.warmups,
        args.strategy,
    )
    write_csv(args.output_dir / "raw_timings.csv", raw_rows)
    write_csv(args.output_dir / "summary.csv", summary_rows)
    write_csv(args.output_dir / "slopes.csv", timing_slopes(summary_rows, args.patterns))

    print(f"Results written to: {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()

