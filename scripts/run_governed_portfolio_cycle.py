# SPDX-License-Identifier: MIT
"""Thin CLI entrypoint: one full governed portfolio cycle.

Executes phases A→B→C→D→E→F→I→J→K→L in sequence using existing scripts as
black-box subprocesses:

  A. Portfolio task phase        — run_portfolio_task.py
  B. Portfolio state phase       — build_portfolio_state_from_artifacts.py
  C. Governed loop phase         — run_governed_planner_loop.py
  D. Governed execution          — execute_governed_actions.py
  E. Execution history           — update_execution_history.py
  F. Action effectiveness        — update_action_effectiveness_from_history.py
  I. Cycle history index         — update_cycle_history.py
  J. Cycle history aggregation   — aggregate_cycle_history.py
  K. Cycle history regression    — detect_cycle_history_regression.py
  L. Governance policy           — enforce_governance_policy.py

Emits a single cycle artifact JSON to --output.

Usage:
    python3 scripts/run_governed_portfolio_cycle.py \\
        --manifest manifests/portfolio_manifest.json \\
        --task artifact_audit_example \\
        --task failure_recovery_example \\
        --output governed_portfolio_cycle.json

Exit codes:
    0  — cycle completed (governed planner executed)
    1  — cycle aborted (any phase failure)
"""

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mcp_governance_orchestrator.governed_cycle import (  # noqa: E402
    artifact_paths as _artifact_paths,
    resolve_planner_ledger as _resolve_planner_ledger_impl,
    run_cycle,
    validate_manifest_repos as _validate_manifest_repos,
    work_dir as _work_dir,
    write_json as _write_json,
)


def _resolve_planner_ledger(args, artifacts):
    """Backward-compatible wrapper: accepts args namespace, delegates to module."""
    return _resolve_planner_ledger_impl(args.ledger, artifacts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run a full governed portfolio cycle.",
        add_help=True,
    )
    parser.add_argument("--manifest", required=True, metavar="FILE",
                        help="Path to portfolio manifest JSON.")
    parser.add_argument("--task", action="append", required=True, metavar="TASK",
                        help="Task name to run (repeatable; at least one required).")
    parser.add_argument("--output", required=True, metavar="FILE",
                        help="Output path for the cycle artifact JSON.")
    parser.add_argument("--ledger", default=None, metavar="FILE",
                        help="Path to action_effectiveness_ledger.json (optional).")
    parser.add_argument("--policy", default=None, metavar="FILE",
                        help="Path to planner_policy.json (optional).")
    parser.add_argument("--top-k", type=int, default=3, metavar="INT",
                        help="Number of top actions to consider (default: 3).")
    parser.add_argument("--exploration-offset", type=int, default=0, metavar="INT",
                        help="Starting exploration offset (default: 0).")
    parser.add_argument("--max-actions", type=int, default=None, metavar="INT",
                        help="Cap selected actions per run (default: no cap).")
    parser.add_argument("--explain", action="store_true", default=False,
                        help="Pass --explain to the governed planner loop.")
    parser.add_argument("--force", action="store_true", default=False,
                        help="Pass --force to the governed planner loop.")
    parser.add_argument("--governance-policy", default=None, metavar="FILE",
                        dest="governance_policy",
                        help="Path to governance_policy.json for Phase L (optional).")

    args = parser.parse_args(argv)
    sys.exit(run_cycle(args))


if __name__ == "__main__":
    main()
