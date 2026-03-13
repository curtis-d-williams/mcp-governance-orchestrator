# SPDX-License-Identifier: MIT
"""
Canonical orchestration pipeline for a single MCP factory cycle.
"""

import io
from contextlib import redirect_stdout
from pathlib import Path
import json

from builder.artifact_registry import build_capability_artifact
from src.mcp_governance_orchestrator.capability_registry import artifact_kind_for_capability
from src.mcp_governance_orchestrator.capability_effectiveness_ledger import record_synthesis_event


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
    if not capability_gaps:
        return None

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
        args.auto_repair_cycle = True

        out = Path(output)
        args.learn_ledger_output = str(
            out.with_name(out.stem + "_learned_ledger.json")
        )

        result = run_governed_loop(args)

        # ------------------------------------------------------------------
        # Builder dispatch (factory artifact generation)
        # ------------------------------------------------------------------

        capability_effectiveness_ledger = {"capabilities": {}}

        try:
            runs = result.get("result", {}).get("evaluation_summary", {}).get("runs", [])
            first_run = runs[0] if runs else {}

            build_request = _resolve_factory_build_request(first_run)
            synthesis_source = "planner_request"

            if build_request is None:
                build_request = _resolve_gap_synthesis_request(portfolio_state)
                synthesis_source = "portfolio_gap"

            if build_request is not None:
                builder_result = build_capability_artifact(
                    artifact_kind=build_request["artifact_kind"],
                    capability=build_request["capability"],
                )

                if isinstance(result, dict):
                    result["builder"] = builder_result

                synthesis_status = "ok"
                synthesis_event = {
                    "capability": build_request["capability"],
                    "artifact_kind": build_request["artifact_kind"],
                    "status": "ok",
                    "source": synthesis_source,
                }
                if isinstance(builder_result, dict):
                    synthesis_status = builder_result.get("status", "ok")
                    synthesis_event["status"] = synthesis_status
                    generated_repo = builder_result.get("generated_repo")
                    if generated_repo is not None:
                        synthesis_event["generated_repo"] = generated_repo

                if isinstance(result, dict):
                    result["synthesis_event"] = synthesis_event

                capability_effectiveness_ledger = record_synthesis_event(
                    capability_effectiveness_ledger,
                    capability=build_request["capability"],
                    artifact_kind=build_request["artifact_kind"],
                    synthesis_source=synthesis_source,
                    synthesis_status=synthesis_status,
                )

        except Exception as exc:
            if isinstance(result, dict):
                result["builder_error"] = str(exc)
            if build_request is not None:
                if isinstance(result, dict):
                    result["synthesis_event"] = {
                        "capability": build_request["capability"],
                        "artifact_kind": build_request["artifact_kind"],
                        "status": "error",
                        "source": synthesis_source,
                    }
                capability_effectiveness_ledger = record_synthesis_event(
                    capability_effectiveness_ledger,
                    capability=build_request["capability"],
                    artifact_kind=build_request["artifact_kind"],
                    synthesis_source=synthesis_source,
                    synthesis_status="error",
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
