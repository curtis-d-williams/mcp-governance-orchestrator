# SPDX-License-Identifier: MIT
"""
Deterministically execute a capability evolution plan.

Responsibilities:
- read capability_evolution_plan JSON
- translate supported actions into builder overrides
- rebuild artifact with deterministic overrides
- compare rebuilt artifact against reference MCP
- update capability effectiveness ledger in-memory
- optionally persist a deterministic execution artifact

Fail closed on malformed inputs, unknown reference targets, or rebuild/compare errors.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from builder.artifact_registry import build_capability_artifact
from src.mcp_governance_orchestrator.capability_effectiveness_ledger import (
    record_normalized_synthesis_event,
)
from src.mcp_governance_orchestrator.capability_evolution_executor import (
    build_evolution_execution,
)
from src.mcp_governance_orchestrator.capability_registry import (
    get_reference_artifact_path,
)
from scripts.compare_mcp_servers import compare_mcp_servers


_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_json(path, label):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"failed to load {label}: {path}") from exc


def _write_json(path, payload):
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalize_plan(plan_artifact):
    if not isinstance(plan_artifact, dict):
        raise ValueError("capability evolution plan artifact must be a JSON object")

    if "evolution_actions" in plan_artifact:
        plan = plan_artifact
    else:
        plan = plan_artifact.get("capability_evolution_plan")

    if not isinstance(plan, dict):
        raise ValueError("missing capability_evolution_plan")
    if not isinstance(plan.get("evolution_actions"), list):
        raise ValueError("capability_evolution_plan.evolution_actions must be a list")

    return plan


def run_capability_evolution_plan(
    *,
    plan_path,
    artifact_kind,
    capability,
    current_tools=None,
    ledger_path=None,
    source="planner_request",
    output_path=None,
):
    plan_artifact = _load_json(plan_path, "capability evolution plan")
    evolution_plan = _normalize_plan(plan_artifact)

    execution = build_evolution_execution(
        evolution_plan,
        artifact_kind=artifact_kind,
        current_tools=current_tools or [],
    )

    builder_overrides = execution.get("builder_overrides", {})
    if not isinstance(builder_overrides, dict):
        raise ValueError("builder_overrides must be a dict")
    if not builder_overrides:
        raise ValueError("no deterministic builder overrides produced from evolution plan")

    reference_path = get_reference_artifact_path(capability)
    if not isinstance(reference_path, str) or not reference_path:
        raise ValueError(f"missing reference artifact path for capability: {capability}")

    prior_ledger = {"capabilities": {}}
    if ledger_path:
        prior_ledger = _load_json(ledger_path, "capability effectiveness ledger")
        if not isinstance(prior_ledger, dict):
            raise ValueError("capability effectiveness ledger must be a JSON object")

    prior_row = prior_ledger.get("capabilities", {}).get(capability, {})
    previous_similarity_score = None
    if isinstance(prior_row, dict):
        previous_similarity_score = prior_row.get("similarity_score")

    builder_result = build_capability_artifact(
        artifact_kind=artifact_kind,
        capability=capability,
        **builder_overrides,
    )
    if not isinstance(builder_result, dict):
        raise ValueError("builder returned non-dict result")

    status = builder_result.get("status", "error")
    if status != "ok":
        raise ValueError(f"builder returned non-ok status: {status}")

    generated_repo = builder_result.get("generated_repo")
    if not isinstance(generated_repo, str) or not generated_repo:
        raise ValueError("builder result missing generated_repo")

    comparison = compare_mcp_servers(
        generated_repo,
        reference_path,
    )

    similarity_score = None
    similarity_delta = None
    if isinstance(comparison, dict):
        similarity = comparison.get("similarity", {})
        if isinstance(similarity, dict):
            similarity_score = similarity.get("overall_score")
            if similarity_score is not None and previous_similarity_score is not None:
                similarity_delta = round(
                    float(similarity_score) - float(previous_similarity_score),
                    2,
                )

    synthesis_event = {
        "capability": capability,
        "artifact_kind": artifact_kind,
        "status": status,
        "source": source,
        "used_evolution": True,
        "generated_repo": generated_repo,
    }
    if similarity_score is not None:
        synthesis_event["similarity_score"] = similarity_score
    if previous_similarity_score is not None:
        synthesis_event["previous_similarity_score"] = previous_similarity_score
    if similarity_delta is not None:
        synthesis_event["similarity_delta"] = similarity_delta

    updated_ledger = record_normalized_synthesis_event(
        prior_ledger,
        synthesis_event,
    )

    artifact = {
        "capability": capability,
        "artifact_kind": artifact_kind,
        "capability_evolution_plan": evolution_plan,
        "capability_evolution_execution": execution,
        "builder": builder_result,
        "reference_mcp_comparison": comparison,
        "synthesis_event": synthesis_event,
        "capability_effectiveness_ledger": updated_ledger,
    }

    if output_path is not None:
        _write_json(output_path, artifact)

    return artifact


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run deterministic capability evolution execution."
    )
    parser.add_argument("--plan", required=True, help="Path to capability evolution plan JSON.")
    parser.add_argument("--artifact-kind", required=True, help="Artifact kind to rebuild.")
    parser.add_argument("--capability", required=True, help="Capability to rebuild.")
    parser.add_argument(
        "--current-tools",
        default=None,
        help="Optional JSON file containing current tool list or object with a tools field.",
    )
    parser.add_argument(
        "--capability-ledger",
        default=None,
        help="Optional capability effectiveness ledger JSON.",
    )
    parser.add_argument(
        "--source",
        default="planner_request",
        help="Synthesis source label for the normalized synthesis event.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output artifact path.",
    )
    args = parser.parse_args(argv)

    current_tools = []
    if args.current_tools:
        current_tools_artifact = _load_json(args.current_tools, "current tools")
        if isinstance(current_tools_artifact, list):
            current_tools = current_tools_artifact
        elif isinstance(current_tools_artifact, dict):
            current_tools = current_tools_artifact.get("tools", [])
        else:
            raise ValueError("current tools input must be a list or object")

    artifact = run_capability_evolution_plan(
        plan_path=args.plan,
        artifact_kind=args.artifact_kind,
        capability=args.capability,
        current_tools=current_tools,
        ledger_path=args.capability_ledger,
        source=args.source,
        output_path=args.output,
    )

    print(json.dumps(artifact, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
