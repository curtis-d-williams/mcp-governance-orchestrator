# SPDX-License-Identifier: MIT
"""Planner diversity sweep experiment (v0.1).

Measures how task diversity changes as the ranked window size (top_k) increases
from 1 to max_k.  For each top_k, captures collision_ratio, task_entropy,
action_entropy, unique_tasks, and entropy_gap.

Reuses _compute_risk and _fetch_actions from analyze_planner_collision_risk.py
so the ranked window exactly matches the planner at every top_k.

Usage:
    python3 scripts/run_diversity_sweep.py \\
        --portfolio-state experiments/portfolio_state_degraded_v2.json \\
        --ledger experiments/action_effectiveness_ledger_synthetic_v2.json

Optional:
    --policy FILE              Path to planner_policy.json.
    --max-k INT                Maximum window size to sweep (default: 8).
    --mapping-override FILE    JSON file overriding the action→task mapping.
    --exploration-offset INT   Start index into the action queue (default: 0).
    --output FILE              Write sweep JSON to this path (default: stdout only).
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
# Pure sweep computation (testable without subprocess)
# ---------------------------------------------------------------------------

def _sweep_one(actions, top_k, ledger, signals, policy, active_mapping,
               exploration_offset=0):
    """Compute diversity metrics for a single top_k value.

    Args:
        actions:           Pre-fetched action list.
        top_k:             Window size for this sweep step.
        ledger:            Effectiveness ledger dict.
        signals:           Portfolio signal averages dict.
        policy:            Planner policy weight dict.
        active_mapping:    Active action→task mapping dict.
        exploration_offset: Start index into the ranked list.

    Returns:
        dict with keys: top_k, unique_tasks, collision_ratio,
        task_entropy, action_entropy, entropy_gap.
    """
    risk = _compute_risk(actions, top_k, ledger, signals, policy, active_mapping,
                         exploration_offset)
    entropy_gap = round(risk["action_entropy"] - risk["task_entropy"], 6)
    return {
        "top_k": top_k,
        "unique_tasks": risk["unique_tasks"],
        "collision_ratio": risk["collision_ratio"],
        "task_entropy": risk["task_entropy"],
        "action_entropy": risk["action_entropy"],
        "entropy_gap": entropy_gap,
    }


def compute_diversity_sweep(actions, max_k, ledger, signals, policy, active_mapping,
                             exploration_offset=0):
    """Compute diversity metrics for top_k = 1 .. max_k (deterministic).

    Args:
        actions:           Pre-fetched action list.
        max_k:             Upper bound of the sweep (inclusive).
        ledger:            Effectiveness ledger dict.
        signals:           Portfolio signal averages dict.
        policy:            Planner policy weight dict.
        active_mapping:    Active action→task mapping dict.
        exploration_offset: Start index into the ranked list.

    Returns:
        List of dicts, one per top_k value, in ascending top_k order.
    """
    return [
        _sweep_one(actions, k, ledger, signals, policy, active_mapping, exploration_offset)
        for k in range(1, max_k + 1)
    ]


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def run_diversity_sweep(policy_path, portfolio_state_path, ledger_path, max_k=8,
                        mapping_override_path=None, output_path=None,
                        exploration_offset=0):
    """Run the diversity sweep and produce a sweep report.

    Args:
        policy_path:           Path to planner_policy.json (or None / nonexistent).
        portfolio_state_path:  Path to portfolio_state.json.
        ledger_path:           Path to action_effectiveness_ledger.json (or None).
        max_k:                 Maximum window size to sweep (default: 8).
        mapping_override_path: Path to mapping-override JSON file (or None).
        output_path:           If set, write sweep JSON here; otherwise stdout only.
        exploration_offset:    Start index into ranked action list (default: 0).

    Returns:
        List of per-top_k metric dicts.
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

    # Fetch actions once; reuse across all top_k values.
    raw_actions = _fetch_actions(portfolio_state_path, ledger_path)

    if not raw_actions:
        if not Path(portfolio_state_path).exists():
            print(
                f"Error: portfolio-state file not found: {portfolio_state_path}",
                file=sys.stderr,
            )
        else:
            print(
                f"Error: action queue is empty for '{portfolio_state_path}' — no actions to sweep. "
                "Verify the portfolio state contains eligible actions.",
                file=sys.stderr,
            )
        sys.exit(1)

    sweep = compute_diversity_sweep(
        raw_actions, max_k, ledger, signals, policy, active_mapping, exploration_offset,
    )

    serialized = json.dumps(sweep, indent=2) + "\n"

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized, encoding="utf-8")
        print(f"Wrote {out}", file=sys.stderr)
    else:
        print(serialized, end="")

    return sweep


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Sweep top_k from 1 to max_k and measure planner task diversity.",
        add_help=True,
    )
    parser.add_argument(
        "--policy", default=None, metavar="FILE",
        help="Path to planner_policy.json (optional).",
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
        "--max-k", type=int, default=8, metavar="INT",
        help="Maximum window size to sweep (default: 8).",
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
        help="Write sweep JSON to this path. Omit to print to stdout only.",
    )
    args = parser.parse_args(argv)

    run_diversity_sweep(
        policy_path=args.policy,
        portfolio_state_path=args.portfolio_state,
        ledger_path=args.ledger,
        max_k=args.max_k,
        mapping_override_path=args.mapping_override,
        output_path=args.output,
        exploration_offset=args.exploration_offset,
    )


if __name__ == "__main__":
    main()
