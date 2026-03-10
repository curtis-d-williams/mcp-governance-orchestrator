# SPDX-License-Identifier: MIT
"""Aggregate per-task action effectiveness from execution_history.json.

Reads execution_history.json produced by update_execution_history.py and
writes a deterministic action_effectiveness_ledger.json.  Running this
script multiple times against the same history file always produces the
same output (idempotent).

Usage:
    python3 scripts/update_action_effectiveness_from_history.py \\
        --execution-history execution_history.json \\
        --output action_effectiveness_ledger.json

Exit codes:
    0  — ledger written
    1  — error (unreadable or invalid input)
"""

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# JSON helper
# ---------------------------------------------------------------------------

def _write_json(path, data):
    """Write *data* as deterministic JSON (indent=2, sort_keys, trailing newline)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _aggregate(records):
    """Return an actions dict aggregated from *records*.

    For each record:
      - selected_tasks defaults to [] if missing
      - status != "ok" is treated as a failure

    Returns:
        dict mapping task_name → {"failure_count", "last_status",
                                   "success_count", "total_runs"}
    """
    actions = {}
    for record in records:
        tasks = record.get("selected_tasks") or []
        status = record.get("status")
        for task in tasks:
            if task not in actions:
                actions[task] = {
                    "failure_count": 0,
                    "last_status": None,
                    "success_count": 0,
                    "total_runs": 0,
                }
            entry = actions[task]
            entry["total_runs"] += 1
            if status == "ok":
                entry["success_count"] += 1
            else:
                entry["failure_count"] += 1
            entry["last_status"] = status
    return actions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def update_action_effectiveness_from_history(execution_history_path, output_path):
    """Aggregate execution history into an action effectiveness ledger.

    Args:
        execution_history_path: Path to execution_history.json.
        output_path:            Destination for action_effectiveness_ledger.json.

    Returns:
        0 on success, 1 on error.
    """
    try:
        history = json.loads(
            Path(execution_history_path).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot read execution history: {exc}\n")
        return 1

    records = history.get("records")
    if not isinstance(records, list):
        sys.stderr.write("error: execution history must contain 'records' as a list\n")
        return 1

    actions = _aggregate(records)
    _write_json(output_path, {"actions": actions})
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Aggregate action effectiveness from execution_history.json.",
        add_help=True,
    )
    parser.add_argument("--execution-history", required=True, metavar="FILE",
                        help="Path to execution_history.json.")
    parser.add_argument("--output", required=True, metavar="FILE",
                        help="Output path for action_effectiveness_ledger.json.")

    args = parser.parse_args(argv)
    sys.exit(update_action_effectiveness_from_history(
        args.execution_history, args.output
    ))


if __name__ == "__main__":
    main()
