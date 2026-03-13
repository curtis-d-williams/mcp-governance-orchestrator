# SPDX-License-Identifier: MIT
"""Deterministic capability effectiveness ledger helpers."""


def record_synthesis_event(
    ledger,
    *,
    capability,
    artifact_kind,
    synthesis_source,
    synthesis_status,
    synthesis_used_evolution=False,
):
    """Return updated capability effectiveness ledger after one synthesis event."""
    capabilities = dict((ledger or {}).get("capabilities", {}))
    entry = dict(capabilities.get(capability, {}))

    entry.setdefault("artifact_kind", artifact_kind)
    entry.setdefault("failed_syntheses", 0)
    entry.setdefault("successful_syntheses", 0)
    entry.setdefault("successful_evolved_syntheses", 0)
    entry.setdefault("total_syntheses", 0)

    entry["artifact_kind"] = artifact_kind
    entry["total_syntheses"] += 1
    if synthesis_status == "ok":
        entry["successful_syntheses"] += 1
        if synthesis_used_evolution:
            entry["successful_evolved_syntheses"] += 1
    else:
        entry["failed_syntheses"] += 1
    entry["last_synthesis_source"] = synthesis_source
    entry["last_synthesis_status"] = synthesis_status
    entry["last_synthesis_used_evolution"] = bool(synthesis_used_evolution)

    capabilities[capability] = entry
    return {"capabilities": capabilities}


def record_normalized_synthesis_event(ledger, synthesis_event):
    """Update ledger using a normalized synthesis event.

    Expected event schema:
        {
            "capability": str,
            "artifact_kind": str,
            "status": "ok" | "error",
            "source": "planner_request" | "portfolio_gap",
            ...
        }
    """

    capability = synthesis_event.get("capability")
    artifact_kind = synthesis_event.get("artifact_kind")
    status = synthesis_event.get("status")
    source = synthesis_event.get("source")
    synthesis_used_evolution = synthesis_event.get("used_evolution", False)

    if not capability or not artifact_kind or not status or not source:
        raise ValueError("Invalid synthesis_event structure")

    return record_synthesis_event(
        ledger,
        capability=capability,
        artifact_kind=artifact_kind,
        synthesis_source=source,
        synthesis_status=status,
        synthesis_used_evolution=synthesis_used_evolution,
    )
