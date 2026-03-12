# SPDX-License-Identifier: MIT
"""Portfolio Control Plane v1 — deterministic state builder.

Accepts a list of normalized repo-signal dicts and returns a
portfolio_state dict whose schema is contract-stable at v1.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "v1"

# Numeric weights for sorting (higher = worse / higher priority).
_SEVERITY_RANK: Dict[str, int] = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}

ACTION_TASK_BINDINGS: Dict[str, str] = {
    "refresh_repo_health": "repo_health_check",
    "regenerate_missing_artifact": "artifact_regeneration_check",
    "rerun_failed_task": "failed_task_retry",
    "run_determinism_regression_suite": "determinism_regression_suite",
    "build_mcp_server": "factory_build_mcp_server",
    "build_capability_artifact": "factory_build_capability_artifact",
}

# Required fields and their expected Python types (int accepted for float fields).
_SIGNAL_FIELDS: Dict[str, type] = {
    "repo_id": str,
    "last_run_ok": bool,
    "artifact_completeness": float,
    "determinism_ok": bool,
    "recent_failures": int,
    "stale_runs": int,
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_signal(signal: Any, idx: int) -> List[str]:
    """Return a list of error strings for a single signal dict."""
    errors: List[str] = []
    if not isinstance(signal, dict):
        return [f"signal[{idx}]: expected dict, got {type(signal).__name__}"]
    for field, expected_type in _SIGNAL_FIELDS.items():
        if field not in signal:
            errors.append(f"signal[{idx}]: missing required field '{field}'")
            continue
        val = signal[field]
        # Accept int where float is expected (JSON numbers).
        if expected_type is float:
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                errors.append(
                    f"signal[{idx}].{field}: expected float, got {type(val).__name__}"
                )
        elif not isinstance(val, expected_type):
            errors.append(
                f"signal[{idx}].{field}: expected {expected_type.__name__},"
                f" got {type(val).__name__}"
            )
        # Range check for completeness after type validation passes.
    if "artifact_completeness" in signal and "artifact_completeness" not in [
        e.split(".")[1].split(":")[0] for e in errors if f"signal[{idx}]." in e
    ]:
        val = float(signal["artifact_completeness"])
        if not (0.0 <= val <= 1.0):
            errors.append(
                f"signal[{idx}].artifact_completeness: must be in [0.0, 1.0], got {val}"
            )

    # Optional: capability-gap signal for factory-generation actions.
    if "missing_capabilities" in signal:
        caps = signal["missing_capabilities"]
        if not isinstance(caps, list) or not all(isinstance(c, str) for c in caps):
            errors.append(
                f"signal[{idx}].missing_capabilities: expected list[str], got {type(caps).__name__}"
            )

    return errors


# ---------------------------------------------------------------------------
# Per-repo computation
# ---------------------------------------------------------------------------

def _sort_key_issue(issue: Dict[str, Any]) -> tuple:
    return (-_SEVERITY_RANK.get(issue["severity"], 0), issue["issue_type"])


def _sort_key_action(action: Dict[str, Any]) -> tuple:
    return (-action["priority"], action["action_type"], action["action_id"])


def _make_action(
    action_type: str,
    repo_id: str,
    priority: float,
    reason: str,
    task_args: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "action_id": f"{action_type}_{repo_id}",
        "action_type": action_type,
        "priority": priority,
        "reason": reason,
        "eligible": True,
        "blocked_by": [],
        "task_binding": {
            "task_id": ACTION_TASK_BINDINGS[action_type],
            "args": task_args or {},
        },
    }


def _make_issue(issue_type: str, severity: str, reason: str) -> Dict[str, Any]:
    return {
        "issue_type": issue_type,
        "severity": severity,
        "reason": reason,
        "status": "open",
    }


def _compute_repo_state(signal: Dict[str, Any]) -> Dict[str, Any]:
    repo_id: str = str(signal["repo_id"])
    last_run_ok: bool = bool(signal["last_run_ok"])
    artifact_completeness: float = float(signal["artifact_completeness"])
    determinism_ok: bool = bool(signal["determinism_ok"])
    recent_failures: int = int(signal["recent_failures"])
    stale_runs: int = int(signal["stale_runs"])
    missing_capabilities: List[str] = list(signal.get("missing_capabilities", []))

    issues: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []

    # Rule: stale signals
    if stale_runs >= 3:
        issues.append(_make_issue("stale_signals", "medium", "stale signals for 3 or more runs"))
        actions.append(_make_action("refresh_repo_health", repo_id, 0.55, "stale signals for 3 or more runs"))

    # Rule: artifact incomplete
    if artifact_completeness < 1.0:
        if artifact_completeness == 0.0:
            severity = "high"
            priority = 0.85
            reason = "required artifact set is completely missing"
        else:
            severity = "medium"
            priority = 0.70
            reason = "required artifact set is incomplete"
        issues.append(_make_issue("artifact_incomplete", severity, reason))
        actions.append(_make_action("regenerate_missing_artifact", repo_id, priority, reason))

    # Rule: repeated failure
    if recent_failures >= 2:
        issues.append(_make_issue("repeated_failure", "high", "task failed repeatedly in recent runs"))
        actions.append(_make_action("rerun_failed_task", repo_id, 0.80, "task failed repeatedly in recent runs"))

    # Rule: determinism regression
    if not determinism_ok:
        issues.append(_make_issue("determinism_regression", "critical", "determinism regression detected"))
        actions.append(_make_action("run_determinism_regression_suite", repo_id, 0.95, "determinism regression detected"))

        # Rule: capability gap
    if "github_repository_management" in missing_capabilities:
        issues.append(_make_issue(
            "capability_gap",
            "medium",
            "missing github_repository_management capability",
        ))
        actions.append(_make_action(
            "build_capability_artifact",
            repo_id,
            0.60,
            "missing github_repository_management capability",
            task_args={
                "artifact_kind": "mcp_server",
                "capability": "github_repository_management",
            },
        ))

    if "slack_workspace_access" in missing_capabilities:
        issues.append(_make_issue(
            "capability_gap",
            "medium",
            "missing slack_workspace_access capability",
        ))
        actions.append(_make_action(
            "build_capability_artifact",
            repo_id,
            0.60,
            "missing slack_workspace_access capability",
            task_args={
                "artifact_kind": "agent_adapter",
                "capability": "slack_workspace_access",
            },
        ))

    if "postgres_data_access" in missing_capabilities:
        issues.append(_make_issue(
            "capability_gap",
            "medium",
            "missing postgres_data_access capability",
        ))
        actions.append(_make_action(
            "build_capability_artifact",
            repo_id,
            0.60,
            "missing postgres_data_access capability",
            task_args={
                "artifact_kind": "data_connector",
                "capability": "postgres_data_access",
            },
        ))

    # Health score: start at 1.0, subtract deductions, clamp, round.
    score = 1.0
    if not determinism_ok:
        score -= 0.60
    if recent_failures >= 2:
        score -= 0.35
    if artifact_completeness == 0.0:
        score -= 0.30
    elif artifact_completeness < 1.0:
        score -= 0.15
    if stale_runs >= 3:
        score -= 0.10
    health_score = round(max(0.0, min(1.0, score)), 2)

    # Status: worst wins (failing > degraded > stale > healthy).
    if not determinism_ok or recent_failures >= 2:
        status = "failing"
    elif artifact_completeness < 1.0:
        status = "degraded"
    elif stale_runs >= 3:
        status = "stale"
    else:
        status = "healthy"

    # Risk level: worst wins (critical > high > medium > low).
    if not determinism_ok:
        risk_level = "critical"
    elif recent_failures >= 2 or artifact_completeness == 0.0:
        risk_level = "high"
    elif stale_runs >= 3 or (0.0 < artifact_completeness < 1.0):
        risk_level = "medium"
    else:
        risk_level = "low"

    # Deterministic sort.
    issues_sorted = sorted(issues, key=_sort_key_issue)
    actions_sorted = sorted(actions, key=_sort_key_action)

    return {
        "repo_id": repo_id,
        "status": status,
        "health_score": health_score,
        "risk_level": risk_level,
        "signals": {
            "last_run_ok": last_run_ok,
            "artifact_completeness": artifact_completeness,
            "determinism_ok": determinism_ok,
            "recent_failures": recent_failures,
            "stale_runs": stale_runs,
        },
        "open_issues": issues_sorted,
        "recommended_actions": actions_sorted,
        "action_history": [],
        "cooldowns": [],
        "escalations": [],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_portfolio_state(
    signals: List[Dict[str, Any]],
    *,
    generated_at: str = "",
    portfolio_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a deterministic portfolio_state dict from a list of repo signals.

    Args:
        signals: List of normalized repo-signal dicts.
        generated_at: Timestamp string.  Defaults to empty string for
            deterministic output.  Pass a fixed value in tests.
        portfolio_id: Override the derived portfolio identifier.  When None
            a stable SHA-256 prefix is derived from the sorted repo IDs.

    Raises:
        ValueError: If any signal fails schema validation.
    """
    if not isinstance(signals, list):
        raise ValueError("signals must be a list")

    all_errors: List[str] = []
    for i, sig in enumerate(signals):
        all_errors.extend(_validate_signal(sig, i))
    if all_errors:
        raise ValueError("Invalid signals:\n" + "\n".join(all_errors))

    # Deterministic repo order.
    sorted_signals = sorted(signals, key=lambda s: str(s["repo_id"]))

    # Stable portfolio_id derived from sorted repo IDs when not supplied.
    if portfolio_id is None:
        repo_ids_key = "|".join(str(s["repo_id"]) for s in sorted_signals)
        portfolio_id = (
            "portfolio-"
            + hashlib.sha256(repo_ids_key.encode("utf-8")).hexdigest()[:12]
        )

    repos = [_compute_repo_state(sig) for sig in sorted_signals]

    # Portfolio-level recommendations: all actions from all repos, same sort.
    all_actions: List[Dict[str, Any]] = []
    for repo in repos:
        all_actions.extend(repo["recommended_actions"])
    portfolio_recommendations = sorted(all_actions, key=_sort_key_action)

    open_issues_total = sum(len(r["open_issues"]) for r in repos)
    eligible_actions_total = sum(
        1 for r in repos for a in r["recommended_actions"] if a["eligible"]
    )
    blocked_actions_total = sum(
        1 for r in repos for a in r["recommended_actions"] if not a["eligible"]
    )

    summary = {
        "repo_count": len(repos),
        "repos_healthy": sum(1 for r in repos if r["status"] == "healthy"),
        "repos_degraded": sum(1 for r in repos if r["status"] == "degraded"),
        "repos_failing": sum(1 for r in repos if r["status"] == "failing"),
        "repos_stale": sum(1 for r in repos if r["status"] == "stale"),
        "open_issues_total": open_issues_total,
        "eligible_actions_total": eligible_actions_total,
        "blocked_actions_total": blocked_actions_total,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "portfolio_id": portfolio_id,
        "generated_at": generated_at,
        "summary": summary,
        "repos": repos,
        "portfolio_recommendations": portfolio_recommendations,
    }
