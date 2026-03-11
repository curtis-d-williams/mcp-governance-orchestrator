# SPDX-License-Identifier: MIT
"""Adaptive governed planner loop (v0.1).

Retries planner preflight with progressively broader exploration_offset values
until risk is acceptable (low_risk or moderate_risk), then executes.

If all attempts remain high_risk:
    - aborts by default (exit 1)
    - proceeds on the final attempt when --force is set

Output artifact (JSON):
    selected_offset   int   — offset used for the accepted run (or final attempt)
    attempts          list  — [{offset, risk_level, collision_ratio, unique_tasks}]
    result            dict  — run_experiment result dict (only present on success)
    forced            bool  — present and True only when --force overrode high_risk

Reuses:
    scripts/run_planner_experiment.py  —  run_experiment, _run_preflight_check,
                                         _copy_args, _ARGS_ATTRS

Usage:
    python3 scripts/run_governed_planner_loop.py \\
        --portfolio-state experiments/portfolio_state_degraded_v2.json \\
        --ledger experiments/action_effectiveness_ledger_synthetic_v2.json \\
        --output governed_result.json
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Load run_planner_experiment via importlib (same pattern as other scripts)
# ---------------------------------------------------------------------------

_EXPERIMENT_SCRIPT = Path(__file__).resolve().parent / "run_planner_experiment.py"
_exp_spec = importlib.util.spec_from_file_location("run_planner_experiment", _EXPERIMENT_SCRIPT)
_exp_mod = importlib.util.module_from_spec(_exp_spec)
_exp_spec.loader.exec_module(_exp_mod)

run_experiment = _exp_mod.run_experiment
_run_preflight_check = _exp_mod._run_preflight_check
_copy_args = _exp_mod._copy_args

# ---------------------------------------------------------------------------
# Load propose_mapping_repair via importlib (no subprocess)
# ---------------------------------------------------------------------------

_REPAIR_SCRIPT = Path(__file__).resolve().parent / "propose_mapping_repair.py"
_repair_spec = importlib.util.spec_from_file_location("propose_mapping_repair", _REPAIR_SCRIPT)
_repair_mod = importlib.util.module_from_spec(_repair_spec)
_repair_spec.loader.exec_module(_repair_mod)

_propose_repair = _repair_mod._propose_repair


# ---------------------------------------------------------------------------
# Offset sequence builder
# ---------------------------------------------------------------------------

_DEFAULT_OFFSETS = [0, 1, 2, 3, 5]


def _build_offset_sequence(starting_offset):
    """Return deduplicated offset list beginning with *starting_offset*.

    The candidate pool is [starting_offset] + _DEFAULT_OFFSETS.
    Duplicates are removed while preserving order; starting_offset always first.

    Args:
        starting_offset: int — the user-requested exploration offset.

    Returns:
        list[int] of offsets to try, in order.
    """
    seen = set()
    result = []
    for offset in [starting_offset] + _DEFAULT_OFFSETS:
        if offset not in seen:
            seen.add(offset)
            result.append(offset)
    return result


# ---------------------------------------------------------------------------
# Empty-window detection helper
# ---------------------------------------------------------------------------

def _is_empty_window_high_risk(evaluation):
    """Return True when *evaluation* is high_risk caused by an empty action window.

    Retrying with a different exploration_offset cannot fix an empty window
    (no eligible actions exist regardless of offset), so the loop short-circuits.

    Detection: risk_level == "high_risk" AND at least one reason contains
    "empty" or "no actions".  This matches the reason text produced by
    _classify_risk in evaluate_planner_config.py.

    Args:
        evaluation: dict returned by preflight_fn, or None.

    Returns:
        bool
    """
    if not evaluation:
        return False
    if evaluation.get("risk_level") != "high_risk":
        return False
    return any(
        "empty" in r.lower() or "no actions" in r.lower()
        for r in evaluation.get("reasons", [])
    )


# ---------------------------------------------------------------------------
# Governance metadata helper
# ---------------------------------------------------------------------------

_GOVERNED_LOOP_VERSION = "0.60.0-alpha"


def _build_governance(args, result):
    """Build the governance metadata block for the artifact.

    Args:
        args:   Namespace-like object with CLI attributes.
        result: run_experiment result dict (may be None if not yet executed).

    Returns:
        dict with keys: planner_version, mapping_override, governed_loop_version.
    """
    planner_version = None
    if result is not None:
        runs = result.get("evaluation_summary", {}).get("runs", [])
        if runs:
            planner_version = runs[0].get("planner_version")
    return {
        "governed_loop_version": _GOVERNED_LOOP_VERSION,
        "mapping_override": getattr(args, "mapping_override_path", None),
        "planner_version": planner_version,
    }


# ---------------------------------------------------------------------------
# Abort artifact builder
# ---------------------------------------------------------------------------

def _build_abort_artifact(args, attempts, last_evaluation):
    """Build the artifact written before a persistent high_risk abort.

    Calls _propose_repair using data already in *last_evaluation* (no extra I/O).
    repair_proposal is included when the proposal is non-empty; set to None otherwise.

    Args:
        args:            Namespace-like object with CLI attributes.
        attempts:        list of attempt dicts recorded so far.
        last_evaluation: evaluation dict from the final preflight call, or None.

    Returns:
        dict suitable for _write_artifact.
    """
    repair_proposal = None
    if last_evaluation is not None:
        window = last_evaluation.get("ranked_action_window", [])
        window_detail = last_evaluation.get("ranked_action_window_detail")
        mapped = last_evaluation.get("mapped_tasks", [])
        from scripts.claude_dynamic_planner_loop import ACTION_TO_TASK, resolve_action_to_task_mapping
        active_mapping = resolve_action_to_task_mapping(
            ACTION_TO_TASK, getattr(args, "mapping_override", None)
        )
        proposed_override, repair_reasons = _propose_repair(
            window, mapped, active_mapping, window_detail=window_detail
        )
        if proposed_override:
            repair_proposal = {
                "ranked_action_window": window,
                "current_mapped_tasks": mapped,
                "proposed_mapping_override": proposed_override,
                "repair_needed": True,
                "reasons": repair_reasons,
            }

    artifact = {
        "abort_reason": "high_risk_persistent",
        "attempts": attempts,
        "governance": _build_governance(args, None),
        "repair_proposal": repair_proposal,
    }
    return artifact


# ---------------------------------------------------------------------------
# Core loop (injectable for testing)
# ---------------------------------------------------------------------------

def run_governed_loop(args, planner_main=None, preflight_fn=None):
    """Adaptive governance loop: retry over offsets until risk is acceptable.

    Args:
        args:          Namespace-like object with CLI attributes (see main()).
        planner_main:  Optional planner callable injected for testing.
        preflight_fn:  Optional callable(args) → evaluation dict | None.
                       Defaults to _run_preflight_check.

    Returns:
        A dict with keys: selected_offset, attempts, result.
        When --force overrides a high_risk attempt, "forced": True is added.
        When the action window is empty (no eligible actions), "idle": True and
        "risk_level": "no_action_window" are added instead of "result".

    Raises:
        SystemExit(1) when a high_risk result cannot be resolved and --force
        is not set.  This covers only collision/diversity high_risk where all
        offsets are exhausted.  Empty-window (no eligible actions) is not a
        failure; it returns an idle artifact with rc=0 instead.
    """
    if preflight_fn is None:
        preflight_fn = _run_preflight_check

    offsets = _build_offset_sequence(getattr(args, "exploration_offset", 0) or 0)
    force = getattr(args, "force", False) or False

    attempts = []
    last_evaluation = None

    for offset in offsets:
        attempt_args = _copy_args(args)
        attempt_args.exploration_offset = offset

        evaluation = preflight_fn(attempt_args)
        risk_level = evaluation.get("risk_level", "low_risk") if evaluation else "low_risk"

        attempts.append({
            "offset": offset,
            "risk_level": risk_level,
            "collision_ratio": evaluation.get("collision_ratio", 0.0) if evaluation else 0.0,
            "unique_tasks": evaluation.get("unique_tasks", 0) if evaluation else 0,
        })

        last_evaluation = evaluation

        if risk_level in ("low_risk", "moderate_risk"):
            result = run_experiment(
                attempt_args,
                planner_main=planner_main,
                risk_check_fn=lambda _a: None,  # preflight already done
            )
            artifact = {
                "governance": _build_governance(args, result),
                "selected_offset": offset,
                "attempts": attempts,
                "result": result,
            }
            _write_artifact(args, artifact)
            return artifact

        # high_risk — check for empty-window short-circuit before retrying
        if _is_empty_window_high_risk(evaluation):
            if force:
                result = run_experiment(
                    attempt_args,
                    planner_main=planner_main,
                    risk_check_fn=lambda _a: None,
                )
                artifact = {
                    "governance": _build_governance(args, result),
                    "selected_offset": offset,
                    "attempts": attempts,
                    "result": result,
                    "forced": True,
                }
                _write_artifact(args, artifact)
                return artifact
            # Healthy idle: no eligible actions exist — not a failure.
            artifact = {
                "governance": _build_governance(args, None),
                "idle": True,
                "risk_level": "no_action_window",
                "selected_offset": offset,
                "attempts": attempts,
            }
            _write_artifact(args, artifact)
            return artifact

        # collision/diversity high_risk — continue to next offset

    # All attempts were high_risk.
    final_offset = offsets[-1]
    final_args = _copy_args(args)
    final_args.exploration_offset = final_offset

    if force:
        result = run_experiment(
            final_args,
            planner_main=planner_main,
            risk_check_fn=lambda _a: None,
        )
        artifact = {
            "governance": _build_governance(args, result),
            "selected_offset": final_offset,
            "attempts": attempts,
            "result": result,
            "forced": True,
        }
        _write_artifact(args, artifact)
        return artifact

    # --- Auto-repair attempt (one shot, before final abort) ---
    # Build the abort artifact first — it already calls _propose_repair internally.
    # Empty-window failures are short-circuited above and never reach here.
    _abort_artifact = _build_abort_artifact(args, attempts, last_evaluation)
    _proposal_data = _abort_artifact.get("repair_proposal")
    _proposed_override = (
        _proposal_data.get("proposed_mapping_override") if _proposal_data else None
    )

    if _proposed_override:
        repaired_args = _copy_args(args)
        repaired_args.exploration_offset = final_offset
        repaired_args.mapping_override = _proposed_override

        repaired_eval = preflight_fn(repaired_args)
        repaired_risk = (
            repaired_eval.get("risk_level", "low_risk") if repaired_eval else "low_risk"
        )

        if repaired_risk in ("low_risk", "moderate_risk"):
            result = run_experiment(
                repaired_args,
                planner_main=planner_main,
                risk_check_fn=lambda _a: None,
            )
            artifact = {
                "auto_repair_applied": True,
                "auto_repair_attempted": True,
                "attempts": attempts,
                "governance": _build_governance(args, result),
                "repair_proposal": _proposed_override,
                "repaired_from_offset": final_offset,
                "result": result,
                "selected_offset": final_offset,
            }
            _write_artifact(args, artifact)
            return artifact

        # Repaired preflight is still high_risk — fail-closed.
        _abort_artifact["auto_repair_attempted"] = True
        _abort_artifact["auto_repair_applied"] = False
        _abort_artifact["repaired_from_offset"] = final_offset
        print(
            f"Governed planner loop: all {len(offsets)} offset(s) returned high_risk. "
            "Auto-repair attempted but repaired configuration is still high_risk. "
            "Use --force to run anyway.",
            file=sys.stderr,
        )
        _write_artifact(args, _abort_artifact)
        raise SystemExit(1)

    # Abort (no repair proposal — window is unrepairable).
    print(
        f"Governed planner loop: all {len(offsets)} offset(s) returned high_risk. "
        "Use --force to run anyway.",
        file=sys.stderr,
    )
    _write_artifact(args, _abort_artifact)
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Output artifact writer
# ---------------------------------------------------------------------------

def _write_artifact(args, artifact):
    """Write the governed loop artifact to the configured output path."""
    output_path = Path(getattr(args, "output", "governed_result.json") or "governed_result.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Adaptive governed planner loop: retry over exploration offsets until risk is acceptable.",
        add_help=True,
    )
    parser.add_argument("--runs", type=int, default=1, metavar="INT",
                        help="Number of planner runs per attempt (default: 1).")
    parser.add_argument("--portfolio-state", default=None, metavar="FILE",
                        help="Path to portfolio_state.json.")
    parser.add_argument("--ledger", default=None, metavar="FILE",
                        help="Path to action_effectiveness_ledger.json.")
    parser.add_argument("--policy", default=None, metavar="FILE",
                        help="Path to planner_policy.json.")
    parser.add_argument("--top-k", type=int, default=3, metavar="INT",
                        help="Number of top actions to consider (default: 3).")
    parser.add_argument("--exploration-offset", type=int, default=0, metavar="INT",
                        help="Starting exploration offset (default: 0).")
    parser.add_argument("--max-actions", type=int, default=None, metavar="INT",
                        help="Cap selected actions per run.")
    parser.add_argument("--explain", action="store_true", default=False,
                        help="Pass --explain to each planner run.")
    parser.add_argument("--force", action="store_true", default=False,
                        help="Execute final attempt even when all offsets return high_risk.")
    parser.add_argument("--output", default="governed_result.json", metavar="FILE",
                        help="Output path for governed loop artifact (default: governed_result.json).")
    parser.add_argument("--envelope-prefix", default="planner_run_envelope", metavar="STR",
                        help="Prefix for envelope filenames (default: planner_run_envelope).")
    parser.add_argument("--mapping-override", default=None, metavar="FILE",
                        help="Path to JSON file overriding the action→task mapping (optional).")

    args = parser.parse_args(argv)

    if args.mapping_override is not None:
        args.mapping_override_path = args.mapping_override
        args.mapping_override = json.loads(
            Path(args.mapping_override_path).read_text(encoding="utf-8")
        )
    else:
        args.mapping_override_path = None

    run_governed_loop(args)


if __name__ == "__main__":
    main()
