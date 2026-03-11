# SPDX-License-Identifier: MIT
"""Phase J: compute an aggregate summary from cycle_history.json.

Reads the cycle history index produced by Phase I (update_cycle_history.py)
and produces a deterministic aggregate summary.  Answers questions such as:

  - How many governed cycles have run?
  - Which tasks are selected most often?
  - What fraction of cycles succeeded vs. aborted?
  - Which ledger sources are being consumed?
  - When was the most recent cycle?

This script is read-only with respect to the history; it never modifies it.

Usage:
    python3 scripts/aggregate_cycle_history.py \\
        --history artifacts/cycle_history.json \\
        --output artifacts/cycle_history_summary.json

Exit codes:
    0  — summary written (empty history is valid and returns a zero-count summary)
    1  — error (unreadable input, bad JSON, or invalid schema)
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
# Core aggregation
# ---------------------------------------------------------------------------

def _compute_summary(cycles):
    """Return a deterministic aggregate summary dict from *cycles*.

    Args:
        cycles: list of cycle record dicts from cycle_history.json.

    Returns:
        dict with the aggregate summary fields.
    """
    total = len(cycles)

    if total == 0:
        return {
            "average_tasks_selected_per_cycle": 0.0,
            "cycles_total": 0,
            "cycles_with_selected_tasks": 0,
            "ledger_source_counts": {},
            "most_recent_cycle_timestamp": None,
            "status_counts": {},
            "success_rate": None,
            "task_selection_counts": {},
            "unique_tasks_selected": 0,
        }

    status_counts = {}
    ledger_source_counts = {}
    task_selection_counts = {}
    cycles_with_tasks = 0
    total_tasks_selected = 0
    timestamps = []

    for cycle in cycles:
        # Status aggregation
        status = cycle.get("status")
        if status is not None:
            status_counts[status] = status_counts.get(status, 0) + 1

        # Ledger source aggregation
        ledger_source = cycle.get("ledger_source")
        if ledger_source is not None:
            ledger_source_counts[ledger_source] = (
                ledger_source_counts.get(ledger_source, 0) + 1
            )

        # Task frequency aggregation
        tasks = cycle.get("selected_tasks") or []
        if tasks:
            cycles_with_tasks += 1
        total_tasks_selected += len(tasks)
        for task in tasks:
            task_selection_counts[task] = task_selection_counts.get(task, 0) + 1

        # Timestamp for most-recent detection (lexicographic max works for ISO-8601)
        ts = cycle.get("timestamp")
        if ts is not None:
            timestamps.append(ts)

    ok_count = status_counts.get("ok", 0)
    success_rate = ok_count / total

    most_recent = max(timestamps) if timestamps else None

    avg_tasks = total_tasks_selected / total

    return {
        "average_tasks_selected_per_cycle": avg_tasks,
        "cycles_total": total,
        "cycles_with_selected_tasks": cycles_with_tasks,
        "ledger_source_counts": ledger_source_counts,
        "most_recent_cycle_timestamp": most_recent,
        "status_counts": status_counts,
        "success_rate": success_rate,
        "task_selection_counts": task_selection_counts,
        "unique_tasks_selected": len(task_selection_counts),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def aggregate_cycle_history(history_path, output_path):
    """Read *history_path* and write an aggregate summary to *output_path*.

    Args:
        history_path: Path to cycle_history.json produced by Phase I.
        output_path:  Destination path for the summary JSON.

    Returns:
        0 on success, 1 on error.
    """
    try:
        raw = Path(history_path).read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot read cycle history: {exc}\n")
        return 1

    if not isinstance(data, dict):
        sys.stderr.write("error: cycle history must be a JSON object\n")
        return 1

    cycles = data.get("cycles")
    if not isinstance(cycles, list):
        sys.stderr.write("error: cycle history must contain 'cycles' as a list\n")
        return 1

    summary = _compute_summary(cycles)
    _write_json(output_path, summary)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
