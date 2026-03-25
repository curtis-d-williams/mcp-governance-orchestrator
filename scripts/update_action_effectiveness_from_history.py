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
# Constants
# ---------------------------------------------------------------------------

_EFFECTIVENESS_WEIGHT = 0.15  # mirrors EFFECTIVENESS_WEIGHT in planner_runtime.py


# ---------------------------------------------------------------------------
# Mapping-aware helpers
# ---------------------------------------------------------------------------

def _classify(score):
    """Map effectiveness score to a classification string."""
    if score >= 0.75:
        return "high"
    if score >= 0.50:
        return "medium"
    return "low"


def _derive_action_types(actions, mapping):
    """Derive an action_types list by inverting mapping into task history.

    mapping: {action_type: task_name} dict (e.g. ACTION_TO_TASK from the planner).

    For each action_type in the mapping, looks up its task's history in actions.
    Multiple action_types that share a task receive the same effectiveness data.
    Action_types whose task has no history in actions are omitted.
    Sorted by action_type for determinism.

    Returns a list of action_type row dicts suitable for load_effectiveness_ledger
    and list_portfolio_actions._build_ledger_index.
    """
    result = []
    for action_type in sorted(mapping):
        task_name = mapping[action_type]
        row = actions.get(task_name)
        if not isinstance(row, dict):
            continue
        total = row.get("total_runs", 0)
        success = row.get("success_count", 0)
        try:
            total_f, success_f = float(total), float(success)
        except (TypeError, ValueError):
            continue
        if total_f <= 0:
            continue
        score = max(0.0, min(1.0, success_f / total_f))
        result.append({
            "action_type": action_type,
            "classification": _classify(score),
            "effectiveness_score": round(score, 4),
            "recommended_priority_adjustment": round(score * _EFFECTIVENESS_WEIGHT, 4),
            "times_executed": int(total_f),
        })
    return result


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

def update_action_effectiveness_from_history(execution_history_path, output_path,
                                              mapping=None):
    """Aggregate execution history into an action effectiveness ledger.

    Args:
        execution_history_path: Path to execution_history.json.
        output_path:            Destination for action_effectiveness_ledger.json.
        mapping:                Optional {action_type: task_name} dict.  When
                                provided, an "action_types" array is derived and
                                written alongside "actions", satisfying the format
                                expected by list_portfolio_actions and
                                load_effectiveness_ledger.  When absent, only the
                                task-keyed "actions" dict is written (prior
                                behaviour).

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
    output = {"actions": actions}
    if mapping:
        output["action_types"] = _derive_action_types(actions, mapping)
    _write_json(output_path, output)
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
    parser.add_argument("--mapping-json", default=None, metavar="JSON",
                        help="JSON object mapping action_type to task_name.  When "
                             "provided, an 'action_types' array is derived and "
                             "written alongside 'actions'.")

    args = parser.parse_args(argv)

    mapping = None
    if args.mapping_json is not None:
        try:
            mapping = json.loads(args.mapping_json)
        except json.JSONDecodeError as exc:
            sys.stderr.write(f"error: --mapping-json is not valid JSON: {exc}\n")
            sys.exit(1)

    sys.exit(update_action_effectiveness_from_history(
        args.execution_history, args.output, mapping=mapping
    ))


if __name__ == "__main__":
    main()
