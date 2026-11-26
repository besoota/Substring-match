"""Build the Haskell benchmark, collect its timings, and summarize each length."""

import argparse
import csv
import hashlib
import io
import json
import os
import platform
import shutil
import statistics
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent
BUILD_FLAGS = ["--make", "-O2"]
DEFAULT_LENGTHS = list(range(1000, 20001, 1000))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src-dir", type=Path, default=HERE.parent / "src",
                        help="lregex/haskell/src (default: ../src relative to this file)")
    parser.add_argument("--output-dir", type=Path, default=Path("results/haskell_starts"),
                        help="parent directory for a new run")
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repetitions", type=int, default=21)
    parser.add_argument("--lengths", type=int, nargs="+", default=DEFAULT_LENGTHS)
    parser.add_argument("--plot", action="store_true", help="also draw execution_time.png (Matplotlib)")
    args = parser.parse_args()
    if args.warmups < 0 or args.repetitions < 1:
        parser.error("use --warmups >= 0 and --repetitions >= 1")
    if any(n < 0 for n in args.lengths) or len(set(args.lengths)) != len(args.lengths):
        parser.error("--lengths must contain distinct, nonnegative integers")
    args.src_dir = args.src_dir.resolve()
    for name in ("Extracted.hs", "Utils.hs"):
        if not (args.src_dir / name).is_file():
            parser.error(f"missing {name} in {args.src_dir}; give --src-dir /path/to/lregex/haskell/src")
    return args


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows, repetitions):
    groups = {}
    for row in rows:
        groups.setdefault((row["pattern_name"], row["regex"]), []).append(row)
    if len(groups) != 3 or any(len(values) != repetitions for values in groups.values()):
        raise ValueError("incomplete output from the Haskell benchmark")
    result = []
    for (name, regex), samples in groups.items():
        times = [int(row["elapsed_ns"]) for row in samples]
        median_ns = statistics.median(times)
        result.append({
            "pattern_name": name, "regex": regex, "text_length": int(samples[0]["text_length"]),
            "repetitions": len(times), "median_ns": median_ns, "median_ms": median_ns / 1e6,
            "min_ns": min(times), "max_ns": max(times), "match_count": int(samples[0]["match_count"]),
        })
    return result


def save_plot(path, summary, pyplot):
    fig, ax = pyplot.subplots(figsize=(8, 4.8), constrained_layout=True)
    patterns = list(dict.fromkeys(row["regex"] for row in summary))
    for regex, marker, color in zip(patterns, ("o", "s", "^"), ("#ac3536", "#275f9c", "#21784d")):
        points = sorted((r["text_length"], r["median_ms"]) for r in summary if r["regex"] == regex)
        ax.plot(*zip(*points), label=regex, marker=marker, markersize=4, color=color, linewidth=1.4)
    ax.set(xlabel="Input length n", ylabel="Median matching time (ms)", ylim=(0, None))
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.savefig(path, dpi=180)
    pyplot.close(fig)


def cpu_model():
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(errors="replace").splitlines():
            if line.startswith("model name") and ":" in line:
                return line.split(":", 1)[1].strip()
    return platform.processor() or platform.machine()


def git_revision(src):
    if not shutil.which("git"):
        return None
    result = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def main():
    args = parse_args()
    ghc = shutil.which("ghc")
    if not ghc:
        raise SystemExit("ghc was not found on PATH. Install GHC or select it on your server, then retry.")
    pyplot = None
    if args.plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as pyplot
        except ImportError as error:
            raise SystemExit("--plot requires Matplotlib. Install it or omit --plot to produce the CSV files.") from error

    started = datetime.now(timezone.utc)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    # Publish each completed set of CSV files as one directory, even for concurrent runs.
    with tempfile.TemporaryDirectory(prefix=".starts-", dir=args.output_dir) as scratch:
        work = Path(scratch).resolve()
        data = work / "data"
        build = work / "build"
        data.mkdir()
        build.mkdir()
        executable = build / ("bench-starts.exe" if os.name == "nt" else "bench-starts")
        subprocess.run([ghc, *BUILD_FLAGS, "-i", "-i" + str(HERE), "-i" + str(args.src_dir),
                        "-outputdir", str(build), str(HERE / "BenchStarts.hs"), "-o", str(executable)],
                       check=True)
        raw, summary = [], []
        for n in args.lengths:
            arguments = [str(executable), str(n), str(args.warmups), str(args.repetitions)]
            completed = subprocess.run(arguments, stdout=subprocess.PIPE, text=True, check=True)
            rows = list(csv.DictReader(io.StringIO(completed.stdout)))
            raw.extend(rows)
            summary.extend(summarize(rows, args.repetitions))
            print(f"n={n} complete", flush=True)
        write_csv(data / "raw_timings.csv", raw)
        write_csv(data / "summary.csv", summary)
        metadata = {
            "started_at_utc": started.isoformat(),
            "ghc_version": subprocess.check_output([ghc, "--numeric-version"], text=True).strip(),
            "build_flags": BUILD_FLAGS, "platform": platform.platform(), "cpu": cpu_model(),
            "upstream_git_commit": git_revision(args.src_dir),
            "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                              [args.src_dir / "Extracted.hs", args.src_dir / "Utils.hs",
                               HERE / "SubstringStarts.hs", HERE / "BenchStarts.hs"]},
            "patterns": list(dict.fromkeys(row["regex"] for row in summary)),
            "input": "the character a repeated n times", "lengths": args.lengths,
            "warmups": args.warmups, "repetitions": args.repetitions,
            "clock": "GHC.Clock.getMonotonicTimeNSec", "gc": "performGC before each timer",
            "timed": "evaluate (force (startPositions regex input)), including oracle evaluation, main scan and enumeration",
            "untimed": "compilation, AST/input construction, warmups, explicit GC, validation, counting, I/O",
        }
        (data / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        if pyplot is not None:
            save_plot(data / "execution_time.png", summary, pyplot)
        run_id = started.strftime("run-%Y%m%dT%H%M%SZ") + "-" + work.name.split("-")[-1]
        output = args.output_dir.resolve() / run_id
        data.rename(output)
    print(f"Results: {output}")


if __name__ == "__main__":
    main()
