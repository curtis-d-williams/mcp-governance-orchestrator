# SPDX-License-Identifier: MIT
"""
Deterministic capability evolution executor.

Interprets capability_evolution_plan actions into narrow builder-input
overrides without redesigning builder contracts.
"""

from typing import Any, Dict, List


def _unique_preserve_order(values: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []

    for value in values:
        if not isinstance(value, str):
            continue
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)

    return ordered


def build_evolution_execution(
    evolution_plan: Dict[str, Any],
    *,
    artifact_kind: str,
    current_tools: List[str] | None = None,
) -> Dict[str, Any]:
    """
    Convert supported evolution actions into deterministic builder overrides.

    v1 support:
    - add_tool -> tools override for mcp_server artifacts
    - enable_feature -> features override for mcp_server artifacts
    - increase_test_coverage -> test_expansion override for mcp_server artifacts
    """
    current_tools = list(current_tools or [])
    actions = evolution_plan.get("evolution_actions", [])

    executable_actions: List[Dict[str, Any]] = []
    deferred_actions: List[Dict[str, Any]] = []

    tools = list(current_tools)
    features: List[str] = []
    test_expansion = False

    for action in actions:
        if not isinstance(action, dict):
            continue

        action_type = action.get("type")

        if action_type == "add_tool" and artifact_kind == "mcp_server":
            tool = action.get("tool")
            if isinstance(tool, str):
                tools.append(tool)
                executable_actions.append(action)
            continue

        if action_type == "enable_feature" and artifact_kind == "mcp_server":
            feature = action.get("feature")
            if isinstance(feature, str):
                features.append(feature)
                executable_actions.append(action)
            continue

        if action_type == "increase_test_coverage" and artifact_kind == "mcp_server":
            test_expansion = True
            executable_actions.append(action)
            continue

        deferred_actions.append(action)

    overrides: Dict[str, Any] = {}
    normalized_tools = _unique_preserve_order(tools)
    normalized_features = _unique_preserve_order(features)

    if artifact_kind == "mcp_server" and normalized_tools != _unique_preserve_order(current_tools):
        overrides["tools"] = normalized_tools

    if artifact_kind == "mcp_server" and normalized_features:
        overrides["features"] = normalized_features

    if artifact_kind == "mcp_server" and test_expansion:
        overrides["test_expansion"] = True

    return {
        "builder_overrides": overrides,
        "executable_actions": executable_actions,
        "deferred_actions": deferred_actions,
        "executed_action_count": len(executable_actions),
        "deferred_action_count": len(deferred_actions),
    }
