# SPDX-License-Identifier: MIT
"""Append a normalized record to artifacts/cycle_history.json.

Reads governed_portfolio_cycle.json and appends a deterministic normalized
record to the cycle history index.  Running this script multiple times
against the same cycle artifact at the same logical timestamp is idempotent:
if the normalized record is already present, it is not duplicated.

Usage:
    python3 scripts/update_cycle_history.py \\
        --cycle-artifact governed_portfolio_cycle.json \\
        --output artifacts/cycle_history.json

Exit codes:
    0  — history file written (or unchanged when already up-to-date)
    1  — error (unreadable input, bad JSON, etc.)
"""

import argparse
import datetime
import json
import sys
import csv
from pathlib import Path


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _write_json(path, data):
    """Write *data* as deterministic JSON (indent=2, sort_keys, trailing newline)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _try_read_json(path):
    """Return parsed JSON from *path* if it exists, else None."""
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


# ---------------------------------------------------------------------------
# Timestamp helper (injectable for deterministic tests)
# ---------------------------------------------------------------------------

def _utcnow_iso():
    """Return the current UTC time as an ISO-8601 string with trailing 'Z'."""
    return datetime.datetime.utcnow().isoformat() + "Z"


# ---------------------------------------------------------------------------
# Record normalization
# ---------------------------------------------------------------------------

_RECORD_KEYS = ("ledger_source", "selected_tasks", "status", "timestamp")


def _normalize_record(cycle_artifact, timestamp):
    """Return a deterministic normalized record from *cycle_artifact*.

    Fields:
      - status:         top-level status from the cycle artifact
      - ledger_source:  planner_inputs.ledger_source (or None)
      - selected_tasks: execution_result.selected_tasks (or None)
      - timestamp:      UTC ISO-8601 string passed by the caller

    Args:
        cycle_artifact: parsed cycle artifact dict
        timestamp:      UTC ISO-8601 string

    Returns:
        dict with exactly the keys in _RECORD_KEYS
    """
    planner_inputs = cycle_artifact.get("planner_inputs") or {}
    execution_result = cycle_artifact.get("execution_result") or {}
    return {
        "ledger_source": planner_inputs.get("ledger_source"),
        "selected_tasks": execution_result.get("selected_tasks"),
        "status": cycle_artifact.get("status"),
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# History update
# ---------------------------------------------------------------------------

def update_cycle_history(cycle_artifact_path, output_path, _now_fn=None):
    """Append a normalized record from *cycle_artifact_path* to *output_path*.

    The dedup key is the canonical JSON of the full normalized record
    (including timestamp).  If the record is already present, the file is
    rewritten deterministically but no new entry is added.

    Args:
        cycle_artifact_path: Path to governed_portfolio_cycle.json.
        output_path:         Path to cycle_history.json (created if absent).
        _now_fn:             Optional callable returning a UTC ISO-8601 string.
                             Defaults to _utcnow_iso().  Provided for testing.

    Returns:
        0 on success, 1 on error.
    """
    if _now_fn is None:
        _now_fn = _utcnow_iso

    try:
        cycle_artifact = json.loads(
            Path(cycle_artifact_path).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot read cycle artifact: {exc}\n")
        return 1

    timestamp = _now_fn()
    new_record = _normalize_record(cycle_artifact, timestamp)
    new_canonical = json.dumps(new_record, sort_keys=True)

    # Load existing history or start fresh.
    existing = _try_read_json(output_path)
    if existing is None:
        existing = {"cycles": []}

    existing_cycles = existing.get("cycles", [])
    if not isinstance(existing_cycles, list):
        existing_cycles = []

    # Collect existing canonical strings (dedupe set).
    existing_canonicals = {json.dumps(r, sort_keys=True) for r in existing_cycles}

    if new_canonical in existing_canonicals:
        # Already present — write back sorted but make no new entry.
        all_canonicals = sorted(existing_canonicals)
    else:
        all_canonicals = sorted(existing_canonicals | {new_canonical})

    cycles = [json.loads(c) for c in all_canonicals]
    _write_json(output_path, {"cycles": cycles})
    return 0


def _compute_summary(cycles):
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
        status = cycle.get("status")
        if status is not None:
            status_counts[status] = status_counts.get(status, 0) + 1

        ledger_source = cycle.get("ledger_source")
        if ledger_source is not None:
            ledger_source_counts[ledger_source] = (
                ledger_source_counts.get(ledger_source, 0) + 1
            )

        tasks = cycle.get("selected_tasks") or []
        if tasks:
            cycles_with_tasks += 1
        total_tasks_selected += len(tasks)
        for task in tasks:
            task_selection_counts[task] = task_selection_counts.get(task, 0) + 1

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


def aggregate_cycle_history(history_path, output_path):
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


_CSV_FIELDS = [
    "filename",
    "timestamp",
    "status",
    "phase",
    "selected_actions",
    "selected_actions_count",
    "risk_level",
    "attempts_count",
    "abort_reason",
]


def _extract_timestamp(filename):
    stem = Path(filename).stem
    idx = stem.find("_cycle")
    return stem[:idx] if idx != -1 else stem


def _extract_selected_actions(governed_result):
    if not isinstance(governed_result, dict):
        return []
    sa = governed_result.get("selected_actions")
    if isinstance(sa, list):
        return sa
    result = governed_result.get("result")
    if isinstance(result, dict):
        sa2 = result.get("selected_actions")
        if isinstance(sa2, list):
            return sa2
    return []


def _extract_risk_level(governed_result):
    if not isinstance(governed_result, dict):
        return None
    attempts = governed_result.get("attempts")
    if isinstance(attempts, list) and attempts:
        return attempts[-1].get("risk_level")
    return None


def _summarize_cycle_file(path):
    try:
        cycle = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    filename = Path(path).name
    cycle_dict = cycle if isinstance(cycle, dict) else {}
    governed_result = cycle_dict.get("governed_result")
    if not isinstance(governed_result, dict):
        governed_result = {}

    selected_actions = _extract_selected_actions(governed_result)
    attempts = governed_result.get("attempts")
    attempts_count = len(attempts) if isinstance(attempts, list) else 0

    return {
        "abort_reason": governed_result.get("abort_reason"),
        "attempts_count": attempts_count,
        "filename": filename,
        "phase": cycle_dict.get("phase"),
        "risk_level": _extract_risk_level(governed_result),
        "selected_actions": selected_actions,
        "selected_actions_count": len(selected_actions),
        "status": cycle_dict.get("status"),
        "timestamp": _extract_timestamp(filename),
    }


def summarize_cycle_history(archive_dir):
    d = Path(archive_dir)
    if not d.exists():
        return []
    rows = []
    for p in sorted(d.glob("*_cycle*.json")):
        row = _summarize_cycle_file(p)
        if row is not None:
            rows.append(row)
    return rows


def _write_csv(out, rows):
    def _to_csv_row(r):
        sa = r.get("selected_actions") or []
        return [
            r.get("filename") or "",
            r.get("timestamp") or "",
            r.get("status") or "",
            r.get("phase") or "",
            ";".join(str(s) for s in sa),
            r.get("selected_actions_count", 0),
            r.get("risk_level") or "",
            r.get("attempts_count", 0),
            r.get("abort_reason") or "",
        ]

    if out is None:
        writer = csv.writer(sys.stdout)
        writer.writerow(_CSV_FIELDS)
        for r in rows:
            writer.writerow(_to_csv_row(r))
    else:
        with open(str(out), "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(_CSV_FIELDS)
            for r in rows:
                writer.writerow(_to_csv_row(r))


_STATUS_RANK = {"ok": 1, "aborted": 0}
_UNKNOWN_STATUS_RANK = 0


def _status_rank(status):
    return _STATUS_RANK.get(status, _UNKNOWN_STATUS_RANK)


def _sorted_tasks(tasks):
    return sorted(tasks) if tasks else []


def _detect_signals(prev, curr):
    signals = []

    prev_task_set = set(_sorted_tasks(prev.get("selected_tasks")))
    curr_task_set = set(_sorted_tasks(curr.get("selected_tasks")))
    if prev_task_set != curr_task_set:
        signals.append({
            "type": "action_set_changed",
            "current_selected_tasks": sorted(curr_task_set),
            "previous_selected_tasks": sorted(prev_task_set),
        })

    prev_status = prev.get("status")
    curr_status = curr.get("status")
    if _status_rank(curr_status) < _status_rank(prev_status):
        signals.append({
            "type": "status_regressed",
            "current_status": curr_status,
            "previous_status": prev_status,
        })

    return sorted(signals, key=lambda s: s["type"])


def _extract_summary_context(summary):
    return {
        "cycles_total": summary.get("cycles_total"),
        "success_rate": summary.get("success_rate"),
        "unique_tasks_selected": summary.get("unique_tasks_selected"),
    }


def detect_cycle_history_regression(history_path, summary_path, output_path):
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
    sorted_cycles = sorted(cycles, key=lambda c: c.get("timestamp") or "")

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
