# SPDX-License-Identifier: MIT
"""Thin CLI wrapper for updating cycle history."""

import argparse
import sys

from cycle_history_runtime import (
    _RECORD_KEYS,
    _normalize_record,
    _try_read_json,
    _utcnow_iso,
    _write_json,
    update_cycle_history,
)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Append a normalized cycle record to cycle_history.json.",
        add_help=True,
    )
    parser.add_argument("--cycle-artifact", required=True, metavar="FILE",
                        help="Path to governed_portfolio_cycle.json.")
    parser.add_argument("--output", required=True, metavar="FILE",
                        help="Path to cycle_history.json (created if absent).")

    args = parser.parse_args(argv)
    sys.exit(update_cycle_history(args.cycle_artifact, args.output))


if __name__ == "__main__":
    main()
