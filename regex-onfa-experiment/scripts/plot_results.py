"""Create scaling plots and numerical estimates from summary.csv."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "summary_csv",
        type=Path,
        help="summary.csv produced by linear_scaling.py",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Defaults to the directory containing summary.csv",
    )
    return parser.parse_args()


def save_line_plot(
    frame: pd.DataFrame,
    y_column: str,
    y_label: str,
    title: str,
    path: Path,
    log_scale: bool = False,
) -> None:
    figure, axis = plt.subplots(figsize=(9, 6))

    for pattern_name, group in frame.groupby("pattern_name"):
        group = group.sort_values("text_length")
        axis.plot(
            group["text_length"],
            group[y_column],
            marker="o",
            markersize=3,
            label=pattern_name,
        )

    if log_scale:
        axis.set_xscale("log")
        axis.set_yscale("log")

    axis.set_xlabel("Text length n")
    axis.set_ylabel(y_label)
    axis.set_title(title)
    axis.grid(True, alpha=0.3)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=300)
    plt.close(figure)


def calculate_complexity_estimates(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for pattern_name, group in frame.groupby("pattern_name"):
        group = group.sort_values("text_length")
        tail = group.iloc[len(group) // 2 :]

        log_n = np.log(tail["text_length"].to_numpy(dtype=float))
        log_time = np.log(tail["median_ns"].to_numpy(dtype=float))
        exponent, intercept = np.polyfit(log_n, log_time, 1)

        predicted = exponent * log_n + intercept
        residual_sum = np.sum((log_time - predicted) ** 2)
        total_sum = np.sum((log_time - np.mean(log_time)) ** 2)
        r_squared = 1.0 - residual_sum / total_sum

        rows.append(
            {
                "pattern_name": pattern_name,
                "estimated_exponent": exponent,
                "log_log_r_squared": r_squared,
                "fit_min_n": int(tail["text_length"].min()),
                "fit_max_n": int(tail["text_length"].max()),
            }
        )

    return pd.DataFrame(rows)


def calculate_doubling_ratios(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for pattern_name, group in frame.groupby("pattern_name"):
        times = dict(zip(group["text_length"], group["median_ns"]))
        for n in sorted(times):
            if 2 * n not in times:
                continue
            rows.append(
                {
                    "pattern_name": pattern_name,
                    "n": int(n),
                    "two_n": int(2 * n),
                    "time_ratio_T_2n_over_T_n": times[2 * n] / times[n],
                }
            )

    return pd.DataFrame(rows)


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or args.summary_csv.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    frame = pd.read_csv(args.summary_csv)
    required_columns = {
        "pattern_name",
        "text_length",
        "median_ns",
        "median_ms",
        "ns_per_character",
    }
    missing = required_columns.difference(frame.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")

    save_line_plot(
        frame,
        "median_ms",
        "Time [ms]",
        "ONFA execution time for a^n",
        output_dir / "execution_time.png",
    )
    save_line_plot(
        frame,
        "ns_per_character",
        "Time [ns]",
        "ONFA execution time for a character",
        output_dir / "time_per_character.png",
    )
    save_line_plot(
        frame,
        "median_ns",
        "Time [ns]",
        "Log of ONFA execution time",
        output_dir / "log_log_execution_time.png",
        log_scale=True,
    )

    estimates = calculate_complexity_estimates(frame)
    estimates.to_csv(
        output_dir / "complexity_estimates.csv",
        index=False,
    )

    doubling_ratios = calculate_doubling_ratios(frame)
    doubling_ratios.to_csv(
        output_dir / "doubling_ratios.csv",
        index=False,
    )

    print(f"Plots and analyses written to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()

