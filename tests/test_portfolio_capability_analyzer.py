# SPDX-License-Identifier: MIT
"""Regression tests for deterministic portfolio capability gap analyzer."""

from src.mcp_governance_orchestrator.portfolio_capability_analyzer import (
    analyze_portfolio_capability_gaps,
)


def test_returns_empty_for_non_dict_state():
    assert analyze_portfolio_capability_gaps([]) == []


def test_returns_empty_when_capability_gaps_missing():
    assert analyze_portfolio_capability_gaps({"repos": []}) == []


def test_returns_empty_when_capability_gaps_not_list():
    assert analyze_portfolio_capability_gaps({"capability_gaps": "not-a-list"}) == []


def test_ignores_unknown_and_malformed_capabilities():
    state = {
        "capability_gaps": [
            "unknown_capability",
            "",
            None,
            123,
        ]
    }

    assert analyze_portfolio_capability_gaps(state) == []


def test_normalizes_known_capability_to_capability_and_artifact_kind():
    state = {
        "capability_gaps": [
            "github_repository_management",
        ]
    }

    assert analyze_portfolio_capability_gaps(state) == [
        {
            "capability": "github_repository_management",
            "artifact_kind": "mcp_server",
        }
    ]


def test_orders_known_capabilities_deterministically_by_capability_name():
    state = {
        "capability_gaps": [
            "snowflake_data_access",
            "github_repository_management",
            "slack_workspace_access",
        ]
    }

    assert analyze_portfolio_capability_gaps(state) == [
        {
            "capability": "github_repository_management",
            "artifact_kind": "mcp_server",
        },
        {
            "capability": "slack_workspace_access",
            "artifact_kind": "agent_adapter",
        },
        {
            "capability": "snowflake_data_access",
            "artifact_kind": "data_connector",
        },
    ]


def test_existing_capability_artifact_suppresses_gap_action():
    state = {
        "capability_gaps": ["github_repository_management"],
        "capability_artifacts": {
            "github_repository_management": {
                "artifact_kind": "mcp_server",
                "latest_artifact": "generated_mcp_server_github",
                "revision": 2,
            }
        },
    }

    assert analyze_portfolio_capability_gaps(state) == []


def test_capability_gap_generated_when_artifact_not_present():
    state = {
        "capability_gaps": ["github_repository_management"],
        "capability_artifacts": {},
    }

    assert analyze_portfolio_capability_gaps(state) == [
        {
            "capability": "github_repository_management",
            "artifact_kind": "mcp_server",
        }
    ]
