# SPDX-License-Identifier: MIT
"""Shared deterministic orchestration runtime for governed planner execution."""

import json
import sys
from pathlib import Path


_DEFAULT_OFFSETS = [0, 1, 2, 3, 5]
_GOVERNED_LOOP_VERSION = "0.60.0-alpha"


def build_offset_sequence(starting_offset):
    """Return deduplicated offset list beginning with *starting_offset*."""
    seen = set()
    result = []
    for offset in [starting_offset] + _DEFAULT_OFFSETS:
        if offset not in seen:
            seen.add(offset)
            result.append(offset)
    return result


def is_empty_window_high_risk(evaluation):
    """Return True when *evaluation* is high_risk caused by an empty action window."""
    if not evaluation:
        return False
    if evaluation.get("risk_level") != "high_risk":
        return False
    return any(
        "empty" in r.lower() or "no actions" in r.lower()
        for r in evaluation.get("reasons", [])
    )


def build_governance(args, result):
    """Build the governance metadata block for the artifact."""
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


def build_abort_artifact(args, attempts, last_evaluation, *, propose_repair):
    """Build the artifact written before a persistent high_risk abort."""
    repair_proposal = None
    if last_evaluation is not None:
        window = last_evaluation.get("ranked_action_window", [])
        window_detail = last_evaluation.get("ranked_action_window_detail")
        mapped = last_evaluation.get("mapped_tasks", [])

        from scripts.claude_dynamic_planner_loop import ACTION_TO_TASK, resolve_action_to_task_mapping

        active_mapping = resolve_action_to_task_mapping(
            ACTION_TO_TASK, getattr(args, "mapping_override", None)
        )
        proposed_override, repair_reasons = propose_repair(
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

    return {
        "abort_reason": "high_risk_persistent",
        "attempts": attempts,
        "governance": build_governance(args, None),
        "repair_proposal": repair_proposal,
    }


def default_learning_output(args):
    output_path = Path(getattr(args, "output", "governed_result.json") or "governed_result.json")
    return str(output_path.with_name(output_path.stem + "_learned_ledger.json"))


def run_optional_repair_cycle(args, *, run_mapping_repair_cycle):
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


def apply_optional_learning(args, artifact, *, update_action_effectiveness_ledger):
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


def run_governed_loop(
    args,
    *,
    run_experiment,
    preflight_fn,
    copy_args,
    propose_repair,
    run_mapping_repair_cycle,
    update_action_effectiveness_ledger,
    write_artifact,
    planner_main=None,
):
    """Adaptive governance loop: retry over offsets until risk is acceptable."""
    offsets = build_offset_sequence(getattr(args, "exploration_offset", 0) or 0)
    force = getattr(args, "force", False) or False

    attempts = []
    last_evaluation = None

    for offset in offsets:
        attempt_args = copy_args(args)
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
                risk_check_fn=lambda _a: None,
            )
            artifact = {
                "governance": build_governance(args, result),
                "selected_offset": offset,
                "attempts": attempts,
                "result": result,
            }
            artifact = apply_optional_learning(
                args, artifact,
                update_action_effectiveness_ledger=update_action_effectiveness_ledger,
            )
            write_artifact(args, artifact)
            return artifact

        if is_empty_window_high_risk(evaluation):
            if force:
                result = run_experiment(
                    attempt_args,
                    planner_main=planner_main,
                    risk_check_fn=lambda _a: None,
                )
                artifact = {
                    "governance": build_governance(args, result),
                    "selected_offset": offset,
                    "attempts": attempts,
                    "result": result,
                    "forced": True,
                }
                artifact = apply_optional_learning(
                    args, artifact,
                    update_action_effectiveness_ledger=update_action_effectiveness_ledger,
                )
                write_artifact(args, artifact)
                return artifact

            artifact = {
                "governance": build_governance(args, None),
                "idle": True,
                "risk_level": "no_action_window",
                "selected_offset": offset,
                "attempts": attempts,
            }
            write_artifact(args, artifact)
            return artifact

    final_offset = offsets[-1]
    final_args = copy_args(args)
    final_args.exploration_offset = final_offset

    if force:
        result = run_experiment(
            final_args,
            planner_main=planner_main,
            risk_check_fn=lambda _a: None,
        )
        artifact = {
            "governance": build_governance(args, result),
            "selected_offset": final_offset,
            "attempts": attempts,
            "result": result,
            "forced": True,
        }
        artifact = apply_optional_learning(
            args, artifact,
            update_action_effectiveness_ledger=update_action_effectiveness_ledger,
        )
        write_artifact(args, artifact)
        return artifact

    abort_artifact = build_abort_artifact(
        args, attempts, last_evaluation, propose_repair=propose_repair
    )

    if getattr(args, "auto_repair_cycle", False):
        cycle_result = run_optional_repair_cycle(
            args, run_mapping_repair_cycle=run_mapping_repair_cycle
        )
        abort_artifact["auto_repair_cycle"] = cycle_result

        if cycle_result.get("repair_success") and cycle_result.get("override_artifact"):
            repaired_args = copy_args(args)
            repaired_args.exploration_offset = final_offset
            repaired_args.mapping_override = cycle_result["override_artifact"]

            result = run_experiment(
                repaired_args,
                planner_main=planner_main,
                risk_check_fn=lambda _a: None,
            )
            artifact = {
                "auto_repair_applied": True,
                "auto_repair_attempted": True,
                "auto_repair_cycle_used": True,
                "attempts": attempts,
                "governance": build_governance(args, result),
                "repair_proposal": cycle_result["override_artifact"],
                "repair_cycle_status": cycle_result.get("status"),
                "repaired_from_offset": final_offset,
                "result": result,
                "selected_offset": final_offset,
            }
            artifact = apply_optional_learning(
                args, artifact,
                update_action_effectiveness_ledger=update_action_effectiveness_ledger,
            )
            write_artifact(args, artifact)
            return artifact

    proposal_data = abort_artifact.get("repair_proposal")
    proposed_override = (
        proposal_data.get("proposed_mapping_override") if proposal_data else None
    )

    if proposed_override:
        repaired_args = copy_args(args)
        repaired_args.exploration_offset = final_offset
        repaired_args.mapping_override = proposed_override

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
                "governance": build_governance(args, result),
                "repair_proposal": proposed_override,
                "repaired_from_offset": final_offset,
                "result": result,
                "selected_offset": final_offset,
            }
            artifact = apply_optional_learning(
                args, artifact,
                update_action_effectiveness_ledger=update_action_effectiveness_ledger,
            )
            write_artifact(args, artifact)
            return artifact

        abort_artifact["auto_repair_attempted"] = True
        abort_artifact["auto_repair_applied"] = False
        abort_artifact["repaired_from_offset"] = final_offset
        print(
            f"Governed planner loop: all {len(offsets)} offset(s) returned high_risk. "
            "Auto-repair attempted but repaired configuration is still high_risk. "
            "Use --force to run anyway.",
            file=sys.stderr,
        )
        write_artifact(args, abort_artifact)
        raise SystemExit(1)

    print(
        f"Governed planner loop: all {len(offsets)} offset(s) returned high_risk. "
        "Use --force to run anyway.",
        file=sys.stderr,
    )
    write_artifact(args, abort_artifact)
    raise SystemExit(1)
