# SPDX-License-Identifier: MIT
"""Deterministic capability registry for governed factory routing metadata."""

from __future__ import annotations

from typing import Any, Dict

from .capability_spec_registry import get_capability_spec


_CAPABILITY_REGISTRY: Dict[str, Dict[str, Any]] = {
    "github_repository_management": {
        "builder_action": "build_mcp_server",
        "reference_artifact_path": "reference_mcp_github_repository_management",
    },
    "slack_workspace_access": {
        "builder_action": "build_capability_artifact",
        "reference_artifact_path": "reference_mcp_slack_workspace_access",
    },
    "snowflake_data_access": {
        "builder_action": "build_capability_artifact",
        "reference_artifact_path": "reference_mcp_snowflake_data_access",
    },
    "postgres_data_access": {
        "builder_action": "build_capability_artifact",
        "reference_artifact_path": "reference_mcp_postgres_data_access",
    },
}


def get_capability_registry() -> Dict[str, Dict[str, Any]]:
    """Return a deterministic copy of the capability registry."""
    return {
        capability: dict(metadata)
        for capability, metadata in sorted(_CAPABILITY_REGISTRY.items())
    }


def get_capability_registration(capability: str) -> Dict[str, Any] | None:
    """Return routing metadata for one capability, if registered."""
    metadata = _CAPABILITY_REGISTRY.get(capability)
    return dict(metadata) if isinstance(metadata, dict) else None


def get_builder_action(capability: str) -> str | None:
    """Return the canonical builder action for a capability."""
    metadata = get_capability_registration(capability)
    if not isinstance(metadata, dict):
        return None
    action = metadata.get("builder_action")
    return action if isinstance(action, str) and action else None


def get_reference_artifact_path(capability: str) -> str | None:
    """Return the canonical reference artifact path for a capability."""
    metadata = get_capability_registration(capability)
    if not isinstance(metadata, dict):
        return None
    path = metadata.get("reference_artifact_path")
    return path if isinstance(path, str) and path else None


def artifact_kind_for_capability(capability: str) -> str | None:
    """Return the canonical artifact kind for a capability."""
    spec = get_capability_spec(capability)
    if not isinstance(spec, dict):
        return None
    artifact_kind = spec.get("artifact_kind")
    return artifact_kind if isinstance(artifact_kind, str) and artifact_kind else None
