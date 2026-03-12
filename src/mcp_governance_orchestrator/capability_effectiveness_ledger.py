# SPDX-License-Identifier: MIT
"""Deterministic capability effectiveness ledger helpers."""

def record_synthesis_event(ledger, *, capability, artifact_kind, synthesis_source, synthesis_status):
    """Return updated capability effectiveness ledger after one synthesis event."""
    capabilities = dict((ledger or {}).get("capabilities", {}))
    entry = dict(capabilities.get(capability, {}))

    entry.setdefault("artifact_kind", artifact_kind)
    entry.setdefault("failed_syntheses", 0)
    entry.setdefault("successful_syntheses", 0)
    entry.setdefault("total_syntheses", 0)

    entry["artifact_kind"] = artifact_kind
    entry["total_syntheses"] += 1
    if synthesis_status == "ok":
        entry["successful_syntheses"] += 1
    else:
        entry["failed_syntheses"] += 1
    entry["last_synthesis_source"] = synthesis_source
    entry["last_synthesis_status"] = synthesis_status

    capabilities[capability] = entry
    return {"capabilities": capabilities}
