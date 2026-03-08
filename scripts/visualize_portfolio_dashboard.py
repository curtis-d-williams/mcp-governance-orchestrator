#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate a portfolio dashboard summary PNG from tier3_portfolio_report.csv."""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

CSV_PATH = Path("tier3_portfolio_report.csv")
PNG_PATH = Path("tier3_portfolio_dashboard_summary.png")


def main() -> int:
    if not CSV_PATH.exists():
        print(f"error: CSV not found: {CSV_PATH}", file=sys.stderr)
        return 1

    df = pd.read_csv(CSV_PATH)

    fig, ax = plt.subplots(figsize=(8, 4))

    if "task" in df.columns and not df.empty:
        task_counts = df["task"].value_counts().sort_index()
        ax.bar(task_counts.index, task_counts.values)
        ax.set_title("Portfolio Task Run Summary")
        ax.set_xlabel("Task")
        ax.set_ylabel("Repo Count")
        plt.xticks(rotation=30, ha="right")
    else:
        ax.text(0.5, 0.5, "No task data", transform=ax.transAxes, ha="center")
        ax.set_title("Portfolio Dashboard")

    plt.tight_layout()
    fig.savefig(PNG_PATH)
    plt.close(fig)
    print(f"Dashboard saved to {PNG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
