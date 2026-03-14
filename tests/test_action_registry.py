# SPDX-License-Identifier: MIT
"""Regression tests for deterministic action registry helpers."""

from src.mcp_governance_orchestrator.action_registry import (
    build_capability_gap_actions,
)


def test_build_capability_gap_actions_prefers_registry_builder_action():
    actions = build_capability_gap_actions(
        [
            {
                "capability": "github_repository_management",
                "artifact_kind": "mcp_server",
            }
        ]
    )

    assert actions == [
        {
            "action_id": "build-github_repository_management",
            "action_type": "build_mcp_server",
            "priority": 0.60,
            "reason": "missing github_repository_management capability",
            "eligible": True,
            "blocked_by": [],
            "task_binding": {
                "task_id": "build_mcp_server",
                "args": {
                    "capability": "github_repository_management",
                },
            },
            "repo_id": "",
        }
    ]


def test_build_capability_gap_actions_falls_back_to_artifact_kind_mapping():
    actions = build_capability_gap_actions(
        [
            {
                "capability": "unknown_capability",
                "artifact_kind": "data_connector",
            }
        ]
    )

    assert actions == [
        {
            "action_id": "build-unknown_capability",
            "action_type": "build_capability_artifact",
            "priority": 0.60,
            "reason": "missing unknown_capability capability",
            "eligible": True,
            "blocked_by": [],
            "task_binding": {
                "task_id": "build_capability_artifact",
                "args": {
                    "capability": "unknown_capability",
                    "artifact_kind": "data_connector",
                },
            },
            "repo_id": "",
        }
    ]


def test_build_capability_gap_actions_orders_deterministically():
    actions = build_capability_gap_actions(
        [
            {
                "capability": "snowflake_data_access",
                "artifact_kind": "data_connector",
            },
            {
                "capability": "github_repository_management",
                "artifact_kind": "mcp_server",
            },
        ],
        priority=0.75,
        repo_id="portfolio",
    )

    assert actions == [
        {
            "action_id": "build-github_repository_management",
            "action_type": "build_mcp_server",
            "priority": 0.75,
            "reason": "missing github_repository_management capability",
            "eligible": True,
            "blocked_by": [],
            "task_binding": {
                "task_id": "build_mcp_server",
                "args": {
                    "capability": "github_repository_management",
                },
            },
            "repo_id": "portfolio",
        },
        {
            "action_id": "build-snowflake_data_access",
            "action_type": "build_capability_artifact",
            "priority": 0.75,
            "reason": "missing snowflake_data_access capability",
            "eligible": True,
            "blocked_by": [],
            "task_binding": {
                "task_id": "build_capability_artifact",
                "args": {
                    "capability": "snowflake_data_access",
                    "artifact_kind": "data_connector",
                },
            },
            "repo_id": "portfolio",
        },
    ]
