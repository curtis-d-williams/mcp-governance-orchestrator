# SPDX-License-Identifier: MIT
"""Deterministically update the action-effectiveness ledger from governed runs.

This module converts observed run outcomes into per-action learning updates.

Input assumptions:
- governed run artifact contains selected actions and task execution results
- each action type may have expected signal deltas in the existing ledger
- observed task success/failure is used as a conservative learning signal

Behavior:
- increments times_executed for selected action types
- updates success_count / failure_count
- recomputes effectiveness_score deterministically
- preserves existing effect_deltas unless explicitly provided by observations

This is intentionally conservative: it learns from execution reliability first,
not from speculative signal attribution.
"""

import argparse
import json
from pathlib import Path


def _load_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _empty_ledger():
    return {"action_types": []}


def _extract_governed_payload(artifact):
    """Return the governed-run payload from either supported artifact shape."""
    if not isinstance(artifact, dict):
        return {}
    if isinstance(artifact.get("result"), dict):
        return artifact
    cycle_result = artifact.get("cycle_result")
    if isinstance(cycle_result, dict):
        return cycle_result
    return {}


def _index_ledger_rows(ledger):
    rows = ledger.get("action_types", [])
    index = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("action_type"), str):
            index[row["action_type"]] = row
    return index


def _ensure_row(index, action_type):
    row = index.get(action_type)
    if row is None:
        row = {
            "action_type": action_type,
            "times_executed": 0,
            "success_count": 0,
            "failure_count": 0,
            "effectiveness_score": 0.0,
            "effect_deltas": {},
        }
        index[action_type] = row
    row.setdefault("times_executed", 0)
    row.setdefault("success_count", 0)
    row.setdefault("failure_count", 0)
    row.setdefault("effectiveness_score", 0.0)
    row.setdefault("effect_deltas", {})
    return row


def _extract_selected_action_types(governed_artifact):
    governed_artifact = _extract_governed_payload(governed_artifact)
    governed_artifact = _extract_governed_payload(governed_artifact)
    runs = governed_artifact.get("result", {}).get("evaluation_summary", {}).get("runs", [])
    if not runs:
        return []
    detail = runs[0].get("selection_detail", {})
    window = detail.get("ranked_action_window", [])
    selected_tasks = set(runs[0].get("selected_actions", []))
    mapping = detail.get("active_action_to_task_mapping", {})

    selected_action_types = []
    credited_tasks = set()

    for action_type in window:
        task_name = mapping.get(action_type)
        if task_name in selected_tasks and task_name not in credited_tasks:
            selected_action_types.append(action_type)
            credited_tasks.add(task_name)

    return selected_action_types


def _extract_task_outcomes(task_results_artifact):
    outcomes = {}
    if isinstance(task_results_artifact, dict):
        task_name = task_results_artifact.get("task_name")
        summary = task_results_artifact.get("summary", {})
        if task_name:
            outcomes[task_name] = summary.get("repos_failed", 0) == 0
    elif isinstance(task_results_artifact, list):
        for item in task_results_artifact:
            if not isinstance(item, dict):
                continue
            task_name = item.get("task_name")
            summary = item.get("summary", {})
            if task_name:
                outcomes[task_name] = summary.get("repos_failed", 0) == 0
    return outcomes


def _extract_selected_task_outcomes(governed_artifact):
    governed_artifact = _extract_governed_payload(governed_artifact)
    runs = governed_artifact.get("result", {}).get("evaluation_summary", {}).get("runs", [])
    if not runs:
        return {}
    selected_tasks = runs[0].get("selected_actions", [])

    result_block = governed_artifact.get("result", {})
    repos = result_block.get("repos", [])
    succeeded = True
    for repo in repos:
        summary = repo.get("summary", {})
        if summary.get("repos_failed", 0) > 0:
            succeeded = False
            break

    return {task: succeeded for task in selected_tasks}


def _recompute_effectiveness_score(row):
    executed = max(0, int(row.get("times_executed", 0)))
    if executed == 0:
        row["effectiveness_score"] = 0.0
        return
    success = max(0, int(row.get("success_count", 0)))
    failure = max(0, int(row.get("failure_count", 0)))
    # Conservative bounded score in [0, 1].
    row["effectiveness_score"] = round(success / max(1, success + failure), 6)


def update_action_effectiveness_ledger(ledger_path, governed_artifact_path, output_path=None):
    ledger = _load_json(ledger_path, _empty_ledger())
    governed = _load_json(governed_artifact_path, {})

    index = _index_ledger_rows(ledger)
    selected_action_types = _extract_selected_action_types(governed)
    selected_task_outcomes = _extract_selected_task_outcomes(governed)

    governed = _extract_governed_payload(governed)
    runs = governed.get("result", {}).get("evaluation_summary", {}).get("runs", [])
    mapping = runs[0].get("selection_detail", {}).get("active_action_to_task_mapping", {}) if runs else {}

    updates = []
    for action_type in selected_action_types:
        row = _ensure_row(index, action_type)
        task_name = mapping.get(action_type)
        succeeded = selected_task_outcomes.get(task_name, False)

        row["times_executed"] = int(row.get("times_executed", 0)) + 1
        if succeeded:
            row["success_count"] = int(row.get("success_count", 0)) + 1
        else:
            row["failure_count"] = int(row.get("failure_count", 0)) + 1

        _recompute_effectiveness_score(row)

        updates.append({
            "action_type": action_type,
            "task_name": task_name,
            "succeeded": succeeded,
            "times_executed": row["times_executed"],
            "effectiveness_score": row["effectiveness_score"],
        })

    ledger["action_types"] = sorted(index.values(), key=lambda r: r["action_type"])

    output = {
        "updated": True,
        "ledger_path": output_path or ledger_path,
        "selected_action_types": selected_action_types,
        "updates": updates,
        "action_types": ledger["action_types"],
    }

    out = Path(output_path or ledger_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Update action-effectiveness ledger from a governed planner artifact."
    )
    parser.add_argument("--ledger", required=True, metavar="FILE",
                        help="Path to action_effectiveness_ledger.json.")
    parser.add_argument("--governed-artifact", required=True, metavar="FILE",
                        help="Path to governed planner loop artifact JSON.")
    parser.add_argument("--output", default=None, metavar="FILE",
                        help="Optional output path for updated ledger.")
    args = parser.parse_args(argv)

    result = update_action_effectiveness_ledger(
        ledger_path=args.ledger,
        governed_artifact_path=args.governed_artifact,
        output_path=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
