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

from mcp_governance_orchestrator.learning_ledger import write_json_deterministic


def _as_int(value):
    """Return *value* as a non-negative int when possible, else 0."""
    return value if isinstance(value, int) and value >= 0 else 0


def _aggregate(cycles):
    """Return an aggregated capabilities dict from *cycles*."""
    capabilities = {}

    for cycle in cycles:
        if not isinstance(cycle, dict):
            continue

        ledger = cycle.get("capability_effectiveness_ledger") or {}
        cycle_capabilities = ledger.get("capabilities") or {}
        if not isinstance(cycle_capabilities, dict):
            continue

        for capability, incoming in cycle_capabilities.items():
            if not isinstance(incoming, dict):
                continue

            if capability not in capabilities:
                capabilities[capability] = {
                    "artifact_kind": incoming.get("artifact_kind"),
                    "failed_syntheses": 0,
                    "last_synthesis_source": incoming.get("last_synthesis_source"),
                    "last_synthesis_status": incoming.get("last_synthesis_status"),
                    "successful_syntheses": 0,
                    "total_syntheses": 0,
                }

            entry = capabilities[capability]
            entry["artifact_kind"] = incoming.get(
                "artifact_kind",
                entry.get("artifact_kind"),
            )
            entry["failed_syntheses"] += _as_int(incoming.get("failed_syntheses"))
            entry["successful_syntheses"] += _as_int(incoming.get("successful_syntheses"))
            entry["total_syntheses"] += _as_int(incoming.get("total_syntheses"))
            entry["last_synthesis_source"] = incoming.get("last_synthesis_source")
            entry["last_synthesis_status"] = incoming.get("last_synthesis_status")

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
