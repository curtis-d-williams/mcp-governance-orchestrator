# SPDX-License-Identifier: MIT
"""Shared runtime helpers for persistent factory orchestration."""

import json
from datetime import datetime, timezone
from pathlib import Path


def utcnow_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path, default):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(path, payload):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path, payload):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True) + "\n")


def initial_factory_state():
    return {
        "cycle_count": 0,
        "last_cycle_status": None,
        "last_decision": None,
        "last_risk_level": None,
        "last_learning_applied": False,
        "consecutive_idle_cycles": 0,
        "consecutive_failed_cycles": 0,
        "last_updated_at": None,
    }


def extract_risk_level(artifact):
    evaluation = artifact.get("evaluation") or {}
    if evaluation.get("risk_level"):
        return evaluation["risk_level"]

    cycle_result = artifact.get("cycle_result") or {}
    if cycle_result.get("risk_level"):
        return cycle_result["risk_level"]

    baseline = cycle_result.get("baseline_evaluation") or {}
    if baseline.get("risk_level"):
        return baseline["risk_level"]

    repaired = cycle_result.get("repaired_evaluation") or {}
    if repaired.get("risk_level"):
        return repaired["risk_level"]

    return None


def extract_learning_applied(artifact):
    learning = artifact.get("learning_update") or {}
    if learning.get("applied") is True:
        return True

    cycle_result = artifact.get("cycle_result") or {}
    nested = cycle_result.get("learning_update") or {}
    return nested.get("applied") is True


def extract_repair_applied(artifact):
    cycle_result = artifact.get("cycle_result") or {}

    if cycle_result.get("auto_repair_applied") is True:
        return True

    if cycle_result.get("repair_success") is True:
        return True

    repair_cycle = cycle_result.get("auto_repair_cycle") or {}
    return repair_cycle.get("repair_success") is True


def reasons_indicate_idle(reasons):
    normalized = " | ".join(str(r).lower() for r in (reasons or []))
    return (
        "no actions" in normalized
        or "planner produced no actions" in normalized
        or "empty" in normalized
        or "no action window" in normalized
    )


def extract_factory_status(artifact, error=None):
    if error is not None:
        return "failed"

    decision = (artifact.get("decision") or {}).get("action")
    if decision == "idle":
        return "idle"

    evaluation = artifact.get("evaluation") or {}
    cycle_result = artifact.get("cycle_result") or {}

    if cycle_result.get("idle") is True:
        return "idle"

    if cycle_result.get("abort_reason"):
        return "failed"

    if reasons_indicate_idle(evaluation.get("reasons")):
        return "idle"

    baseline = cycle_result.get("baseline_evaluation") or {}
    if reasons_indicate_idle(baseline.get("reasons")):
        return "idle"

    if decision == "repair_only":
        if cycle_result.get("repair_success") is True:
            return "completed"
        return "failed"

    return artifact.get("status") or "completed"


def build_factory_journal_entry(artifact, *, status, error=None):
    cycle_result = artifact.get("cycle_result") or {}
    decision = artifact.get("decision") or {}
    return {
        "timestamp": utcnow_iso(),
        "decision": decision.get("action"),
        "risk_level": extract_risk_level(artifact),
        "repair_applied": extract_repair_applied(artifact),
        "learning_applied": extract_learning_applied(artifact),
        "status": status,
        "error": str(error) if error else None,
        "repair_cycle_status": cycle_result.get("repair_cycle_status")
        or cycle_result.get("status"),
    }


def update_factory_state(state, artifact, *, status):
    next_state = dict(state)
    next_state["cycle_count"] = int(state.get("cycle_count", 0)) + 1
    next_state["last_cycle_status"] = status
    next_state["last_decision"] = (artifact.get("decision") or {}).get("action")
    next_state["last_risk_level"] = extract_risk_level(artifact)
    next_state["last_learning_applied"] = extract_learning_applied(artifact)

    if status == "idle":
        next_state["consecutive_idle_cycles"] = int(state.get("consecutive_idle_cycles", 0)) + 1
    else:
        next_state["consecutive_idle_cycles"] = 0

    if status == "failed":
        next_state["consecutive_failed_cycles"] = int(state.get("consecutive_failed_cycles", 0)) + 1
    else:
        next_state["consecutive_failed_cycles"] = 0

    next_state["last_updated_at"] = utcnow_iso()
    return next_state


def should_stop_factory(state, *, max_failures, max_idle_cycles):
    if int(state.get("consecutive_failed_cycles", 0)) >= max_failures:
        return True, "max_consecutive_failures_reached"
    if int(state.get("consecutive_idle_cycles", 0)) >= max_idle_cycles:
        return True, "max_consecutive_idle_cycles_reached"
    return False, None
