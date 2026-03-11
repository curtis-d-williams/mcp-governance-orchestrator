# SPDX-License-Identifier: MIT
"""Planner collision-risk analyzer (v0.1).

Predicts planner diversity collapse before execution by simulating the
ranked action window and applying the active action→task mapping.

Usage:
    python3 scripts/analyze_planner_collision_risk.py \\
        --policy neutral \\
        --top-k 3 \\
        --portfolio-state experiments/portfolio_state_degraded_v2.json \\
        --ledger experiments/action_effectiveness_ledger_synthetic_v2.json

Optional:
    --mapping-override PATH    JSON file overriding the action→task mapping.
    --exploration-offset INT   Start index into the action queue window (default: 0).
    --output PATH              Output path (default: planner_risk_summary.json).

Output:
    planner_risk_summary.json
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path for `from scripts.*` imports,
# whether invoked directly or via importlib from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from planner_runtime import (
    compute_planner_collision_risk,
    entropy_from_counts,
    fetch_planner_actions,
    load_effectiveness_ledger,
    load_mapping_override,
    load_planner_policy,
    load_portfolio_signals,
)
from scripts.claude_dynamic_planner_loop import (
    ACTION_TO_TASK,
    resolve_action_to_task_mapping,
    resolve_task_for_action,
)

OUTPUT_FILE = Path("planner_risk_summary.json")

# Backward-compatible private aliases for existing tests/importers.
_entropy = entropy_from_counts
_fetch_actions = fetch_planner_actions
_compute_risk = compute_planner_collision_risk


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def analyze_collision_risk(policy_path, top_k, portfolio_state_path, ledger_path,
                            mapping_override_path=None, output_path=None,
                            exploration_offset=0):
    """Run collision-risk analysis and write the summary JSON."""
    ledger = load_effectiveness_ledger(ledger_path)
    signals = load_portfolio_signals(portfolio_state_path)
    policy = load_planner_policy(policy_path)
    mapping_override = load_mapping_override(mapping_override_path)
    active_mapping = resolve_action_to_task_mapping(ACTION_TO_TASK, mapping_override)

    raw_actions = _fetch_actions(portfolio_state_path, ledger_path)
    risk = _compute_risk(
        raw_actions,
        top_k,
        ledger,
        signals,
        policy,
        active_mapping,
        exploration_offset=exploration_offset,
        mapping_override=mapping_override,
    )

    summary = {
        "policy": policy_path,
        "top_k": top_k,
        **risk,
    }

    out = Path(output_path) if output_path else OUTPUT_FILE
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")

    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Predict planner diversity collapse before execution.",
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
        help="Start index into the action queue window (default: 0, clamped to valid range).",
    )
    parser.add_argument(
        "--output", default=None, metavar="FILE",
        help=f"Output path for risk summary JSON (default: {OUTPUT_FILE}).",
    )
    args = parser.parse_args(argv)

    analyze_collision_risk(
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
