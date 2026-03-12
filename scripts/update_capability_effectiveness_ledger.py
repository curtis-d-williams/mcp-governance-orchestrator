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
    write_json_deterministic,
)


def _as_int(value):
    return value if isinstance(value, int) and value >= 0 else 0


def _extract_cycle_capabilities(artifact):
    if not isinstance(artifact, dict):
        return {}
    ledger = artifact.get("capability_effectiveness_ledger") or {}
    capabilities = ledger.get("capabilities") or {}
    return capabilities if isinstance(capabilities, dict) else {}


def _ensure_entry(index, capability, incoming):
    entry = index.get(capability)
    if entry is None:
        entry = {
            "artifact_kind": incoming.get("artifact_kind"),
            "failed_syntheses": 0,
            "last_synthesis_source": incoming.get("last_synthesis_source"),
            "last_synthesis_status": incoming.get("last_synthesis_status"),
            "successful_syntheses": 0,
            "total_syntheses": 0,
        }
        index[capability] = entry

    entry.setdefault("artifact_kind", incoming.get("artifact_kind"))
    entry.setdefault("failed_syntheses", 0)
    entry.setdefault("last_synthesis_source", incoming.get("last_synthesis_source"))
    entry.setdefault("last_synthesis_status", incoming.get("last_synthesis_status"))
    entry.setdefault("successful_syntheses", 0)
    entry.setdefault("total_syntheses", 0)
    return entry


def update_capability_effectiveness_ledger(ledger_path, cycle_artifact_path, output_path=None):
    ledger = load_json_fail_closed(ledger_path, empty_ledger("capabilities"))
    artifact = load_json_fail_closed(cycle_artifact_path, {})

    capabilities = ledger.get("capabilities")
    if not isinstance(capabilities, dict):
        capabilities = {}

    incoming_caps = _extract_cycle_capabilities(artifact)
    updates = []

    for capability, incoming in sorted(incoming_caps.items()):
        if not isinstance(incoming, dict):
            continue

        entry = _ensure_entry(capabilities, capability, incoming)
        entry["artifact_kind"] = incoming.get("artifact_kind", entry.get("artifact_kind"))
        entry["failed_syntheses"] = _as_int(entry.get("failed_syntheses")) + _as_int(
            incoming.get("failed_syntheses")
        )
        entry["successful_syntheses"] = _as_int(entry.get("successful_syntheses")) + _as_int(
            incoming.get("successful_syntheses")
        )
        entry["total_syntheses"] = _as_int(entry.get("total_syntheses")) + _as_int(
            incoming.get("total_syntheses")
        )
        entry["last_synthesis_source"] = incoming.get(
            "last_synthesis_source",
            entry.get("last_synthesis_source"),
        )
        entry["last_synthesis_status"] = incoming.get(
            "last_synthesis_status",
            entry.get("last_synthesis_status"),
        )

        updates.append({
            "capability": capability,
            "artifact_kind": entry.get("artifact_kind"),
            "failed_syntheses": entry["failed_syntheses"],
            "successful_syntheses": entry["successful_syntheses"],
            "total_syntheses": entry["total_syntheses"],
            "last_synthesis_source": entry.get("last_synthesis_source"),
            "last_synthesis_status": entry.get("last_synthesis_status"),
        })

    result_ledger = {
        "capabilities": {
            capability: capabilities[capability]
            for capability in sorted(capabilities)
        }
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
