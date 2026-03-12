# SPDX-License-Identifier: MIT
"""Operator-facing planner evaluation CLI (v0.1).

Wraps the collision-risk analyzer with a deterministic risk classification
rubric, producing a human-readable assessment of planner safety and diversity
quality before execution.

Reuses _compute_risk and _fetch_actions from analyze_planner_collision_risk.py
so planner simulation logic is not duplicated.

Usage:
    python3 scripts/evaluate_planner_config.py \\
        --policy neutral \\
        --top-k 3 \\
        --portfolio-state experiments/portfolio_state_degraded_v2.json \\
        --ledger experiments/action_effectiveness_ledger_synthetic_v2.json

Optional:
    --mapping-override PATH    JSON file overriding the action→task mapping.
    --exploration-offset INT   Start index into the action queue window (default: 0).
    --output PATH              Write evaluation JSON to this path (default: stdout only).
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path for `from scripts.*` imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.claude_dynamic_planner_loop import (
    ACTION_TO_TASK,
    resolve_action_to_task_mapping,
)

from planner_runtime import (
    build_planner_evaluation,
    classify_risk,
    compute_expected_success_signal,
    compute_planner_collision_risk,
    fetch_planner_actions,
    load_capability_effectiveness_ledger,
    load_effectiveness_ledger,
    load_mapping_override,
    load_planner_policy,
    load_portfolio_signals,
)


# ---------------------------------------------------------------------------
# Pure evaluation builder (testable without subprocess)
# ---------------------------------------------------------------------------

_classify_risk = classify_risk
_compute_risk = compute_planner_collision_risk
_fetch_actions = fetch_planner_actions
build_evaluation = build_planner_evaluation


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def evaluate_planner_config(policy_path, top_k, portfolio_state_path, ledger_path,
                             mapping_override_path=None, output_path=None,
                             exploration_offset=0, capability_ledger_path=None):
    """Run collision-risk analysis and produce an operator evaluation."""
    ledger = load_effectiveness_ledger(ledger_path)
    capability_ledger = load_capability_effectiveness_ledger(capability_ledger_path)
    signals = load_portfolio_signals(portfolio_state_path)
    policy = load_planner_policy(policy_path)
    mapping_override = load_mapping_override(mapping_override_path)
    active_mapping = resolve_action_to_task_mapping(ACTION_TO_TASK, mapping_override)

    raw_actions = _fetch_actions(portfolio_state_path, ledger_path)
    metrics = _compute_risk(
        raw_actions,
        top_k,
        ledger,
        signals,
        policy,
        active_mapping,
        exploration_offset=exploration_offset,
        mapping_override=mapping_override,
        capability_ledger=capability_ledger,
    )

    expected_success_rate, historical_runs = compute_expected_success_signal(
        metrics.get("mapped_tasks", []),
        ledger,
    )

    evaluation = build_evaluation(
        metrics,
        top_k,
        expected_success_rate=expected_success_rate,
        historical_runs=historical_runs,
    )
    evaluation["policy"] = policy_path
    evaluation["top_k"] = top_k

    serialized = json.dumps(evaluation, indent=2) + "\n"

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized, encoding="utf-8")
        print(f"Wrote {out}", file=sys.stderr)
    else:
        print(serialized, end="")

    return evaluation


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Evaluate planner config for diversity quality and collision risk.",
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
        "--capability-ledger", default=None, metavar="FILE",
        help="Path to capability_effectiveness_ledger.json (optional).",
    )
    parser.add_argument(
        "--exploration-offset", type=int, default=0, metavar="INT",
        help="Start index into the action queue window (default: 0).",
    )
    parser.add_argument(
        "--output", default=None, metavar="FILE",
        help="Write evaluation JSON to this path. Omit to print to stdout only.",
    )
    args = parser.parse_args(argv)

    evaluate_planner_config(
        policy_path=args.policy,
        top_k=args.top_k,
        portfolio_state_path=args.portfolio_state,
        ledger_path=args.ledger,
        mapping_override_path=args.mapping_override,
        output_path=args.output,
        exploration_offset=args.exploration_offset,
        capability_ledger_path=args.capability_ledger,
    )


if __name__ == "__main__":
    main()
