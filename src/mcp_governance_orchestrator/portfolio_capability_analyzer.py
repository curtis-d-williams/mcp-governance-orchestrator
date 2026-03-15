# SPDX-License-Identifier: MIT
"""Deterministic portfolio capability gap analyzer.

This module converts portfolio_state capability gaps into normalized
records that the planner can convert into build actions.

Design constraints:
- Pure logic (no I/O)
- Deterministic ordering
- Fail closed on malformed inputs
- Does not invoke builders or planner logic
"""

from __future__ import annotations

from typing import Any, Dict, List

from .capability_spec_registry import get_capability_spec

PERSISTENCE_THRESHOLD = 3


def analyze_portfolio_capability_gaps(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return normalized capability gap records.

    Args:
        state: portfolio_state dictionary.

    Returns:
        Deterministically ordered list of capability gap records:

        [
            {
                "capability": "<capability_name>",
                "artifact_kind": "<artifact_kind>"
            }
        ]

    Behavior:
        - Ignores unknown capabilities
        - Ignores malformed capability entries
        - Deterministic ordering by capability name
        - Returns empty list when no gaps exist
    """
    if not isinstance(state, dict):
        return []

    gaps = state.get("capability_gaps")
    if not isinstance(gaps, list):
        return []

    gap_cycles = state.get("capability_gap_cycles", {})
    existing_artifacts = state.get("capability_artifacts", {})
    if not isinstance(existing_artifacts, dict):
        existing_artifacts = {}

    normalized: List[Dict[str, Any]] = []

    for capability in gaps:
        if not isinstance(capability, str) or not capability:
            continue

        if capability in existing_artifacts:
            continue

        cycles = int(gap_cycles.get(capability, PERSISTENCE_THRESHOLD))
        if cycles < PERSISTENCE_THRESHOLD:
            continue

        spec = get_capability_spec(capability)
        if not isinstance(spec, dict):
            continue

        artifact_kind = spec.get("artifact_kind")
        if not isinstance(artifact_kind, str):
            continue

        normalized.append(
            {
                "capability": capability,
                "artifact_kind": artifact_kind,
            }
        )

    normalized.sort(key=lambda r: r["capability"])
    return normalized
