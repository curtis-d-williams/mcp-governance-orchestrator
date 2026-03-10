# SPDX-License-Identifier: MIT
"""Thin helper: execute governed actions selected by the planner loop.

Reads a governed result JSON, extracts selected task(s), executes them
via run_portfolio_task.py, and writes a deterministic execution result JSON.

Usage:
    python3 scripts/execute_governed_actions.py \\
        --governed-result governed_result.json \\
        --manifest manifests/portfolio_manifest.json \\
        --output execution_result.json

Exit codes:
    0  — execution succeeded (task(s) ran, returncode 0)
    1  — aborted (no tasks resolved) or task execution failed (returncode != 0)
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.claude_dynamic_planner_loop import ACTION_TO_TASK


# ---------------------------------------------------------------------------
# JSON output helper
# ---------------------------------------------------------------------------

def _write_json(path, data):
    """Write *data* as deterministic JSON (indent=2, sort_keys, trailing newline)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Task extraction
# ---------------------------------------------------------------------------

def _extract_selected_tasks(governed_result):
    """Extract selected tasks from a governed result dict.

    Primary source:
        governed_result["result"]["evaluation_summary"]["runs"][0]["selected_actions"]

    Fallback source:
        ...["selection_detail"]["ranked_action_window"]  — action type strings
        resolved via ACTION_TO_TASK.

    Returns:
        (tasks, resolved_via) where resolved_via is "selected_actions" or
        "action_mapping_fallback".  Returns ([], None) when nothing resolves.
    """
    # Primary: selected_actions
    try:
        runs = governed_result["result"]["evaluation_summary"]["runs"]
        if runs:
            selected = runs[0].get("selected_actions", [])
            if selected:
                return list(selected), "selected_actions"
    except (KeyError, TypeError, IndexError):
        pass

    # Fallback: first resolvable action in ranked_action_window
    try:
        runs = governed_result["result"]["evaluation_summary"]["runs"]
        if runs:
            window = runs[0].get("selection_detail", {}).get("ranked_action_window", [])
            for action in window:
                task = ACTION_TO_TASK.get(action)
                if task:
                    return [task], "action_mapping_fallback"
    except (KeyError, TypeError, IndexError):
        pass

    return [], None


# ---------------------------------------------------------------------------
# Main executor
# ---------------------------------------------------------------------------

def execute_governed_actions(governed_result_path, manifest, output_path):
    """Execute the tasks selected by the governed planner loop.

    Args:
        governed_result_path: Path to governed_result.json.
        manifest:             Path to portfolio manifest JSON.
        output_path:          Destination for the execution result JSON.

    Returns:
        0 on success (task(s) ran, returncode 0).
        1 on abort or task failure.
    """
    # Read governed result.
    try:
        governed_result = json.loads(
            Path(governed_result_path).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        _write_json(output_path, {
            "status": "aborted",
            "reason": "governed_result_unreadable",
            "error": str(exc),
        })
        return 1

    selected_tasks, resolved_via = _extract_selected_tasks(governed_result)

    if not selected_tasks:
        _write_json(output_path, {
            "status": "aborted",
            "reason": "no_selected_tasks",
            "resolved_via": None,
            "selected_tasks": [],
        })
        return 1

    # Execute via run_portfolio_task.py.
    script = str(_REPO_ROOT / "scripts" / "run_portfolio_task.py")
    cmd = ["python3", script] + selected_tasks + [str(manifest)]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    # Try to parse stdout as JSON.
    parsed_output = None
    try:
        parsed_output = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        pass

    status = "ok" if proc.returncode == 0 else "aborted"
    _write_json(output_path, {
        "parsed_output": parsed_output,
        "resolved_via": resolved_via,
        "returncode": proc.returncode,
        "selected_tasks": selected_tasks,
        "status": status,
        "stderr": proc.stderr,
        "stdout": proc.stdout,
    })
    return 0 if proc.returncode == 0 else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Execute governed actions selected by the planner loop.",
        add_help=True,
    )
    parser.add_argument("--governed-result", required=True, metavar="FILE",
                        help="Path to governed_result.json.")
    parser.add_argument("--manifest", required=True, metavar="FILE",
                        help="Path to portfolio manifest JSON.")
    parser.add_argument("--output", required=True, metavar="FILE",
                        help="Output path for the execution result JSON.")

    args = parser.parse_args(argv)
    sys.exit(execute_governed_actions(args.governed_result, args.manifest, args.output))


if __name__ == "__main__":
    main()
