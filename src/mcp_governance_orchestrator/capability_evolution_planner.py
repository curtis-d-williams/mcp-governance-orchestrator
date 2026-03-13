# SPDX-License-Identifier: MIT
"""
Capability Evolution Planner.

Transforms reference MCP comparison results into deterministic
capability evolution actions.
"""

from typing import Dict, Any, List

def plan_capability_evolution(comparison: Dict[str, Any]) -> Dict[str, Any]:
    actions: List[Dict[str, Any]] = []

    tool_surface = comparison.get("tool_surface", {})
    missing_tools = sorted(tool_surface.get("missing_tools", []))

    capability_surface = comparison.get("capability_surface", {})
    missing_enabled = sorted(capability_surface.get("missing_enabled", []))

    testability = comparison.get("testability", {})
    coverage = testability.get("coverage_ratio")

    # deterministic ordering

    for tool in missing_tools:
        actions.append(
            {
                "type": "add_tool",
                "tool": tool,
            }
        )

    for feature in missing_enabled:
        actions.append(
            {
                "type": "enable_feature",
                "feature": feature,
            }
        )

    if coverage is not None and coverage < 0.8:
        actions.append(
            {
                "type": "increase_test_coverage",
            }
        )

    return {
        "evolution_actions": actions,
        "action_count": len(actions),
    }
