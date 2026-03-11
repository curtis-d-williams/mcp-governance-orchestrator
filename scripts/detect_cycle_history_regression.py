# SPDX-License-Identifier: MIT
"""Thin CLI wrapper for detecting cycle history regression."""

import argparse
import sys

from cycle_history_runtime import (
    _UNKNOWN_STATUS_RANK,
    _STATUS_RANK,
    _detect_signals,
    _extract_summary_context,
    _sorted_tasks,
    _status_rank,
    _write_json,
    detect_cycle_history_regression,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Detect regressions in governed cycle history (Phase K).",
        add_help=True,
    )
    parser.add_argument("--history", required=True, metavar="FILE",
                        help="Path to cycle_history.json.")
    parser.add_argument("--summary", required=True, metavar="FILE",
                        help="Path to cycle_history_summary.json.")
    parser.add_argument("--output", required=True, metavar="FILE",
                        help="Output path for the regression report JSON.")

    args = parser.parse_args(argv)
    sys.exit(detect_cycle_history_regression(
        args.history, args.summary, args.output
    ))


if __name__ == "__main__":
    main()
