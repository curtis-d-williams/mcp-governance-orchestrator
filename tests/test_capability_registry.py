# SPDX-License-Identifier: MIT
"""Regression tests for deterministic capability registry helpers."""

from src.mcp_governance_orchestrator.capability_registry import (
    get_builder_action,
    get_capability_registration,
    get_capability_registry,
    get_reference_artifact_path,
)


def test_get_capability_registry_returns_sorted_copy():
    registry = get_capability_registry()

    assert list(registry.keys()) == [
        "github_repository_management",
        "postgres_data_access",
        "slack_workspace_access",
        "snowflake_data_access",
    ]

    registry["github_repository_management"]["builder_action"] = "mutated"

    fresh = get_capability_registry()
    assert fresh["github_repository_management"]["builder_action"] == "build_mcp_server"


def test_get_capability_registration_returns_copy_for_known_capability():
    registration = get_capability_registration("github_repository_management")

    assert registration == {
        "builder_action": "build_mcp_server",
        "reference_artifact_path": "reference_mcp_github_repository_management",
    }

    registration["builder_action"] = "mutated"

    fresh = get_capability_registration("github_repository_management")
    assert fresh["builder_action"] == "build_mcp_server"


def test_get_capability_registration_returns_none_for_unknown_capability():
    assert get_capability_registration("unknown_capability") is None


def test_get_builder_action_returns_expected_action():
    assert get_builder_action("github_repository_management") == "build_mcp_server"
    assert get_builder_action("slack_workspace_access") == "build_capability_artifact"
    assert get_builder_action("unknown_capability") is None


def test_get_reference_artifact_path_returns_expected_path():
    assert (
        get_reference_artifact_path("github_repository_management")
        == "reference_mcp_github_repository_management"
    )
    assert (
        get_reference_artifact_path("snowflake_data_access")
        == "reference_mcp_snowflake_data_access"
    )
    assert get_reference_artifact_path("unknown_capability") is None
