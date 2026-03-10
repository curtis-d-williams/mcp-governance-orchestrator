# SPDX-License-Identifier: MIT
"""Mapping repair proposal generator (v0.1).

Simulates the ranked planner action window and proposes a deterministic
mapping override when multiple actions collapse to the same task target,
reducing task diversity.

This is a proposal generator only — it does not modify any existing mapping
or execute any planner run.

Usage:
    python3 scripts/propose_mapping_repair.py \\
        --portfolio-state experiments/portfolio_state_degraded_v2.json \\
        --ledger experiments/action_effectiveness_ledger_synthetic_v2.json

Optional:
    --policy FILE               Path to planner_policy.json.
    --top-k INT                 Window size (default: 3).
    --exploration-offset INT    Start index into ranked list (default: 0).
    --output FILE               Write proposal JSON here (default: stdout).

Output shape:
    {
      "ranked_action_window": [...],
      "current_mapped_tasks": [...],
      "proposed_mapping_override": {...},
      "repair_needed": true/false,
      "reasons": [...]
    }
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

# Ensure repo root on sys.path for `from scripts.*` imports.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.planner_scoring import (
    load_effectiveness_ledger,
    load_planner_policy,
    load_portfolio_signals,
)
from scripts.claude_dynamic_planner_loop import (
    ACTION_TO_TASK,
    ALL_TASKS,
    resolve_action_to_task_mapping,
)

# Load _compute_risk and _fetch_actions from the analyzer (no duplication).
_ANALYZER_SCRIPT = Path(__file__).resolve().parent / "analyze_planner_collision_risk.py"
_analyzer_spec = importlib.util.spec_from_file_location(
    "analyze_planner_collision_risk", _ANALYZER_SCRIPT
)
_analyzer_mod = importlib.util.module_from_spec(_analyzer_spec)
_analyzer_spec.loader.exec_module(_analyzer_mod)

_compute_risk = _analyzer_mod._compute_risk
_fetch_actions = _analyzer_mod._fetch_actions


# ---------------------------------------------------------------------------
# Repair proposal builder — pure, deterministic, no I/O
# ---------------------------------------------------------------------------

def _propose_repair(ranked_action_window, current_mapped_tasks, active_mapping):
    """Build a diversified mapping override for colliding actions.

    Heuristic (deterministic):
      1. Walk the ranked window in order.
      2. Track which tasks have already been assigned in this window.
      3. For each action:
         a. If its current mapped task has not been seen yet, keep it as-is
            (no override entry needed for this action).
         b. If the task is already taken (collision), pick the lexicographically
            first task from ALL_TASKS that:
            - has not yet been assigned in this window's override, and
            - is not the task we are replacing (to force meaningful change).
         c. If no alternative is available, leave the action unmapped (None).
      4. Only actions whose mapping is *changed* appear in the override dict.

    Args:
        ranked_action_window: list[str] — action_types in window order.
        current_mapped_tasks: list[str|None] — parallel task mapping list.
        active_mapping:       dict[str, str] — the active action→task mapping.

    Returns:
        (proposed_override: dict[str, str], reasons: list[str])
        proposed_override is empty when no repair is needed or possible.
    """
    if not ranked_action_window:
        return {}, ["action window is empty — no repair can be proposed"]

    # Check for any collision at all.
    seen_counts: dict = {}
    for task in current_mapped_tasks:
        if task is not None:
            seen_counts[task] = seen_counts.get(task, 0) + 1

    colliding_tasks = {t for t, c in seen_counts.items() if c > 1}
    if not colliding_tasks:
        return {}, ["all mapped tasks in the window are already distinct — no repair needed"]

    # Build the repair proposal.
    candidate_pool = sorted(ALL_TASKS)  # deterministic ordering
    assigned_in_window: set = set()
    override: dict = {}
    reasons: list = []

    for action_type, current_task in zip(ranked_action_window, current_mapped_tasks):
        if current_task not in colliding_tasks:
            # Not colliding — keep as-is; mark the task as assigned.
            if current_task is not None:
                assigned_in_window.add(current_task)
            continue

        if current_task not in assigned_in_window:
            # First occurrence of a colliding task — keep the mapping, mark it.
            assigned_in_window.add(current_task)
            continue

        # Collision detected — find the first available alternative.
        replacement = None
        for candidate in candidate_pool:
            if candidate not in assigned_in_window and candidate != current_task:
                replacement = candidate
                break

        if replacement is not None:
            override[action_type] = replacement
            assigned_in_window.add(replacement)
            reasons.append(
                f"{action_type!r} remapped from {current_task!r} to {replacement!r} "
                "to reduce task-collapse collision"
            )
        else:
            reasons.append(
                f"{action_type!r} collides on {current_task!r} but no alternative "
                "task is available — left unchanged"
            )

    return override, reasons


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def propose_mapping_repair(policy_path, portfolio_state_path, ledger_path,
                            top_k=3, exploration_offset=0, output_path=None):
    """Simulate the ranked window and propose a diversifying mapping override.

    Args:
        policy_path:           Path to planner_policy.json (or None).
        portfolio_state_path:  Path to portfolio_state.json.
        ledger_path:           Path to action_effectiveness_ledger.json (or None).
        top_k:                 Window size.
        exploration_offset:    Start index into ranked action list.
        output_path:           If set, write JSON here; otherwise print to stdout.

    Returns:
        The proposal dict.
    """
    ledger = load_effectiveness_ledger(ledger_path)
    signals = load_portfolio_signals(portfolio_state_path)
    policy = load_planner_policy(policy_path)
    active_mapping = resolve_action_to_task_mapping(ACTION_TO_TASK, None)

    raw_actions = _fetch_actions(portfolio_state_path, ledger_path)

    risk = _compute_risk(
        raw_actions, top_k, ledger, signals, policy, active_mapping, exploration_offset,
    )

    ranked_action_window = risk["ranked_action_window"]
    current_mapped_tasks = risk["mapped_tasks"]

    proposed_override, reasons = _propose_repair(
        ranked_action_window, current_mapped_tasks, active_mapping,
    )

    repair_needed = bool(proposed_override)

    proposal = {
        "ranked_action_window": ranked_action_window,
        "current_mapped_tasks": current_mapped_tasks,
        "proposed_mapping_override": proposed_override,
        "repair_needed": repair_needed,
        "reasons": reasons,
    }

    serialized = json.dumps(proposal, indent=2) + "\n"

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized, encoding="utf-8")
        print(f"Wrote {out}", file=sys.stderr)
    else:
        print(serialized, end="")

    return proposal


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Propose a mapping override to repair planner task-collapse risk.",
        add_help=True,
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
        "--policy", default=None, metavar="FILE",
        help="Path to planner_policy.json (optional).",
    )
    parser.add_argument(
        "--top-k", type=int, default=3, metavar="INT",
        help="Number of top actions to consider (default: 3).",
    )
    parser.add_argument(
        "--exploration-offset", type=int, default=0, metavar="INT",
        help="Start index into the action queue window (default: 0).",
    )
    parser.add_argument(
        "--output", default=None, metavar="FILE",
        help="Write proposal JSON to this path. Omit to print to stdout.",
    )
    args = parser.parse_args(argv)

    propose_mapping_repair(
        policy_path=args.policy,
        portfolio_state_path=args.portfolio_state,
        ledger_path=args.ledger,
        top_k=args.top_k,
        exploration_offset=args.exploration_offset,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
