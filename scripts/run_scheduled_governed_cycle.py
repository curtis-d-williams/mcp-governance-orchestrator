# SPDX-License-Identifier: MIT
"""Thin CLI wrapper for Phase M scheduled governed cycle execution."""

import argparse

from portfolio_governance_runtime import (
    _build_alert,
    _build_cycle_cmd,
    _build_summary,
    _classify_alert_level,
    _derive_timestamp,
    _get_planner_selected_tasks,
    run_scheduled_cycle,
)


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
    parser.add_argument("--repo-id", action="append", default=None, metavar="REPO_ID",
                        dest="repo_ids",
                        help="Repo id to include from the manifest (repeatable; default: all repos).")
    parser.add_argument("--top-k", type=int, default=None, metavar="N",
                        dest="top_k",
                        help="Number of top actions to consider (optional passthrough).")
    parser.add_argument("--force", action="store_true", default=False,
                        help="Pass --force to the governed cycle.")
    parser.add_argument("--governance-policy", default=None, metavar="FILE",
                        dest="governance_policy",
                        help="Optional governance policy path passed to the governed cycle.")
    parser.add_argument("--summary-output", required=True, metavar="FILE",
                        help="Output path for the summary JSON.")
    parser.add_argument("--alert-output", required=True, metavar="FILE",
                        help="Output path for the alert JSON.")

    args = parser.parse_args(argv)
    return run_scheduled_cycle(args)


if __name__ == "__main__":
    raise SystemExit(main())
