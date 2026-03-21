# SPDX-License-Identifier: MIT
"""Aggregate capability effectiveness from cycle history artifacts.

Reads a JSON file containing a top-level "cycles" list, where each cycle may
contain a "capability_effectiveness_ledger" with a "capabilities" mapping.
Writes a deterministic aggregated capability_effectiveness_ledger.json.

Usage:
    python3 scripts/update_capability_effectiveness_from_cycles.py \
        --cycle-history cycle_history_with_capabilities.json \
        --output capability_effectiveness_ledger.json

Exit codes:
    0  — ledger written
    1  — error (unreadable or invalid input)
"""

import argparse
import json
import sys
from pathlib import Path

from mcp_governance_orchestrator.learning_ledger import (
    write_json_deterministic,
    merge_counter_ledger,
)


def _aggregate(cycles):
    """Return an aggregated capabilities dict from *cycles*."""
    capabilities = {}

    for cycle in cycles:
        if not isinstance(cycle, dict):
            continue

        cycle_result = cycle.get("cycle_result") or {}
        synthesis_event = cycle_result.get("synthesis_event") or {}

        if isinstance(synthesis_event, dict) and synthesis_event:
            capability = synthesis_event.get("capability")
            artifact_kind = synthesis_event.get("artifact_kind")
            status = synthesis_event.get("status")
            source = synthesis_event.get("source")

            if capability and artifact_kind and status and status != "no_op" and source:
                used_evolution = bool(synthesis_event.get("used_evolution", False))
                cap_entry = {
                    "artifact_kind": artifact_kind,
                    "failed_syntheses": 0 if status == "ok" else 1,
                    "successful_evolved_syntheses": 1 if (status == "ok" and used_evolution) else 0,
                    "successful_syntheses": 1 if status == "ok" else 0,
                    "total_syntheses": 1,
                    "last_synthesis_source": source,
                    "last_synthesis_status": status,
                    "last_synthesis_used_evolution": used_evolution,
                }
                if synthesis_event.get("similarity_score") is not None:
                    cap_entry["similarity_score"] = synthesis_event["similarity_score"]
                if synthesis_event.get("previous_similarity_score") is not None:
                    cap_entry["previous_similarity_score"] = synthesis_event["previous_similarity_score"]
                if synthesis_event.get("similarity_delta") is not None:
                    cap_entry["similarity_delta"] = synthesis_event["similarity_delta"]
                if synthesis_event.get("comparison_status") is not None:
                    cap_entry["last_comparison_status"] = synthesis_event["comparison_status"]
                cycle_capabilities = {capability: cap_entry}

                capabilities = merge_counter_ledger(
                    capabilities,
                    cycle_capabilities,
                    counter_fields=[
                        "failed_syntheses",
                        "successful_evolved_syntheses",
                        "successful_syntheses",
                        "total_syntheses",
                    ],
                    last_fields=[
                        "last_synthesis_source",
                        "last_synthesis_status",
                        "last_synthesis_used_evolution",
                        "similarity_score",
                        "previous_similarity_score",
                        "similarity_delta",
                        "last_comparison_status",
                    ],
                )
                continue

        ledger = cycle.get("capability_effectiveness_ledger") or {}
        cycle_capabilities = ledger.get("capabilities") or {}
        if not isinstance(cycle_capabilities, dict):
            continue

        capabilities = merge_counter_ledger(
            capabilities,
            cycle_capabilities,
            counter_fields=[
                "failed_syntheses",
                "successful_evolved_syntheses",
                "successful_syntheses",
                "total_syntheses",
            ],
            last_fields=[
                "last_synthesis_source",
                "last_synthesis_status",
                "last_synthesis_used_evolution",
                "similarity_score",
                "previous_similarity_score",
                "similarity_delta",
                "last_comparison_status",
            ],
        )

    return capabilities

def update_capability_effectiveness_from_cycles(cycle_history_path, output_path):
    """Aggregate cycle history into a capability effectiveness ledger."""
    try:
        history = json.loads(Path(cycle_history_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot read cycle history: {exc}\n")
        return 1

    cycles = history.get("cycles")
    if not isinstance(cycles, list):
        sys.stderr.write("error: cycle history must contain 'cycles' as a list\n")
        return 1

    capabilities = _aggregate(cycles)
    write_json_deterministic(output_path, {"capabilities": capabilities})
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Aggregate capability effectiveness from cycle history.",
        add_help=True,
    )
    parser.add_argument("--cycle-history", required=True, metavar="FILE",
                        help="Path to cycle-history JSON containing a top-level cycles list.")
    parser.add_argument("--output", required=True, metavar="FILE",
                        help="Output path for capability_effectiveness_ledger.json.")

    args = parser.parse_args(argv)
    sys.exit(update_capability_effectiveness_from_cycles(
        args.cycle_history, args.output
    ))


if __name__ == "__main__":
    main()
