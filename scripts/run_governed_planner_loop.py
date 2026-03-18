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

from governed_runtime import (
    apply_optional_learning as _apply_optional_learning,
    build_abort_artifact as _build_abort_artifact,
    build_governance as _build_governance,
    build_offset_sequence as _build_offset_sequence,
    default_learning_output as _default_learning_output,
    is_empty_window_high_risk as _is_empty_window_high_risk,
    run_governed_loop as _runtime_run_governed_loop,
    run_optional_repair_cycle as _run_optional_repair_cycle,
)

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
# Load run_mapping_repair_cycle via importlib (optional safeguard)
# ---------------------------------------------------------------------------

_REPAIR_CYCLE_SCRIPT = Path(__file__).resolve().parent / "run_mapping_repair_cycle.py"
_repair_cycle_spec = importlib.util.spec_from_file_location("run_mapping_repair_cycle", _REPAIR_CYCLE_SCRIPT)
_repair_cycle_mod = importlib.util.module_from_spec(_repair_cycle_spec)
_repair_cycle_spec.loader.exec_module(_repair_cycle_mod)

run_mapping_repair_cycle = _repair_cycle_mod.run_mapping_repair_cycle

# ---------------------------------------------------------------------------
# Load update_action_effectiveness_ledger via importlib (optional learning)
# ---------------------------------------------------------------------------

_LEARNING_SCRIPT = Path(__file__).resolve().parent / "update_action_effectiveness_ledger.py"
_learning_spec = importlib.util.spec_from_file_location("update_action_effectiveness_ledger", _LEARNING_SCRIPT)
_learning_mod = importlib.util.module_from_spec(_learning_spec)
_learning_spec.loader.exec_module(_learning_mod)

update_action_effectiveness_ledger = _learning_mod.update_action_effectiveness_ledger


# ---------------------------------------------------------------------------
# Core loop wrapper (backward-compatible script API)
# ---------------------------------------------------------------------------

def run_governed_loop(args, planner_main=None, preflight_fn=None):
    """Adaptive governance loop wrapper preserving the historical script API."""
    return _runtime_run_governed_loop(
        args,
        run_experiment=run_experiment,
        preflight_fn=preflight_fn or _run_preflight_check,
        copy_args=_copy_args,
        propose_repair=_propose_repair,
        run_mapping_repair_cycle=run_mapping_repair_cycle,
        update_action_effectiveness_ledger=update_action_effectiveness_ledger,
        write_artifact=_write_artifact,
        planner_main=planner_main,
    )


# ---------------------------------------------------------------------------
# Output artifact writer
# ---------------------------------------------------------------------------

def _run_optional_repair_cycle(args):
    """Run the standalone repair cycle and return its result dict."""
    output_path = Path(getattr(args, "output", "governed_result.json") or "governed_result.json")
    cycle_output = output_path.with_name(output_path.stem + "_repair_cycle.json")
    cycle_override = output_path.with_name(output_path.stem + "_repair_override.json")

    return run_mapping_repair_cycle(
        portfolio_state_path=getattr(args, "portfolio_state", None),
        ledger_path=getattr(args, "ledger", None),
        policy_path=getattr(args, "policy", None),
        top_k=getattr(args, "top_k", 3),
        exploration_offset=getattr(args, "exploration_offset", 0) or 0,
        output_path=str(cycle_output),
        override_output_path=str(cycle_override),
    )


def _default_learning_output(args):
    output_path = Path(getattr(args, "output", "governed_result.json") or "governed_result.json")
    return str(output_path.with_name(output_path.stem + "_learned_ledger.json"))


def _apply_optional_learning(args, artifact):
    """Optionally update the effectiveness ledger from a governed artifact."""
    learning_output = getattr(args, "learn_ledger_output", None)
    if not learning_output:
        return artifact

    ledger_path = getattr(args, "ledger", None)
    if not ledger_path:
        artifact["learning_update"] = {
            "applied": False,
            "reason": "no_ledger_path",
        }
        return artifact

    artifact_path = Path(getattr(args, "output", "governed_result.json") or "governed_result.json")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    learning_result = update_action_effectiveness_ledger(
        ledger_path=ledger_path,
        governed_artifact_path=str(artifact_path),
        output_path=learning_output,
    )
    artifact["learning_update"] = {
        "applied": True,
        **learning_result,
    }
    return artifact


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
    parser.add_argument("--auto-repair-cycle", action="store_true", default=False,
                        help="When all offsets remain high_risk, run the validated mapping repair cycle before aborting.")
    parser.add_argument("--learn-ledger-output", default=None, metavar="FILE",
                        help="After a successful governed run, write an updated effectiveness ledger to this path.")
    parser.add_argument("--capability-ledger", default=None, dest="capability_ledger", metavar="FILE",
                        help="Path to capability_effectiveness_ledger.json (optional).")

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
