# SPDX-License-Identifier: MIT
"""
Canonical orchestration pipeline for a single MCP factory cycle.
"""

import io
from contextlib import redirect_stdout
from pathlib import Path
import json

from builder.artifact_registry import build_capability_artifact
from builder.mcp_builder import build_mcp_server


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
    - legacy action_type == "build_mcp_server" dispatches to build_mcp_server(...)
    - generic action_type == "build_capability_artifact" dispatches to
      build_capability_artifact(...)
    """

    selected_actions = first_run.get("selected_actions", [])
    selection_detail = first_run.get("selection_detail", {})
    ranked_action_window = selection_detail.get("ranked_action_window", [])
    ranked_action_window_detail = selection_detail.get(
        "ranked_action_window_detail",
        [],
    )

    should_build_generic = (
        "build_capability_artifact" in selected_actions
        or "build_capability_artifact" in ranked_action_window
    )
    should_build_legacy_mcp = (
        "build_mcp_server" in selected_actions
        or "build_mcp_server" in ranked_action_window
    )

    if not should_build_generic and not should_build_legacy_mcp:
        return None

    request = {
        "dispatch": "legacy_mcp" if should_build_legacy_mcp else "generic",
        "artifact_kind": "mcp_server",
        "capability": "github_repository_management",
    }

    for action in ranked_action_window_detail:
        action_type = action.get("action_type")
        args = action.get("task_binding", {}).get("args", {})

        if action_type == "build_capability_artifact":
            request["dispatch"] = "generic"
            request["artifact_kind"] = args.get(
                "artifact_kind",
                request["artifact_kind"],
            )
            request["capability"] = args.get(
                "capability",
                request["capability"],
            )
            return request

        if action_type == "build_mcp_server":
            request["dispatch"] = "legacy_mcp"
            request["artifact_kind"] = "mcp_server"
            request["capability"] = args.get(
                "capability",
                request["capability"],
            )
            return request

    return request

def run_factory_cycle(
    *,
    portfolio_state,
    ledger,
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

        try:
            runs = result.get("result", {}).get("evaluation_summary", {}).get("runs", [])
            first_run = runs[0] if runs else {}

            build_request = _resolve_factory_build_request(first_run)

            if build_request is not None:
                if build_request["dispatch"] == "legacy_mcp":
                    builder_result = build_mcp_server(
                        capability=build_request["capability"]
                    )
                else:
                    builder_result = build_capability_artifact(
                        artifact_kind=build_request["artifact_kind"],
                        capability=build_request["capability"],
                    )

                if isinstance(result, dict):
                    result["builder"] = builder_result

        except Exception as exc:
            if isinstance(result, dict):
                result["builder_error"] = str(exc)

    artifact = {
        "decision": decision,
        "inputs": {
            "portfolio_state": portfolio_state,
            "ledger": ledger,
            "policy": policy,
            "top_k": top_k,
        },
        "evaluation": evaluation,
        "cycle_result": result,
        "status": "completed",
    }

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return artifact
