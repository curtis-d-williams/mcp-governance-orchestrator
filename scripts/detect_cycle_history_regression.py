# SPDX-License-Identifier: MIT
"""Phase K: detect regressions in governed cycle history.

Reads cycle_history.json (Phase I output) and a cycle history summary
(Phase J output) and produces a deterministic regression report.

Detection signals emitted:

  action_set_changed — the set of tasks selected in the most recent cycle
                       differs from the set selected in the immediately
                       preceding cycle.

  status_regressed   — the most recent cycle status is worse than the
                       preceding cycle status (ok is better than aborted).

The detector is read-only; it never modifies history or summary files.

Usage:
    python3 scripts/detect_cycle_history_regression.py \\
        --history  artifacts/cycle_history.json \\
        --summary  artifacts/cycle_history_summary.json \\
        --output   artifacts/cycle_history_regression.json

Exit codes:
    0  — report written (includes no-regression and insufficient-history cases)
    1  — error (unreadable input, bad JSON, invalid schema)
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
# Status ranking (higher is better)
# ---------------------------------------------------------------------------

_STATUS_RANK = {"ok": 1, "aborted": 0}
_UNKNOWN_STATUS_RANK = 0  # unknown statuses treated as worst (fail-closed)


def _status_rank(status):
    """Return the numeric rank for *status* (higher = better)."""
    return _STATUS_RANK.get(status, _UNKNOWN_STATUS_RANK)


# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------

def _sorted_tasks(tasks):
    """Return a deterministic sorted list from *tasks*; None or empty → []."""
    return sorted(tasks) if tasks else []


def _detect_signals(prev, curr):
    """Return a deterministic list of regression signals.

    Signals are ordered alphabetically by type for stable output.

    Args:
        prev: previous cycle record dict (second-most-recent by timestamp)
        curr: current cycle record dict (most-recent by timestamp)

    Returns:
        list of signal dicts, sorted by "type" for determinism.
    """
    signals = []

    # A. action_set_changed
    prev_task_set = set(_sorted_tasks(prev.get("selected_tasks")))
    curr_task_set = set(_sorted_tasks(curr.get("selected_tasks")))
    if prev_task_set != curr_task_set:
        signals.append({
            "type": "action_set_changed",
            "current_selected_tasks": sorted(curr_task_set),
            "previous_selected_tasks": sorted(prev_task_set),
        })

    # B. status_regressed
    prev_status = prev.get("status")
    curr_status = curr.get("status")
    if _status_rank(curr_status) < _status_rank(prev_status):
        signals.append({
            "type": "status_regressed",
            "current_status": curr_status,
            "previous_status": prev_status,
        })

    # Alphabetical sort by type for deterministic ordering.
    return sorted(signals, key=lambda s: s["type"])


# ---------------------------------------------------------------------------
# Summary context extraction
# ---------------------------------------------------------------------------

def _extract_summary_context(summary):
    """Return the relevant summary context from the Phase J summary dict."""
    return {
        "cycles_total": summary.get("cycles_total"),
        "success_rate": summary.get("success_rate"),
        "unique_tasks_selected": summary.get("unique_tasks_selected"),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def detect_cycle_history_regression(history_path, summary_path, output_path):
    """Detect regressions in cycle history and write a report.

    Args:
        history_path: Path to cycle_history.json (Phase I output).
        summary_path: Path to cycle_history_summary.json (Phase J output).
        output_path:  Destination for the regression report JSON.

    Returns:
        0 on success, 1 on error.
    """
    # --- Read history ---
    try:
        history_data = json.loads(
            Path(history_path).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot read cycle history: {exc}\n")
        return 1

    if not isinstance(history_data, dict):
        sys.stderr.write("error: cycle history must be a JSON object\n")
        return 1

    cycles = history_data.get("cycles")
    if not isinstance(cycles, list):
        sys.stderr.write("error: cycle history must contain 'cycles' as a list\n")
        return 1

    # --- Read summary ---
    try:
        summary_data = json.loads(
            Path(summary_path).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot read cycle history summary: {exc}\n")
        return 1

    if not isinstance(summary_data, dict):
        sys.stderr.write("error: cycle history summary must be a JSON object\n")
        return 1

    summary_context = _extract_summary_context(summary_data)

    # Sort cycles by timestamp for deterministic current/previous selection.
    # Cycles with None/missing timestamps sort to the front (empty string).
    sorted_cycles = sorted(cycles, key=lambda c: c.get("timestamp") or "")

    # --- Insufficient history ---
    if len(sorted_cycles) < 2:
        current_ts = sorted_cycles[-1].get("timestamp") if sorted_cycles else None
        report = {
            "current_cycle_timestamp": current_ts,
            "insufficient_history": True,
            "regression_detected": False,
            "signals": [],
            "summary_context": summary_context,
        }
        _write_json(output_path, report)
        return 0

    current = sorted_cycles[-1]
    previous = sorted_cycles[-2]

    signals = _detect_signals(previous, current)

    report = {
        "current_cycle_timestamp": current.get("timestamp"),
        "insufficient_history": False,
        "regression_detected": len(signals) > 0,
        "signals": signals,
        "summary_context": summary_context,
    }
    _write_json(output_path, report)
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
