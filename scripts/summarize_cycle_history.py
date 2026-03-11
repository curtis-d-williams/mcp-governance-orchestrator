# SPDX-License-Identifier: MIT
"""Thin CLI wrapper for summarizing archived governed cycle history."""

import argparse
import json

from cycle_history_runtime import (
    _CSV_FIELDS,
    _extract_risk_level,
    _extract_selected_actions,
    _extract_timestamp,
    _summarize_cycle_file,
    _write_csv,
    _write_json,
    summarize_cycle_history,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Summarize archived governed portfolio cycle artifacts.",
        add_help=True,
    )
    parser.add_argument("--archive-dir", default="artifacts/cycles", metavar="DIR",
                        help="Directory of archived cycle artifacts (default: artifacts/cycles).")
    parser.add_argument("--output", default=None, metavar="FILE",
                        help="Output file path. Omit to print to stdout.")
    parser.add_argument("--format", default="json", choices=["json", "csv"],
                        help="Output format: json or csv (default: json).")

    args = parser.parse_args(argv)
    rows = summarize_cycle_history(args.archive_dir)

    if args.format == "csv":
        _write_csv(args.output, rows)
    else:
        if args.output is not None:
            _write_json(args.output, rows)
        else:
            print(json.dumps(rows, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
