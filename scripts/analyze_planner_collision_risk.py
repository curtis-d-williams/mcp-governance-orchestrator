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
import math
import subprocess
import sys
from pathlib import Path

# Ensure repo root is on sys.path for `from scripts.*` imports,
# whether invoked directly or via importlib from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.planner_scoring import (
    _apply_learning_adjustments,
    load_effectiveness_ledger,
    load_planner_policy,
    load_portfolio_signals,
)
from scripts.claude_dynamic_planner_loop import ACTION_TO_TASK, resolve_action_to_task_mapping

OUTPUT_FILE = Path("planner_risk_summary.json")


# ---------------------------------------------------------------------------
# Entropy helper (matches generate_experiment_report._entropy exactly)
# ---------------------------------------------------------------------------

def _entropy(counts):
    """Shannon entropy in bits from a label-frequency dict.

    Args:
        counts: dict mapping str labels to non-negative counts.

    Returns:
        Entropy in bits (float), rounded to 6 decimal places.
        Returns 0.0 when counts is empty or all counts are zero.

    Keys iterated in sorted order for deterministic float accumulation.
    """
    total = sum(counts.values())
    if total == 0:
        return 0.0
    h = 0.0
    for key in sorted(counts):
        p = counts[key] / total
        if p > 0:
            h -= p * math.log2(p)
    return round(h, 6)


# ---------------------------------------------------------------------------
# Action-queue fetch (mirrors _fetch_action_queue in claude_dynamic_planner_loop)
# ---------------------------------------------------------------------------

def _fetch_actions(portfolio_state_path, ledger_path=None):
    """Invoke list_portfolio_actions.py and return a parsed action list.

    Returns [] on any error so callers can degrade gracefully.
    """
    cmd = [
        sys.executable,
        "scripts/list_portfolio_actions.py",
        "--input", str(portfolio_state_path),
        "--json",
    ]
    if ledger_path is not None:
        cmd += ["--ledger", str(ledger_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(
                f"Action queue fetch failed (rc={result.returncode}): "
                f"{result.stderr.strip()}",
                file=sys.stderr,
            )
            return []
        return json.loads(result.stdout)
    except Exception as exc:
        print(f"Action queue fetch error: {exc}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# Pure risk computation (testable without subprocess)
# ---------------------------------------------------------------------------

def _compute_risk(actions, top_k, ledger, signals, policy, active_mapping,
                  exploration_offset=0):
    """Compute collision-risk metrics from pre-loaded, pre-fetched data.

    This is the pure, deterministic core — no I/O, no subprocess.

    Args:
        actions:           Raw action list (dicts with action_type, priority, …).
        top_k:             Window size.
        ledger:            {action_type: row_dict} effectiveness ledger.
        signals:           {signal_name: float} portfolio signal averages.
        policy:            {signal_name: weight} planner policy weights.
        active_mapping:    {action_type: task_name} active action→task mapping.
        exploration_offset: Start index into the ranked list (default: 0).

    Returns:
        dict with keys: ranked_action_window, mapped_tasks, unique_tasks,
        collapse_count, collision_ratio, task_entropy, action_entropy.
    """
    # Rank actions using the planner's exact scoring formula.
    ranked = _apply_learning_adjustments(actions, ledger, signals, policy)

    # Slice the exploration window (exact planner logic).
    start = max(0, min(exploration_offset, max(0, len(ranked) - top_k)))
    end = start + top_k
    window = ranked[start:end]

    ranked_action_window = [a.get("action_type", "") for a in window]

    # Map each action to its task; track first-seen tasks.
    mapped_tasks = []
    seen_tasks = set()
    for at in ranked_action_window:
        task = active_mapping.get(at)
        mapped_tasks.append(task)
        if task is not None and task not in seen_tasks:
            seen_tasks.add(task)

    unique_tasks = len(seen_tasks)
    window_size = len(ranked_action_window)

    # collapse_count: actions that did not contribute a new unique task.
    # Consistent with planner's action_task_collapse_count formula.
    collapse_count = window_size - unique_tasks
    collision_ratio = (
        round(collapse_count / window_size, 6) if window_size > 0 else 0.0
    )

    # Task entropy: over the frequency distribution of mapped (non-None) tasks.
    task_counts: dict = {}
    for t in mapped_tasks:
        if t is not None:
            task_counts[t] = task_counts.get(t, 0) + 1
    task_entropy = _entropy(task_counts)

    # Action entropy: over action types in the window.
    action_counts: dict = {}
    for at in ranked_action_window:
        action_counts[at] = action_counts.get(at, 0) + 1
    action_entropy = _entropy(action_counts)

    return {
        "ranked_action_window": ranked_action_window,
        "mapped_tasks": mapped_tasks,
        "unique_tasks": unique_tasks,
        "collapse_count": collapse_count,
        "collision_ratio": collision_ratio,
        "task_entropy": task_entropy,
        "action_entropy": action_entropy,
    }


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def analyze_collision_risk(policy_path, top_k, portfolio_state_path, ledger_path,
                            mapping_override_path=None, output_path=None,
                            exploration_offset=0):
    """Run collision-risk analysis and write the summary JSON.

    Args:
        policy_path:           Path to planner_policy.json (or None / nonexistent).
        top_k:                 Window size.
        portfolio_state_path:  Path to portfolio_state.json.
        ledger_path:           Path to action_effectiveness_ledger.json (or None).
        mapping_override_path: Path to mapping-override JSON file (or None).
        output_path:           Destination path for summary (default: planner_risk_summary.json).
        exploration_offset:    Start index into ranked action list (default: 0).

    Returns:
        The summary dict that was written to disk.
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
