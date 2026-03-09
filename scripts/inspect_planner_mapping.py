# SPDX-License-Identifier: MIT
"""Planner mapping diagnostic CLI (v0.1).

Inspects the planner's ranked action window and shows how actions collapse
into task clusters, helping operators understand why diversity collapse occurs.

Reuses _compute_risk and _fetch_actions from analyze_planner_collision_risk.py
so the ranked window exactly matches the planner.

Usage:
    python3 scripts/inspect_planner_mapping.py \\
        --policy neutral \\
        --top-k 3 \\
        --portfolio-state experiments/portfolio_state_degraded_v2.json \\
        --ledger experiments/action_effectiveness_ledger_synthetic_v2.json

Optional:
    --mapping-override PATH    JSON file overriding the action→task mapping.
    --exploration-offset INT   Start index into the action queue window (default: 0).
    --output PATH              Write diagnostic JSON to this path (default: stdout only).
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path for `from scripts.*` imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.planner_scoring import (
    load_effectiveness_ledger,
    load_planner_policy,
    load_portfolio_signals,
)
from scripts.claude_dynamic_planner_loop import ACTION_TO_TASK, resolve_action_to_task_mapping

# ---------------------------------------------------------------------------
# Load _compute_risk and _fetch_actions from the analyzer (no duplication)
# ---------------------------------------------------------------------------

_ANALYZER_SCRIPT = Path(__file__).resolve().parent / "analyze_planner_collision_risk.py"
_analyzer_spec = importlib.util.spec_from_file_location(
    "analyze_planner_collision_risk", _ANALYZER_SCRIPT
)
_analyzer_mod = importlib.util.module_from_spec(_analyzer_spec)
_analyzer_spec.loader.exec_module(_analyzer_mod)

_compute_risk = _analyzer_mod._compute_risk
_fetch_actions = _analyzer_mod._fetch_actions


# ---------------------------------------------------------------------------
# Cluster builder — pure, deterministic, no I/O
# ---------------------------------------------------------------------------

def _build_clusters(ranked_action_window, mapped_tasks):
    """Build task clusters from parallel window/mapping lists.

    Groups each action by its mapped task, preserving window order within
    each cluster.  Unmapped actions (task=None) are collected under the
    key "unmapped"; that key is omitted when there are no unmapped actions.

    Cluster keys are sorted for deterministic JSON output.

    Args:
        ranked_action_window: list of action_type strings in window order.
        mapped_tasks:         parallel list of task strings (or None).

    Returns:
        dict with keys:
            task_clusters      {task_name: [action_types]}  (sorted keys)
            cluster_count      int — number of distinct keys in task_clusters
            largest_cluster_size int — max actions in any single cluster (0 if empty)
            collision_count    int — actions beyond the first in each cluster
                               == sum(max(0, len(v)-1) for v in clusters)
                               == window_size - cluster_count
    """
    raw: dict = {}
    for at, task in zip(ranked_action_window, mapped_tasks):
        key = task if task is not None else "unmapped"
        raw.setdefault(key, []).append(at)

    # Sort cluster keys; preserve insertion (window) order within each cluster.
    task_clusters = {k: list(raw[k]) for k in sorted(raw)}

    cluster_count = len(task_clusters)
    largest_cluster_size = max((len(v) for v in task_clusters.values()), default=0)
    collision_count = sum(max(0, len(v) - 1) for v in task_clusters.values())

    return {
        "task_clusters": task_clusters,
        "cluster_count": cluster_count,
        "largest_cluster_size": largest_cluster_size,
        "collision_count": collision_count,
    }


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def inspect_mapping(policy_path, top_k, portfolio_state_path, ledger_path,
                    mapping_override_path=None, output_path=None,
                    exploration_offset=0):
    """Run the mapping diagnostic and produce a cluster report.

    Args:
        policy_path:           Path to planner_policy.json (or None / nonexistent).
        top_k:                 Window size.
        portfolio_state_path:  Path to portfolio_state.json.
        ledger_path:           Path to action_effectiveness_ledger.json (or None).
        mapping_override_path: Path to mapping-override JSON file (or None).
        output_path:           If set, write JSON here; otherwise print to stdout.
        exploration_offset:    Start index into ranked action list (default: 0).

    Returns:
        The diagnostic dict.
    """
    ledger = load_effectiveness_ledger(ledger_path)
    signals = load_portfolio_signals(portfolio_state_path)
    policy = load_planner_policy(policy_path)

    mapping_override = None
    if mapping_override_path is not None:
        p = Path(mapping_override_path)
        if p.exists():
            try:
                mapping_override = json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"Warning: could not load mapping override: {exc}", file=sys.stderr)

    active_mapping = resolve_action_to_task_mapping(ACTION_TO_TASK, mapping_override)
    raw_actions = _fetch_actions(portfolio_state_path, ledger_path)

    risk = _compute_risk(
        raw_actions, top_k, ledger, signals, policy, active_mapping, exploration_offset,
    )

    clusters = _build_clusters(
        risk["ranked_action_window"],
        risk["mapped_tasks"],
    )

    result = {
        "policy": policy_path,
        "top_k": top_k,
        "window_actions": risk["ranked_action_window"],
        "mapped_tasks": risk["mapped_tasks"],
        **clusters,
    }

    serialized = json.dumps(result, indent=2) + "\n"

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized, encoding="utf-8")
        print(f"Wrote {out}", file=sys.stderr)
    else:
        print(serialized, end="")

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Inspect how planner actions collapse into task clusters.",
        add_help=True,
    )
    parser.add_argument(
        "--policy", default=None, metavar="FILE",
        help="Path to planner_policy.json for governance signal weights (optional).",
    )
    parser.add_argument(
        "--top-k", type=int, default=3, metavar="INT",
        help="Number of top actions to consider (default: 3).",
    )
    parser.add_argument(
        "--portfolio-state", required=True, metavar="FILE",
        help="Path to portfolio_state.json.",
    )
    parser.add_argument(
        "--ledger", default=None, metavar="FILE",
        help="Path to action_effectiveness_ledger.json (optional).",
    )
    parser.add_argument(
        "--mapping-override", default=None, metavar="FILE",
        help="Path to JSON file overriding the action→task mapping (optional).",
    )
    parser.add_argument(
        "--exploration-offset", type=int, default=0, metavar="INT",
        help="Start index into the action queue window (default: 0).",
    )
    parser.add_argument(
        "--output", default=None, metavar="FILE",
        help="Write diagnostic JSON to this path. Omit to print to stdout only.",
    )
    args = parser.parse_args(argv)

    inspect_mapping(
        policy_path=args.policy,
        top_k=args.top_k,
        portfolio_state_path=args.portfolio_state,
        ledger_path=args.ledger,
        mapping_override_path=args.mapping_override,
        output_path=args.output,
        exploration_offset=args.exploration_offset,
    )


if __name__ == "__main__":
    main()
