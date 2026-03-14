# SPDX-License-Identifier: MIT
"""Regression tests for deterministic capability evolution planning."""

from src.mcp_governance_orchestrator.capability_evolution_planner import (
    plan_capability_evolution,
)


def test_plan_capability_evolution_sorts_actions_deterministically():
    plan = plan_capability_evolution(
        {
            "tool_surface": {
                "missing_tools": ["z_tool", "a_tool", "m_tool"],
            },
            "capability_surface": {
                "missing_enabled": ["z_feature", "a_feature"],
            },
            "testability": {
                "coverage_ratio": 0.25,
            },
        }
    )

    assert plan == {
        "evolution_actions": [
            {"type": "add_tool", "tool": "a_tool"},
            {"type": "add_tool", "tool": "m_tool"},
            {"type": "add_tool", "tool": "z_tool"},
            {"type": "enable_feature", "feature": "a_feature"},
            {"type": "enable_feature", "feature": "z_feature"},
            {"type": "increase_test_coverage"},
        ],
        "action_count": 6,
    }


def test_plan_capability_evolution_omits_test_coverage_when_threshold_met():
    plan = plan_capability_evolution(
        {
            "tool_surface": {
                "missing_tools": [],
            },
            "capability_surface": {
                "missing_enabled": [],
            },
            "testability": {
                "coverage_ratio": 0.8,
            },
        }
    )

    assert plan == {
        "evolution_actions": [],
        "action_count": 0,
    }
