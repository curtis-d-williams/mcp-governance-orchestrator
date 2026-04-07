# SPDX-License-Identifier: MIT
"""
Capability Evolution Planner.

Transforms reference MCP comparison results into deterministic
capability evolution actions.
"""

from typing import Dict, Any, List, Optional

def plan_capability_evolution(
    comparison: Dict[str, Any],
    capability_ledger: Optional[Dict[str, Any]] = None,
    capability: Optional[str] = None,
) -> Dict[str, Any]:
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

    ledger_suppressed = False
    if capability_ledger is not None and capability is not None:
        ledger_row = capability_ledger.get("capabilities", {}).get(capability, {})
        similarity_delta = ledger_row.get("similarity_delta")
        if similarity_delta is not None and float(similarity_delta) < 0:
            actions = [a for a in actions if a.get("type") not in ("add_tool", "enable_feature")]
            ledger_suppressed = True

    return {
        "evolution_actions": actions,
        "action_count": len(actions),
        "ledger_suppressed": ledger_suppressed,
    }
