"""Run the Haskell benchmark or redraw its plot from a saved summary."""

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
PLOT_COLORS = {
    "(a*)*(?=.*b.*)": "red",
    "a*(?=.*b.*)": "blue",
    "(?=.*a.*)(?=.*b.*)": "green",
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src-dir", type=Path, default=HERE.parent / "src",
                        help="lregex/haskell/src (default: ../src relative to this file)")
    parser.add_argument("--output-dir", type=Path, default=Path("results/haskell_starts"),
                        help="parent directory for a new run")
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repetitions", type=int, default=21)
    parser.add_argument("--lengths", type=int, nargs="+", default=DEFAULT_LENGTHS)
    plots = parser.add_mutually_exclusive_group()
    plots.add_argument("--plot", action="store_true", help="also draw execution_time.png (Matplotlib)")
    plots.add_argument("--plot-only", type=Path, metavar="SUMMARY_CSV",
                       help="redraw execution_time.png beside an existing summary.csv")
    args = parser.parse_args()
    if args.plot_only is not None:
        if not args.plot_only.is_file():
            parser.error(f"summary CSV not found: {args.plot_only}")
        return args
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
    import numpy as np
    from matplotlib.ticker import FormatStrFormatter, MaxNLocator

    points = {regex: [] for regex in PLOT_COLORS}
    for row in summary:
        seconds = float(row["median_ns"]) / 1_000_000_000
        points[row["regex"]].append((int(row["text_length"]), seconds))
    if not any(points.values()):
        raise ValueError("summary contains no measurements")

    # Thesis Figure 4.1 is a 500 x 700 portrait image.
    fig, ax = pyplot.subplots(figsize=(5, 7), dpi=100)
    for regex, color in PLOT_COLORS.items():
        if not points[regex]:
            continue
        lengths, times = zip(*sorted(points[regex]))
        label = regex.replace("(?=", "(?>")  # Thesis notation for positive lookahead.
        ax.scatter(lengths, times, label=label, color=color, marker="o", s=49, alpha=0.7, zorder=3)
        if lengths[0] != lengths[-1]:
            endpoints = (lengths[0], lengths[-1])
            fit = np.polyfit(lengths, times, deg=1)
            ax.plot(endpoints, np.polyval(fit, endpoints), color=color, linewidth=1.5,
                    label=f"{label}\n  (poly fit, degree=1)")
    ax.set_xlabel("Size of string (number of characters)", fontsize=14)
    ax.set_ylabel("Time (seconds)", fontsize=14)
    ax.xaxis.set_major_locator(MaxNLocator(nbins="auto", steps=[1, 2, 2.5, 5, 10],
                                          integer=True, min_n_ticks=1))
    y_ticks = ax.get_yticks()
    if 0.0001 <= y_ticks[1] - y_ticks[0] < 0.1:
        ax.yaxis.set_major_formatter(FormatStrFormatter("%.4f"))
    ax.grid(True, axis="both", color="#b0b0b0", linewidth=0.8)
    ax.legend(loc="upper left", fontsize=12)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
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
    pyplot = None
    if args.plot or args.plot_only is not None:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as pyplot
            pyplot.style.use("default")
        except ImportError as error:
            raise SystemExit("Drawing the plot requires Matplotlib. Install it in this Python environment.") from error
    if args.plot_only is not None:
        output = args.plot_only.with_name("execution_time.png")
        with tempfile.TemporaryDirectory(dir=output.parent) as scratch:
            new_plot = Path(scratch) / output.name
            with args.plot_only.open(encoding="utf-8-sig", newline="") as file:
                try:
                    save_plot(new_plot, csv.DictReader(file), pyplot)
                except (KeyError, ValueError) as error:
                    raise SystemExit(f"Invalid benchmark summary {args.plot_only}: {error}") from error
            new_plot.replace(output)
        print(f"Plot: {output.resolve()}")
        return

    ghc = shutil.which("ghc")
    if not ghc:
        raise SystemExit("ghc was not found on PATH. Install GHC or select it on your server, then retry.")

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
