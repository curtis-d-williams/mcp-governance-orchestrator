# SPDX-License-Identifier: MIT
"""
Canonical orchestration pipeline for a single MCP factory cycle.
"""

import io
from contextlib import redirect_stdout
from pathlib import Path
import json

from builder.artifact_registry import build_capability_artifact
import builder  # noqa: F401 — triggers @register_builder side effects in all builder modules
from src.mcp_governance_orchestrator.capability_registry import (
    artifact_kind_for_capability,
    get_reference_artifact_path,
)
from src.mcp_governance_orchestrator.capability_effectiveness_ledger import (
    record_synthesis_event,
    record_normalized_synthesis_event,
)

from scripts.compare_mcp_servers import compare_mcp_servers
from scripts.update_capability_gaps_from_mcp_comparison import (
    derive_capability_gaps_from_comparison,
)

from src.mcp_governance_orchestrator.capability_evolution_planner import (
    plan_capability_evolution,
)
from src.mcp_governance_orchestrator.capability_evolution_executor import (
    build_evolution_execution,
)



def decide_action(evaluation):
    if not evaluation:
        return {"action": "idle", "reason": "no_evaluation"}

    risk = evaluation.get("risk_level")

    if risk == "high_risk":
        return {
            "action": "repair_only",
            "reason": "planner_high_risk",
            "repair_enabled": True,
            "learning_enabled": False,
        }

    if risk in ("low_risk", "moderate_risk"):
        return {
            "action": "governed_run",
            "reason": "planner_acceptable_risk",
            "repair_enabled": True,
            "learning_enabled": True,
        }

    return {"action": "idle", "reason": "unknown_state"}


def _resolve_factory_build_request(first_run):
    """
    Resolve a capability-artifact build request from planner output.

    Backward compatibility:
    - legacy action_type == "build_mcp_server" normalizes to a capability request
    - generic action_type == "build_capability_artifact" is the canonical form
    """

    selected_actions = first_run.get("selected_actions", [])
    selection_detail = first_run.get("selection_detail", {})
    ranked_action_window = selection_detail.get("ranked_action_window", [])
    ranked_action_window_detail = selection_detail.get(
        "ranked_action_window_detail",
        [],
    )

    candidate_action_types = []
    candidate_action_types.extend(selected_actions)
    candidate_action_types.extend(ranked_action_window)

    has_build_request = any(
        action_type in ("build_capability_artifact", "build_mcp_server")
        for action_type in candidate_action_types
    )
    if not has_build_request:
        return None

    request = {
        "artifact_kind": None,
        "capability": None,
    }

    for action in ranked_action_window_detail:
        action_type = action.get("action_type")
        args = action.get("task_binding", {}).get("args", {})

        if action_type not in ("build_capability_artifact", "build_mcp_server"):
            continue

        if action_type == "build_mcp_server":
            request["artifact_kind"] = "mcp_server"

        request["artifact_kind"] = args.get(
            "artifact_kind",
            request["artifact_kind"],
        )
        request["capability"] = args.get(
            "capability",
            request["capability"],
        )
        break

    if request["capability"] is None and "build_mcp_server" in candidate_action_types:
        request["capability"] = "github_repository_management"
        request["artifact_kind"] = "mcp_server"

    if request["capability"] is None:
        return None

    if request["artifact_kind"] is None:
        request["artifact_kind"] = artifact_kind_for_capability(
            request["capability"]
        )

    if request["artifact_kind"] is None:
        return None

    return request


def _resolve_gap_synthesis_request(portfolio_state_path):
    """
    Resolve a capability-artifact build request from portfolio capability gaps.

    This is the autonomous fallback when the planner does not emit an explicit
    build request.
    """
    try:
        state = json.loads(Path(portfolio_state_path).read_text(encoding="utf-8"))
    except Exception:
        return None

    capability_gaps = state.get("capability_gaps", [])
    if capability_gaps:
        capability = capability_gaps[0]
        if not isinstance(capability, str):
            return None

        artifact_kind = artifact_kind_for_capability(capability)
        if artifact_kind is None:
            return None

        return {
            "artifact_kind": artifact_kind,
            "capability": capability,
        }

    for action in state.get("portfolio_recommendations", []):
        if not isinstance(action, dict):
            continue

        action_type = action.get("action_type")
        if action_type not in ("build_capability_artifact", "build_mcp_server"):
            continue

        args = action.get("task_binding", {}).get("args", {})
        capability = args.get("capability")
        artifact_kind = args.get("artifact_kind")

        if action_type == "build_mcp_server" and capability is None:
            capability = "github_repository_management"
        if action_type == "build_mcp_server" and artifact_kind is None:
            artifact_kind = "mcp_server"
        if capability is None:
            continue
        if artifact_kind is None:
            artifact_kind = artifact_kind_for_capability(capability)
        if artifact_kind is None:
            continue

        return {
            "artifact_kind": artifact_kind,
            "capability": capability,
        }

    return None


def run_factory_cycle(
    *,
    portfolio_state,
    ledger,
    capability_ledger=None,
    policy,
    top_k,
    output,
    evaluate_planner_config,
    run_mapping_repair_cycle,
    run_governed_loop,
):
    """
    Execute a single factory cycle using injected runtime capabilities.
    """

    with redirect_stdout(io.StringIO()):
        evaluation = evaluate_planner_config(
            portfolio_state_path=portfolio_state,
            ledger_path=ledger,
            capability_ledger_path=capability_ledger,
            policy_path=policy,
            top_k=top_k,
            exploration_offset=0,
            mapping_override_path=None,
            output_path=None,
        )

    decision = decide_action(evaluation)

    result = None
    evolution_blocked_by_similarity_regression = False
    from planner_runtime import load_capability_effectiveness_ledger

    prior_capability_effectiveness_ledger = load_capability_effectiveness_ledger(capability_ledger)
    if not prior_capability_effectiveness_ledger:
        prior_capability_effectiveness_ledger = {"capabilities": {}}

    capability_effectiveness_ledger = {"capabilities": {}}
    build_request = None
    synthesis_source = None

    if decision["action"] == "repair_only":
        result = run_mapping_repair_cycle(
            portfolio_state_path=portfolio_state,
            ledger_path=ledger,
            policy_path=policy,
            top_k=top_k,
        )

    elif decision["action"] == "governed_run":
        class Args:
            pass

        args = Args()
        args.runs = 1
        args.portfolio_state = portfolio_state
        args.ledger = ledger
        args.policy = policy
        args.top_k = top_k
        args.output = output
        args.force = False
        args.exploration_offset = 0
        args.max_actions = None
        args.explain = False
        args.envelope_prefix = "planner_run_envelope"
        args.mapping_override = None
        args.mapping_override_path = None
        args.capability_ledger = capability_ledger
        args.auto_repair_cycle = True

        out = Path(output)
        args.learn_ledger_output = str(
            out.with_name(out.stem + "_learned_ledger.json")
        )

        result = run_governed_loop(args)

        runs = result.get("result", {}).get("evaluation_summary", {}).get("runs", [])
        first_run = runs[0] if runs else {}
        build_request = _resolve_factory_build_request(first_run)
        if build_request is not None:
            synthesis_source = "planner_request"

    if build_request is None:
        build_request = _resolve_gap_synthesis_request(portfolio_state)
        if build_request is not None:
            synthesis_source = "portfolio_gap"

    try:
        if build_request is not None:
            builder_result = build_capability_artifact(
                artifact_kind=build_request["artifact_kind"],
                capability=build_request["capability"],
            )

            if isinstance(result, dict):
                result["builder"] = builder_result

            # ------------------------------------------------------------------
            # Stage 5: MCP reference comparison learning
            # ------------------------------------------------------------------
            if (
                isinstance(builder_result, dict)
                and builder_result.get("status") == "ok"
                and builder_result.get("artifact_kind") == "mcp_server"
            ):
                try:
                    generated_repo = builder_result.get("generated_repo")
                    capability = builder_result.get("capability")

                    reference_repo = get_reference_artifact_path(capability)
                    if not isinstance(reference_repo, str) or not reference_repo:
                        raise ValueError(
                            f"missing reference artifact path for capability: {capability}"
                        )

                    comparison = compare_mcp_servers(
                        generated_repo,
                        reference_repo,
                    )

                    gap_artifact = derive_capability_gaps_from_comparison(
                        comparison,
                    )

                    if isinstance(result, dict):
                        result["reference_mcp_comparison"] = comparison
                        result["reference_mcp_comparison_gaps"] = gap_artifact
                    evolution_plan = plan_capability_evolution(comparison)

                    if isinstance(result, dict):
                        result["capability_evolution_plan"] = evolution_plan

                    evolution_execution = build_evolution_execution(
                        evolution_plan,
                        artifact_kind=builder_result.get("artifact_kind"),
                        current_tools=builder_result.get("tools", []),
                    )

                    if isinstance(result, dict):
                        result["capability_evolution_execution"] = evolution_execution

                    builder_overrides = evolution_execution.get("builder_overrides", {})
                    evolution_execution_metadata = {
                        "builder_overrides_present": bool(builder_overrides),
                        "builder_override_keys": sorted(builder_overrides.keys()),
                        "builder_overrides_applied": False,
                    }
                    prior_similarity_delta = None
                    if build_request is not None:
                        prior_row = prior_capability_effectiveness_ledger.get("capabilities", {}).get(
                            build_request["capability"],
                            {},
                        )
                        if isinstance(prior_row, dict):
                            prior_similarity_delta = prior_row.get("similarity_delta")

                    evolution_blocked_by_similarity_regression = (
                        prior_similarity_delta is not None and float(prior_similarity_delta) < 0
                    )
                    used_evolution = bool(builder_overrides) and not evolution_blocked_by_similarity_regression

                    if builder_overrides and not evolution_blocked_by_similarity_regression:
                        evolution_execution_metadata["builder_overrides_applied"] = True
                        max_evolution_iterations = 3
                        min_similarity_improvement = 0.01
                        evolution_iterations = []
                        previous_iteration_score = comparison.get("similarity", {}).get("overall_score")

                        for iteration_index in range(max_evolution_iterations):
                            evolved_builder_result = build_capability_artifact(
                                artifact_kind=build_request["artifact_kind"],
                                capability=build_request["capability"],
                                **builder_overrides,
                            )

                            iteration_comparison = compare_mcp_servers(
                                evolved_builder_result.get("generated_repo"),
                                reference_repo,
                            )
                            iteration_score = iteration_comparison.get("similarity", {}).get("overall_score")
                            iteration_delta = None
                            if iteration_score is not None and previous_iteration_score is not None:
                                iteration_delta = round(
                                    float(iteration_score) - float(previous_iteration_score),
                                    2,
                                )

                            evolution_iterations.append({
                                "iteration": iteration_index + 1,
                                "builder_result": evolved_builder_result,
                                "comparison": iteration_comparison,
                                "similarity_score": iteration_score,
                                "similarity_delta": iteration_delta,
                            })

                            builder_result = evolved_builder_result
                            comparison = iteration_comparison

                            if (
                                iteration_delta is None
                                or iteration_delta <= 0
                                or iteration_delta < min_similarity_improvement
                            ):
                                break

                            previous_iteration_score = iteration_score
                            evolution_plan = plan_capability_evolution(comparison)
                            evolution_execution = build_evolution_execution(
                                evolution_plan,
                                artifact_kind=builder_result.get("artifact_kind"),
                                current_tools=builder_result.get("tools", []),
                            )
                            builder_overrides = evolution_execution.get("builder_overrides", {})
                            if not builder_overrides:
                                break

                        if isinstance(result, dict):
                            result["evolution_iterations"] = evolution_iterations
                            result["evolved_builder"] = builder_result
                            result["builder"] = builder_result
                            result["reference_mcp_comparison"] = comparison


                except Exception:
                    # Comparison is a learning signal only — never break the cycle
                    pass

            prior_similarity_score = None
            if build_request is not None:
                prior_row = prior_capability_effectiveness_ledger.get("capabilities", {}).get(
                    build_request["capability"],
                    {},
                )
                if isinstance(prior_row, dict):
                    prior_similarity_score = prior_row.get("similarity_score")

            similarity_score = None
            similarity_delta = None
            comparison_artifact = result.get("reference_mcp_comparison") if isinstance(result, dict) else None
            if isinstance(comparison_artifact, dict):
                similarity = comparison_artifact.get("similarity", {})
                if isinstance(similarity, dict):
                    similarity_score = similarity.get("overall_score")
                    if similarity_score is not None and prior_similarity_score is not None:
                        similarity_delta = round(
                            float(similarity_score) - float(prior_similarity_score),
                            2,
                        )

            synthesis_event = {
                "capability": build_request["capability"],
                "artifact_kind": build_request["artifact_kind"],
                "status": "ok",
                "source": synthesis_source,
                "used_evolution": locals().get("used_evolution", False),
            }
            if similarity_score is not None:
                synthesis_event["similarity_score"] = similarity_score
            if prior_similarity_score is not None:
                synthesis_event["previous_similarity_score"] = prior_similarity_score
            if similarity_delta is not None:
                synthesis_event["similarity_delta"] = similarity_delta
            if isinstance(builder_result, dict):
                synthesis_event["status"] = builder_result.get("status", "ok")
                generated_repo = builder_result.get("generated_repo")
                if generated_repo is not None:
                    synthesis_event["generated_repo"] = generated_repo

            if isinstance(result, dict):
                result["synthesis_event"] = synthesis_event
                if "evolution_execution_metadata" in locals():
                    result["evolution_execution_metadata"] = evolution_execution_metadata
                result["evolution_blocked_by_similarity_regression"] = (
                    evolution_blocked_by_similarity_regression
                )
                if evolution_blocked_by_similarity_regression:
                    result["evolution_regression_signal"] = {
                        "prior_similarity_delta": prior_similarity_delta
                    }
                if similarity_score is not None:
                    similarity_progression = {
                        "current_score": similarity_score,
                    }
                    if prior_similarity_score is not None:
                        similarity_progression["previous_score"] = prior_similarity_score
                    if similarity_delta is not None:
                        similarity_progression["delta"] = similarity_delta
                    result["similarity_progression"] = similarity_progression

            capability_effectiveness_ledger = record_normalized_synthesis_event(
                capability_effectiveness_ledger,
                synthesis_event,
            )

        else:
            synthesis_event = {
                "status": "no_op",
                "source": "none",
                "capability": "none",
                "artifact_kind": "none",
            }
            if isinstance(result, dict):
                result["synthesis_event"] = synthesis_event
            capability_effectiveness_ledger = record_normalized_synthesis_event(
                capability_effectiveness_ledger,
                synthesis_event,
            )

    except Exception as exc:
        if isinstance(result, dict):
            result["builder_error"] = str(exc)
        if build_request is not None:
            synthesis_event = {
                "capability": build_request["capability"],
                "artifact_kind": build_request["artifact_kind"],
                "status": "error",
                "source": synthesis_source,
            }
            if isinstance(result, dict):
                result["synthesis_event"] = synthesis_event
            capability_effectiveness_ledger = record_normalized_synthesis_event(
                capability_effectiveness_ledger,
                synthesis_event,
            )

    artifact = {
        "decision": decision,
        "inputs": {
            "portfolio_state": portfolio_state,
            "ledger": ledger,
            "capability_ledger": capability_ledger,
            "policy": policy,
            "top_k": top_k,
        },
        "evaluation": evaluation,
        "cycle_result": result,
        "capability_effectiveness_ledger": locals().get(
            "capability_effectiveness_ledger",
            {"capabilities": {}},
        ),
        "status": "completed",
    }

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return artifact
