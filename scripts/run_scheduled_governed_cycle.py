# SPDX-License-Identifier: MIT
"""Phase M: scheduled governed cycle runner + operator-facing alert surface.

Thin operational wrapper around scripts/run_governed_portfolio_cycle.py.

Invokes the governed cycle as a subprocess, reads the final cycle artifact,
and produces two operator-facing outputs:
  - An operational summary JSON (--summary-output)
  - An alert artifact JSON (--alert-output)

Designed to be cron-friendly: exits 0 when the wrapper completes its job
(even if the cycle had governance warnings), exits 1 only on wrapper-level
failures (subprocess crash, artifact unreadable).

Usage:
    python3 scripts/run_scheduled_governed_cycle.py \\
        --manifest manifests/portfolio_manifest.json \\
        --task artifact_audit_example \\
        --output governed_portfolio_cycle.json \\
        --summary-output cycle_summary.json \\
        --alert-output cycle_alert.json

Exit codes:
    0  — wrapper completed successfully (inspect alert artifact for issues)
    1  — wrapper failure (subprocess failed or cycle artifact unreadable)
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GOVERNED_CYCLE_SCRIPT = _REPO_ROOT / "scripts" / "run_governed_portfolio_cycle.py"


# ---------------------------------------------------------------------------
# JSON helper
# ---------------------------------------------------------------------------

def _write_json(path, data):
    """Write deterministic JSON (indent=2, sort_keys=True, trailing newline)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Subprocess command builder
# ---------------------------------------------------------------------------

def _build_cycle_cmd(args):
    """Build the subprocess command list for the governed cycle."""
    cmd = [
        sys.executable,
        str(_GOVERNED_CYCLE_SCRIPT),
        "--manifest", args.manifest,
        "--output", args.output,
    ]
    for task in args.task:
        cmd += ["--task", task]
    if args.top_k is not None:
        cmd += ["--top-k", str(args.top_k)]
    if args.force:
        cmd.append("--force")
    if args.governance_policy is not None:
        cmd += ["--governance-policy", args.governance_policy]
    return cmd


# ---------------------------------------------------------------------------
# Pure helpers for summary and alert construction
# ---------------------------------------------------------------------------

def _derive_timestamp(cycle_data):
    """Derive the best available timestamp from the cycle artifact.

    Priority:
      1. cycle_history_regression.current_cycle_timestamp
      2. cycle_history.cycles[-1].timestamp (most recent entry)
      3. None
    """
    regression = cycle_data.get("cycle_history_regression") or {}
    ts = regression.get("current_cycle_timestamp")
    if ts:
        return ts

    history = cycle_data.get("cycle_history") or {}
    cycles = history.get("cycles") or []
    if cycles:
        return cycles[-1].get("timestamp")

    return None


def _get_planner_selected_tasks(cycle_data):
    """Extract the sorted list of selected tasks from execution_result."""
    execution_result = cycle_data.get("execution_result") or {}
    selected = execution_result.get("selected_tasks")
    if isinstance(selected, list):
        return sorted(selected)
    return []


def _classify_alert_level(cycle_status, governance_decision):
    """Return alert level string from cycle status and governance decision.

    Mapping:
      cycle_status != "ok"                        -> "critical"
      governance_decision in ("abort", "warn")    -> "warning"
      otherwise                                   -> "none"

    cycle_status takes precedence when both conditions apply.
    """
    if cycle_status != "ok":
        return "critical"
    if governance_decision in ("abort", "warn"):
        return "warning"
    return "none"


def _build_summary(cycle_output_path, cycle_data):
    """Build the deterministic operational summary dict."""
    status = cycle_data.get("status", "unknown")

    governance_decision_data = cycle_data.get("governance_decision") or {}
    governance_decision = governance_decision_data.get("decision", "unknown")

    regression_data = cycle_data.get("cycle_history_regression") or {}
    regression_detected = bool(regression_data.get("regression_detected", False))

    history = cycle_data.get("cycle_history") or {}
    cycles = history.get("cycles") or []
    cycle_history_length = len(cycles)

    planner_selected_tasks = _get_planner_selected_tasks(cycle_data)
    timestamp = _derive_timestamp(cycle_data)
    alert_level = _classify_alert_level(status, governance_decision)

    return {
        "alert_level": alert_level,
        "cycle_history_length": cycle_history_length,
        "cycle_output": str(cycle_output_path),
        "governance_decision": governance_decision,
        "planner_selected_tasks": planner_selected_tasks,
        "regression_detected": regression_detected,
        "status": status,
        "timestamp": timestamp,
    }


def _build_alert(cycle_status, governance_decision):
    """Build the deterministic alert artifact dict."""
    alert_level = _classify_alert_level(cycle_status, governance_decision)
    alert = alert_level != "none"

    reasons = []
    if cycle_status != "ok":
        reasons.append("cycle_status_aborted")
    if governance_decision == "abort":
        reasons.append("governance_decision_abort")
    elif governance_decision == "warn":
        reasons.append("governance_decision_warn")

    return {
        "alert": alert,
        "alert_level": alert_level,
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Main wrapper
# ---------------------------------------------------------------------------

def run_scheduled_cycle(args):
    """Execute the scheduled governed cycle wrapper.

    Returns:
        0 — wrapper completed (inspect alert artifact for issues)
        1 — wrapper-level failure
    """
    cmd = _build_cycle_cmd(args)

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(
            f"error: governed cycle subprocess failed (rc={exc.returncode})\n"
        )
        _write_json(args.alert_output, {
            "alert": True,
            "alert_level": "critical",
            "reasons": ["wrapper_subprocess_failed"],
        })
        return 1
    except FileNotFoundError as exc:
        sys.stderr.write(f"error: cannot launch governed cycle: {exc}\n")
        _write_json(args.alert_output, {
            "alert": True,
            "alert_level": "critical",
            "reasons": ["wrapper_subprocess_failed"],
        })
        return 1

    # Read the cycle artifact produced by the governed cycle.
    cycle_output_path = Path(args.output)
    try:
        cycle_data = json.loads(cycle_output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(
            f"error: cannot read cycle artifact {args.output}: {exc}\n"
        )
        _write_json(args.alert_output, {
            "alert": True,
            "alert_level": "critical",
            "reasons": ["wrapper_artifact_unreadable"],
        })
        return 1

    cycle_status = cycle_data.get("status", "unknown")
    governance_decision_data = cycle_data.get("governance_decision") or {}
    governance_decision = governance_decision_data.get("decision", "unknown")

    summary = _build_summary(cycle_output_path, cycle_data)
    alert = _build_alert(cycle_status, governance_decision)

    _write_json(args.summary_output, summary)
    _write_json(args.alert_output, alert)

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Phase M: scheduled governed cycle runner + operator alert surface.",
        add_help=True,
    )
    parser.add_argument("--manifest", required=True, metavar="FILE",
                        help="Path to portfolio manifest JSON.")
    parser.add_argument("--output", required=True, metavar="FILE",
                        help="Output path for the cycle artifact JSON.")
    parser.add_argument("--task", action="append", required=True, metavar="TASK",
                        help="Task name to run (repeatable; at least one required).")
    parser.add_argument("--top-k", type=int, default=None, metavar="N",
                        dest="top_k",
                        help="Number of top actions to consider (optional passthrough).")
    parser.add_argument("--force", action="store_true", default=False,
                        help="Pass --force to the governed cycle.")
    parser.add_argument("--governance-policy", default=None, metavar="FILE",
                        dest="governance_policy",
                        help="Path to governance_policy.json for Phase L (optional).")
    parser.add_argument("--summary-output", required=True, metavar="FILE",
                        dest="summary_output",
                        help="Output path for the operational summary JSON.")
    parser.add_argument("--alert-output", required=True, metavar="FILE",
                        dest="alert_output",
                        help="Output path for the alert artifact JSON.")

    args = parser.parse_args(argv)
    sys.exit(run_scheduled_cycle(args))


if __name__ == "__main__":
    main()
