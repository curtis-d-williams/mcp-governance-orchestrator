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
        "ledger_suppressed": False,
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

    assert plan == {"evolution_actions": [], "action_count": 0, "ledger_suppressed": False}


def test_plan_capability_evolution_suppresses_actions_on_negative_similarity_delta():
    ledger = {
        "capabilities": {
            "github": {
                "similarity_delta": -0.05,
                "total_syntheses": 3,
                "successful_syntheses": 2,
            }
        }
    }
    comparison = {
        "tool_surface": {"missing_tools": ["list_repos"]},
        "capability_surface": {"missing_enabled": ["webhooks"]},
        "testability": {"coverage_ratio": 0.5},
    }
    plan = plan_capability_evolution(comparison, capability_ledger=ledger, capability="github")
    action_types = [a["type"] for a in plan["evolution_actions"]]
    assert "add_tool" not in action_types
    assert "enable_feature" not in action_types
    assert plan["ledger_suppressed"] is True


def test_plan_capability_evolution_suppression_retains_coverage_action():
    ledger = {
        "capabilities": {
            "github": {
                "similarity_delta": -0.05,
            }
        }
    }
    comparison = {
        "tool_surface": {"missing_tools": ["list_repos"]},
        "capability_surface": {"missing_enabled": ["webhooks"]},
        "testability": {"coverage_ratio": 0.5},
    }
    plan = plan_capability_evolution(comparison, capability_ledger=ledger, capability="github")
    action_types = [a["type"] for a in plan["evolution_actions"]]
    assert "increase_test_coverage" in action_types
    assert plan["ledger_suppressed"] is True


def test_plan_capability_evolution_does_not_suppress_on_zero_similarity_delta():
    ledger = {
        "capabilities": {
            "github": {
                "similarity_delta": 0.0,
            }
        }
    }
    comparison = {
        "tool_surface": {"missing_tools": ["list_repos"]},
        "capability_surface": {"missing_enabled": []},
        "testability": {},
    }
    plan = plan_capability_evolution(comparison, capability_ledger=ledger, capability="github")
    action_types = [a["type"] for a in plan["evolution_actions"]]
    assert "add_tool" in action_types
    assert plan["ledger_suppressed"] is False


def test_plan_capability_evolution_does_not_suppress_on_positive_similarity_delta():
    ledger = {
        "capabilities": {
            "github": {
                "similarity_delta": 0.08,
            }
        }
    }
    comparison = {
        "tool_surface": {"missing_tools": ["list_repos"]},
        "capability_surface": {"missing_enabled": []},
        "testability": {},
    }
    plan = plan_capability_evolution(comparison, capability_ledger=ledger, capability="github")
    action_types = [a["type"] for a in plan["evolution_actions"]]
    assert "add_tool" in action_types
    assert plan["ledger_suppressed"] is False


def test_plan_capability_evolution_no_ledger_provided_unchanged():
    comparison = {
        "tool_surface": {"missing_tools": ["list_repos"]},
        "capability_surface": {"missing_enabled": ["webhooks"]},
        "testability": {"coverage_ratio": 0.5},
    }
    plan = plan_capability_evolution(comparison)
    action_types = [a["type"] for a in plan["evolution_actions"]]
    assert "add_tool" in action_types
    assert "enable_feature" in action_types
    assert "increase_test_coverage" in action_types
    assert plan["ledger_suppressed"] is False


def test_plan_capability_evolution_capability_not_in_ledger_unchanged():
    ledger = {
        "capabilities": {
            "other_capability": {
                "similarity_delta": -0.05,
            }
        }
    }
    comparison = {
        "tool_surface": {"missing_tools": ["list_repos"]},
        "capability_surface": {"missing_enabled": []},
        "testability": {},
    }
    plan = plan_capability_evolution(comparison, capability_ledger=ledger, capability="github")
    action_types = [a["type"] for a in plan["evolution_actions"]]
    assert "add_tool" in action_types
    assert plan["ledger_suppressed"] is False
