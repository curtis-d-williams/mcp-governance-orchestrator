# SPDX-License-Identifier: MIT
"""Deterministic action registry for synthesized planner actions.

This module converts normalized capability gap records into canonical
planner actions without invoking planner, builder, or I/O logic.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .capability_registry import get_builder_action


def build_capability_gap_actions(
    gap_records: List[Dict[str, Any]],
    *,
    priority: float = 0.60,
    repo_id: str = "",
) -> List[Dict[str, Any]]:
    """Return canonical planner actions for capability gap records.

    Mapping:
    - prefer registry builder_action when available
    - otherwise fall back to:
      - mcp_server      -> build_mcp_server
      - all other kinds -> build_capability_artifact

    Args:
        gap_records: Normalized records from portfolio_capability_analyzer.
        priority: Deterministic default priority for synthesized actions.
        repo_id: Optional synthetic repo scope for portfolio-level actions.

    Returns:
        Deterministically ordered planner action dicts compatible with
        scripts/list_portfolio_actions.py and planner_runtime.py.
    """
    if not isinstance(gap_records, list):
        return []

    actions: List[Dict[str, Any]] = []
    _seen_capabilities = set()

    for record in gap_records:
        if not isinstance(record, dict):
            continue

        capability = record.get("capability")
        artifact_kind = record.get("artifact_kind")

        if capability in _seen_capabilities:
            continue
        if not isinstance(capability, str) or not capability:
            continue
        if not isinstance(artifact_kind, str) or not artifact_kind:
            continue

        action_type = get_builder_action(capability)
        if not isinstance(action_type, str) or not action_type:
            action_type = (
                "build_mcp_server"
                if artifact_kind == "mcp_server"
                else "build_capability_artifact"
            )

        task_args = {"capability": capability}
        if action_type == "build_capability_artifact":
            task_args["artifact_kind"] = artifact_kind

        _seen_capabilities.add(capability)

        actions.append(
            {
                "action_id": f"build-{capability}",
                "action_type": action_type,
                "priority": float(priority),
                "reason": f"missing {capability} capability",
                "eligible": True,
                "blocked_by": [],
                "task_binding": {
                    "task_id": action_type,
                    "args": task_args,
                },
                "repo_id": repo_id,
            }
        )

    actions.sort(
        key=lambda a: (
            -a.get("priority", 0.0),
            0 if a.get("action_type") == "build_mcp_server" else 1,
            a.get("action_id", ""),
            a.get("repo_id", ""),
        )
    )
    return actions
