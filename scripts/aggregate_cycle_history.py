# SPDX-License-Identifier: MIT
"""Thin CLI wrapper for aggregating cycle history."""

import argparse
import sys

from cycle_history_runtime import (
    _compute_summary,
    _write_json,
    aggregate_cycle_history,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Aggregate a summary from cycle_history.json (Phase I output).",
        add_help=True,
    )
    parser.add_argument("--history", required=True, metavar="FILE",
                        help="Path to cycle_history.json.")
    parser.add_argument("--output", required=True, metavar="FILE",
                        help="Output path for the cycle history summary JSON.")

    args = parser.parse_args(argv)
    sys.exit(aggregate_cycle_history(args.history, args.output))


if __name__ == "__main__":
    main()
