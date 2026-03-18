# SPDX-License-Identifier: MIT
"""Deterministically update the capability-effectiveness ledger from one factory cycle.

Consumes an autonomous factory cycle artifact that may contain a top-level
"capability_effectiveness_ledger" with a "capabilities" mapping, then merges
that per-cycle ledger into a persistent capability_effectiveness_ledger.json.

Behavior:
- preserves existing capability rows unless updated by the incoming cycle
- increments failed/successful/total syntheses cumulatively
- updates artifact_kind, last_synthesis_source, and last_synthesis_status
  to the most recent observed values
- writes deterministic JSON (indent=2, sort_keys=True, trailing newline)
"""

import argparse
import json
from pathlib import Path

from mcp_governance_orchestrator.learning_ledger import (
    empty_ledger,
    load_json_fail_closed,
    merge_counter_ledger,
    write_json_deterministic,
)


def _extract_cycle_capabilities(artifact):
    if not isinstance(artifact, dict):
        return {}
    ledger = artifact.get("capability_effectiveness_ledger") or {}
    capabilities = ledger.get("capabilities") or {}
    return capabilities if isinstance(capabilities, dict) else {}


def update_capability_effectiveness_ledger(ledger_path, cycle_artifact_path, output_path=None):
    ledger = load_json_fail_closed(ledger_path, empty_ledger("capabilities"))
    artifact = load_json_fail_closed(cycle_artifact_path, {})

    capabilities = ledger.get("capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}

    incoming_caps = _extract_cycle_capabilities(artifact)
    capabilities = merge_counter_ledger(
        capabilities,
        incoming_caps,
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

    updates = [
        {
            "capability": capability,
            "artifact_kind": capabilities[capability].get("artifact_kind"),
            "failed_syntheses": capabilities[capability]["failed_syntheses"],
            "successful_evolved_syntheses": capabilities[capability]["successful_evolved_syntheses"],
            "successful_syntheses": capabilities[capability]["successful_syntheses"],
            "total_syntheses": capabilities[capability]["total_syntheses"],
            "last_synthesis_source": capabilities[capability].get("last_synthesis_source"),
            "last_synthesis_status": capabilities[capability].get("last_synthesis_status"),
            "last_synthesis_used_evolution": capabilities[capability].get("last_synthesis_used_evolution"),
        }
        for capability, incoming in sorted(incoming_caps.items())
        if isinstance(incoming, dict)
    ]

    for entry in capabilities.values():
        if isinstance(entry, dict):
            entry.setdefault("last_synthesis_used_evolution", False)
            entry.setdefault("successful_evolved_syntheses", 0)

    result_ledger = {
        "capabilities": capabilities
    }

    out = Path(output_path or ledger_path)
    write_json_deterministic(out, result_ledger)

    return {
        "updated": True,
        "ledger_path": str(out),
        "capabilities": result_ledger["capabilities"],
        "updates": updates,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Update capability-effectiveness ledger from an autonomous factory cycle artifact."
    )
    parser.add_argument("--ledger", required=True, metavar="FILE",
                        help="Path to capability_effectiveness_ledger.json.")
    parser.add_argument("--cycle-artifact", required=True, metavar="FILE",
                        help="Path to autonomous factory cycle artifact JSON.")
    parser.add_argument("--output", default=None, metavar="FILE",
                        help="Optional output path for updated ledger.")
    args = parser.parse_args(argv)

    result = update_capability_effectiveness_ledger(
        ledger_path=args.ledger,
        cycle_artifact_path=args.cycle_artifact,
        output_path=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
