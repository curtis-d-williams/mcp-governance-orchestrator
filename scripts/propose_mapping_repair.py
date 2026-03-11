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

def _propose_repair(ranked_action_window, current_mapped_tasks, active_mapping,
                    window_detail=None):
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
      4. When a repair is needed, the override covers ALL actions in the window
         (including unchanged ones) so it can be applied as a complete effective
         override without depending on the default mapping for any window action.
         Actions with no current task mapping are omitted from the override.

    When window_detail is provided (list of {action_id, action_type, repo_id}
    dicts), the proposed_mapping_override uses a structured schema:
      {
        "by_action_id": {action_id: task},   # for duplicate action_types
        "by_action_type": {action_type: task} # for unique action_types
      }
    This prevents duplicate action_type overrides from overwriting each other.

    When window_detail is None, falls back to the flat {action_type: task} schema
    for backward compatibility with existing callers and tests.

    Args:
        ranked_action_window: list[str] — action_types in window order.
        current_mapped_tasks: list[str|None] — parallel task mapping list.
        active_mapping:       dict[str, str] — the active action→task mapping.
        window_detail:        optional list[dict] — per-action {action_id,
                              action_type, repo_id}; enables structured output.

    Returns:
        (proposed_override: dict, reasons: list[str])
        proposed_override is empty ({}) when no repair is needed or possible.
        When window_detail is absent, proposed_override is flat {action_type: task}.
        When window_detail is present, proposed_override is structured
        {"by_action_id": {...}, "by_action_type": {...}} (keys omitted if empty).
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
    reasons: list = []

    # --- Detect duplicate action_types (needed for both paths when window_detail given) ---
    type_counts: dict = {}
    if window_detail is not None:
        for d in window_detail:
            at = d["action_type"]
            type_counts[at] = type_counts.get(at, 0) + 1

    # Use flat dict algorithm when window_detail is absent OR when no action_type
    # appears more than once (structured format only needed for actual dups).
    has_dup_types = any(c > 1 for c in type_counts.values())

    if window_detail is None or not has_dup_types:
        # --- Original flat dict algorithm (backward compat) ---
        override: dict = {}
        for action_type, current_task in zip(ranked_action_window, current_mapped_tasks):
            if current_task not in colliding_tasks:
                # Not colliding — preserve mapping in full override; mark task assigned.
                if current_task is not None:
                    override[action_type] = current_task
                    assigned_in_window.add(current_task)
                continue

            if current_task not in assigned_in_window:
                # First occurrence of a colliding task — preserve; mark assigned.
                override[action_type] = current_task
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

    # --- Instance-aware algorithm: window_detail provided AND has duplicate types ---

    by_action_id: dict = {}
    by_action_type: dict = {}

    for detail, current_task in zip(window_detail, current_mapped_tasks):
        action_id = detail["action_id"]
        action_type = detail["action_type"]
        # Use action_id key when the type appears more than once (prevents overwrite).
        use_id_key = type_counts.get(action_type, 1) > 1

        def _store(key_id, key_type, task):
            if use_id_key:
                by_action_id[key_id] = task
            else:
                by_action_type[key_type] = task

        if current_task not in colliding_tasks:
            # Not colliding — preserve mapping; mark task assigned.
            if current_task is not None:
                _store(action_id, action_type, current_task)
                assigned_in_window.add(current_task)
            continue

        if current_task not in assigned_in_window:
            # First occurrence of a colliding task — preserve; mark assigned.
            _store(action_id, action_type, current_task)
            assigned_in_window.add(current_task)
            continue

        # Collision detected — find the first available alternative.
        replacement = None
        for candidate in candidate_pool:
            if candidate not in assigned_in_window and candidate != current_task:
                replacement = candidate
                break

        if replacement is not None:
            _store(action_id, action_type, replacement)
            assigned_in_window.add(replacement)
            reasons.append(
                f"{action_type!r} (id={action_id!r}) remapped from {current_task!r} "
                f"to {replacement!r} to reduce task-collapse collision"
            )
        else:
            reasons.append(
                f"{action_type!r} (id={action_id!r}) collides on {current_task!r} "
                "but no alternative task is available — left unchanged"
            )

    structured: dict = {}
    if by_action_id:
        structured["by_action_id"] = by_action_id
    if by_action_type:
        structured["by_action_type"] = by_action_type

    return structured, reasons


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def propose_mapping_repair(policy_path, portfolio_state_path, ledger_path,
                            top_k=3, exploration_offset=0, output_path=None,
                            output_override_path=None):
    """Simulate the ranked window and propose a diversifying mapping override.

    Args:
        policy_path:           Path to planner_policy.json (or None).
        portfolio_state_path:  Path to portfolio_state.json.
        ledger_path:           Path to action_effectiveness_ledger.json (or None).
        top_k:                 Window size.
        exploration_offset:    Start index into ranked action list.
        output_path:           If set, write full proposal JSON here; otherwise print to stdout.
        output_override_path:  If set, write only proposed_mapping_override JSON here.

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
    ranked_action_window_detail = risk.get("ranked_action_window_detail")
    current_mapped_tasks = risk["mapped_tasks"]

    proposed_override, reasons = _propose_repair(
        ranked_action_window, current_mapped_tasks, active_mapping,
        window_detail=ranked_action_window_detail,
    )

    repair_needed = bool(proposed_override)

    proposal = {
        "ranked_action_window": ranked_action_window,
        "ranked_action_window_detail": ranked_action_window_detail,
        "current_mapped_tasks": current_mapped_tasks,
        "proposed_mapping_override": proposed_override,
        "repair_needed": repair_needed,
        "reasons": reasons,
    }

    serialized = json.dumps(proposal, indent=2) + "\n"
    override_serialized = json.dumps(
        proposal["proposed_mapping_override"], indent=2, sort_keys=True
    ) + "\n"

    wrote_any = False

    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(serialized, encoding="utf-8")
        print(f"Wrote {out}", file=sys.stderr)
        wrote_any = True

    if output_override_path is not None:
        out_override = Path(output_override_path)
        out_override.parent.mkdir(parents=True, exist_ok=True)
        out_override.write_text(override_serialized, encoding="utf-8")
        print(f"Wrote {out_override}", file=sys.stderr)
        wrote_any = True

    if not wrote_any:
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
        help="Write full proposal JSON to this path. Omit to print to stdout.",
    )
    parser.add_argument(
        "--output-override", default=None, metavar="FILE",
        help="Write only proposed_mapping_override JSON to this path.",
    )
    args = parser.parse_args(argv)

    propose_mapping_repair(
        policy_path=args.policy,
        portfolio_state_path=args.portfolio_state,
        ledger_path=args.ledger,
        top_k=args.top_k,
        exploration_offset=args.exploration_offset,
        output_path=args.output,
        output_override_path=args.output_override,
    )


if __name__ == "__main__":
    main()
