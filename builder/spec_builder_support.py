# SPDX-License-Identifier: MIT
"""Shared capability-spec helpers for deterministic artifact builders."""

from pathlib import Path

from src.mcp_governance_orchestrator.capability_spec_registry import get_capability_spec


REPO_ROOT = Path(__file__).resolve().parents[1]


def require_capability_spec(capability, expected_artifact_kind):
    spec = get_capability_spec(capability)
    if spec is None:
        raise ValueError(f"unknown capability: {capability}")
    if spec["artifact_kind"] != expected_artifact_kind:
        raise ValueError(
            f"capability {capability} is not mapped to artifact kind {expected_artifact_kind}"
        )
    return spec


def default_generated_repo_name(spec):
    return f"generated_{spec['artifact_kind']}_{spec['slug']}" 

