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
# Risk classification rubric
# ---------------------------------------------------------------------------

# A gap larger than this (in bits) between action_entropy and task_entropy is
# treated as a secondary indicator of collision pressure.
_ENTROPY_DIVERGENCE_THRESHOLD = 0.3


def _classify_risk(metrics, top_k):
    """Classify risk level and produce reasons + recommendations.

    Deterministic rubric (evaluated in priority order):

    high_risk:
        - collision_ratio >= 0.5
        - OR unique_tasks <= 1 with top_k >= 3
        - OR entropy_gap >= 1.0

    moderate_risk (when not high_risk):
        - collision_ratio > 0
        - OR task_entropy materially below action_entropy
          (action_entropy - task_entropy > _ENTROPY_DIVERGENCE_THRESHOLD)

    low_risk:
        - collision_ratio == 0
        - AND task_entropy is not materially below action_entropy

    Args:
        metrics: dict produced by _compute_risk (all keys required).
        top_k:   window size (int) used for the analysis.

    Returns:
        (risk_level: str, reasons: list[str], recommendations: list[str])
    """
    collision_ratio = metrics["collision_ratio"]
    unique_tasks = metrics["unique_tasks"]
    collapse_count = metrics["collapse_count"]
    task_entropy = metrics["task_entropy"]
    action_entropy = metrics["action_entropy"]
    window_size = len(metrics["ranked_action_window"])
    entropy_gap = action_entropy - task_entropy

    reasons: list = []
    recommendations: list = []

    # --- Empty window: nothing to evaluate ---
    if window_size == 0:
        return (
            "low_risk",
            ["action window is empty: no actions available to evaluate"],
            ["safe to use as-is"],
        )

    # --- High-risk conditions ---
    high = False

    if collision_ratio >= 0.5:
        high = True
        reasons.append(
            f"collision_ratio is {collision_ratio:.6f} (>=0.5): more than half the window "
            "actions collapse to already-seen tasks, severely limiting task diversity"
        )

    if unique_tasks <= 1 and top_k >= 3:
        high = True
        reasons.append(
            f"unique_tasks={unique_tasks} with top_k={top_k}: the window selects at most "
            "one distinct task despite a large window — mapping collapse is near-total"
        )

    if entropy_gap >= 1.0:
        high = True
        reasons.append(
            f"entropy_gap is {entropy_gap:.6f} bits (>=1.0): action diversity greatly exceeds task diversity, indicating severe task compression"
        )

    if high:
        recommendations.append(
            "consider reducing mapping collisions by splitting overloaded task targets"
        )
        recommendations.append(
            "inspect top_k window composition — multiple high-priority actions map to the same task"
        )
        recommendations.append(
            "try a different policy or --mapping-override to diversify task selection"
        )
        return "high_risk", reasons, recommendations

    # --- Moderate-risk conditions ---
    moderate = False

    if collision_ratio > 0:
        moderate = True
        reasons.append(
            f"collision_ratio is {collision_ratio:.6f}: {collapse_count} action(s) in the "
            "window collapse to tasks already targeted by higher-ranked actions"
        )

    if entropy_gap > _ENTROPY_DIVERGENCE_THRESHOLD:
        moderate = True
        reasons.append(
            f"task_entropy ({task_entropy:.6f} bits) is materially below action_entropy "
            f"({action_entropy:.6f} bits): task diversity is compressed relative to action diversity"
        )

    if moderate:
        if collision_ratio > 0:
            recommendations.append(
                "consider reducing mapping collisions for better task coverage"
            )
        if entropy_gap > _ENTROPY_DIVERGENCE_THRESHOLD:
            recommendations.append(
                "try a different policy or --mapping-override to spread tasks more evenly"
            )
        return "moderate_risk", reasons, recommendations

    # --- Low risk ---
    if window_size > 0:
        reasons.append(
            "collision_ratio is 0.0: all window actions map to distinct tasks"
        )
        if abs(action_entropy - task_entropy) <= 0.001:
            reasons.append(
                "task entropy closely tracks action entropy: ranked window preserves task diversity well"
            )
    else:
        reasons.append("action window is empty: no actions available to evaluate")

    recommendations.append("safe to use as-is")
    return "low_risk", reasons, recommendations


# ---------------------------------------------------------------------------
# Pure evaluation builder (testable without subprocess)
# ---------------------------------------------------------------------------

def build_evaluation(metrics, top_k):
    """Attach risk_level, reasons, and recommendations to a metrics dict.

    Args:
        metrics: dict from _compute_risk (ranked_action_window, mapped_tasks,
                 unique_tasks, collapse_count, collision_ratio, task_entropy,
                 action_entropy).
        top_k:   window size used for the analysis.

    Returns:
        New dict with all metrics keys plus risk_level, reasons, recommendations.
    """
    risk_level, reasons, recommendations = _classify_risk(metrics, top_k)
    return {
        **metrics,
        "risk_level": risk_level,
        "reasons": reasons,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def evaluate_planner_config(policy_path, top_k, portfolio_state_path, ledger_path,
                             mapping_override_path=None, output_path=None,
                             exploration_offset=0):
    """Run collision-risk analysis and produce an operator evaluation.

    Args:
        policy_path:           Path to planner_policy.json (or None / nonexistent).
        top_k:                 Window size.
        portfolio_state_path:  Path to portfolio_state.json.
        ledger_path:           Path to action_effectiveness_ledger.json (or None).
        mapping_override_path: Path to mapping-override JSON file (or None).
        output_path:           If set, write evaluation JSON here; otherwise stdout only.
        exploration_offset:    Start index into ranked action list (default: 0).

    Returns:
        The evaluation dict.
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

    metrics = _compute_risk(
        raw_actions, top_k, ledger, signals, policy, active_mapping, exploration_offset,
    )

    evaluation = build_evaluation(metrics, top_k)
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
    )


if __name__ == "__main__":
    main()
