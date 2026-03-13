# SPDX-License-Identifier: MIT
"""Regression tests for deterministic capability evolution execution."""

from src.mcp_governance_orchestrator.capability_evolution_executor import (
    build_evolution_execution,
)


def test_build_evolution_execution_builds_mcp_tool_overrides():
    execution = build_evolution_execution(
        {
            "evolution_actions": [
                {"type": "add_tool", "tool": "get_repository"},
                {"type": "add_tool", "tool": "create_issue"},
                {"type": "add_tool", "tool": "get_repository"},
                {"type": "enable_feature", "feature": "supports_feature_flags"},
                {"type": "increase_test_coverage"},
            ]
        },
        artifact_kind="mcp_server",
        current_tools=["list_repositories", "get_repository"],
    )

    assert execution == {
        "builder_overrides": {
            "tools": [
                "list_repositories",
                "get_repository",
                "create_issue",
            ]
        },
        "executable_actions": [
            {"type": "add_tool", "tool": "get_repository"},
            {"type": "add_tool", "tool": "create_issue"},
            {"type": "add_tool", "tool": "get_repository"},
        ],
        "deferred_actions": [
            {"type": "enable_feature", "feature": "supports_feature_flags"},
            {"type": "increase_test_coverage"},
        ],
        "executed_action_count": 3,
        "deferred_action_count": 2,
    }


def test_build_evolution_execution_ignores_add_tool_for_non_mcp_artifacts():
    execution = build_evolution_execution(
        {
            "evolution_actions": [
                {"type": "add_tool", "tool": "get_repository"},
                {"type": "increase_test_coverage"},
            ]
        },
        artifact_kind="data_connector",
        current_tools=["health_check"],
    )

    assert execution == {
        "builder_overrides": {},
        "executable_actions": [],
        "deferred_actions": [
            {"type": "add_tool", "tool": "get_repository"},
            {"type": "increase_test_coverage"},
        ],
        "executed_action_count": 0,
        "deferred_action_count": 2,
    }
