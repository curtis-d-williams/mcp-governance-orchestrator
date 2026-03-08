# SPDX-License-Identifier: MIT
"""Action Effectiveness Ledger v1.

Evaluates action effectiveness by action_type using before/after
portfolio_state snapshots and a list of executed actions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "v1"

_RISK_RANK: Dict[str, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def _repo_index(state: Dict[str, Any], label: str) -> Dict[str, Dict[str, Any]]:
    """Return {repo_id: repo_dict} from a portfolio_state object."""
    _require(isinstance(state, dict), f"{label}: expected dict")
    repos = state.get("repos")
    _require(isinstance(repos, list), f"{label}: 'repos' must be a list")
    index: Dict[str, Dict[str, Any]] = {}
    for i, repo in enumerate(repos):
        _require(isinstance(repo, dict), f"{label}.repos[{i}]: expected dict")
        rid = repo.get("repo_id")
        _require(isinstance(rid, str) and rid, f"{label}.repos[{i}]: missing repo_id")
        index[rid] = repo
    return index


def _validate_record(rec: Any, idx: int) -> None:
    _require(isinstance(rec, dict), f"record[{idx}]: expected dict")
    for key in ("before_state", "after_state", "executed_actions"):
        _require(key in rec, f"record[{idx}]: missing key '{key}'")
    _require(isinstance(rec["executed_actions"], list),
             f"record[{idx}].executed_actions: expected list")
    for j, act in enumerate(rec["executed_actions"]):
        _require(isinstance(act, dict),
                 f"record[{idx}].executed_actions[{j}]: expected dict")
        for field in ("action_type", "repo_id"):
            _require(isinstance(act.get(field), str) and act[field],
                     f"record[{idx}].executed_actions[{j}]: missing '{field}'")


# ---------------------------------------------------------------------------
# Per-execution delta helpers
# ---------------------------------------------------------------------------

def _risk_rank(repo: Dict[str, Any]) -> int:
    return _RISK_RANK.get(repo.get("risk_level", "low"), 0)


def _health_score(repo: Dict[str, Any]) -> float:
    val = repo.get("health_score", 1.0)
    return float(val)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Core ledger builder
# ---------------------------------------------------------------------------

def _count_recommended(action_type: str, state: Dict[str, Any]) -> int:
    """Count how many times action_type appears in all repos' recommended_actions."""
    total = 0
    for repo in state.get("repos", []):
        for act in repo.get("recommended_actions", []):
            if isinstance(act, dict) and act.get("action_type") == action_type:
                total += 1
    return total


def build_action_effectiveness_ledger(
    records: List[Dict[str, Any]],
    *,
    generated_at: str = "",
) -> Dict[str, Any]:
    """Build a deterministic Action Effectiveness Ledger from evaluation records.

    Args:
        records: Ordered list of {before_state, after_state, executed_actions}.
        generated_at: Timestamp string; defaults to "" for deterministic output.

    Raises:
        ValueError: On any schema or referential-integrity violation.
    """
    _require(isinstance(records, list), "records must be a list")

    for idx, rec in enumerate(records):
        _validate_record(rec, idx)

    # ---- Accumulate per-action_type statistics across all records ----------

    # Keyed by action_type.
    exec_risk_deltas: Dict[str, List[float]] = {}
    exec_health_deltas: Dict[str, List[float]] = {}
    exec_successes: Dict[str, int] = {}
    exec_counts: Dict[str, int] = {}
    recommended_counts: Dict[str, int] = {}

    for idx, rec in enumerate(records):
        before_idx = _repo_index(rec["before_state"], f"record[{idx}].before_state")
        after_idx = _repo_index(rec["after_state"], f"record[{idx}].after_state")

        # Count recommendations from before_state.
        for repo in rec["before_state"].get("repos", []):
            for act in repo.get("recommended_actions", []):
                if isinstance(act, dict):
                    at = act.get("action_type", "")
                    if at:
                        recommended_counts[at] = recommended_counts.get(at, 0) + 1

        # Score each executed action.
        for act in rec["executed_actions"]:
            at: str = act["action_type"]
            rid: str = act["repo_id"]

            _require(
                rid in before_idx,
                f"record[{idx}]: repo_id '{rid}' not found in before_state",
            )
            _require(
                rid in after_idx,
                f"record[{idx}]: repo_id '{rid}' not found in after_state",
            )

            before_repo = before_idx[rid]
            after_repo = after_idx[rid]

            risk_delta = float(_risk_rank(after_repo) - _risk_rank(before_repo))
            health_delta = float(_health_score(after_repo) - _health_score(before_repo))

            exec_risk_deltas.setdefault(at, []).append(risk_delta)
            exec_health_deltas.setdefault(at, []).append(health_delta)
            exec_counts[at] = exec_counts.get(at, 0) + 1
            if risk_delta < 0 or health_delta > 0:
                exec_successes[at] = exec_successes.get(at, 0) + 1
            else:
                exec_successes.setdefault(at, 0)

    # ---- Build action_types list -------------------------------------------

    all_types = sorted(
        set(recommended_counts) | set(exec_counts)
    )

    action_type_rows = []
    for at in all_types:
        t_exec = exec_counts.get(at, 0)
        t_rec = recommended_counts.get(at, 0)

        if t_exec > 0:
            risk_deltas = exec_risk_deltas.get(at, [])
            health_deltas = exec_health_deltas.get(at, [])
            avg_risk_delta = round(sum(risk_deltas) / len(risk_deltas), 2)
            avg_health_delta = round(sum(health_deltas) / len(health_deltas), 2)
            successes = exec_successes.get(at, 0)
            success_rate = round(successes / t_exec, 2)
        else:
            avg_risk_delta = 0.0
            avg_health_delta = 0.0
            success_rate = 0.0

        # Effectiveness score.
        norm_health = _clamp(avg_health_delta, 0.0, 1.0)
        norm_risk = _clamp((-avg_risk_delta) / 3.0, 0.0, 1.0)
        effectiveness_score = round(
            0.5 * success_rate + 0.3 * norm_health + 0.2 * norm_risk,
            2,
        )

        # Priority adjustment.
        if effectiveness_score >= 0.80:
            priority_adj = 0.10
        elif effectiveness_score >= 0.65:
            priority_adj = 0.05
        elif effectiveness_score >= 0.40:
            priority_adj = 0.00
        else:
            priority_adj = -0.05

        # Classification.
        if effectiveness_score >= 0.65:
            classification = "effective"
        elif effectiveness_score >= 0.40:
            classification = "neutral"
        else:
            classification = "ineffective"

        # Conservative ledger: unexecuted action types have no history to judge.
        # Override to neutral/zero so they are not penalised before any data exists.
        if t_exec == 0:
            priority_adj = 0.0
            classification = "neutral"

        action_type_rows.append({
            "action_type": at,
            "times_recommended": t_rec,
            "times_executed": t_exec,
            "success_rate": success_rate,
            "avg_risk_delta": avg_risk_delta,
            "avg_health_delta": avg_health_delta,
            "effectiveness_score": effectiveness_score,
            "recommended_priority_adjustment": priority_adj,
            "classification": classification,
        })

    # ---- Summary -----------------------------------------------------------

    effective_count = sum(1 for r in action_type_rows if r["classification"] == "effective")
    neutral_count = sum(1 for r in action_type_rows if r["classification"] == "neutral")
    ineffective_count = sum(1 for r in action_type_rows if r["classification"] == "ineffective")

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "summary": {
            "actions_tracked": len(action_type_rows),
            "effective_actions": effective_count,
            "neutral_actions": neutral_count,
            "ineffective_actions": ineffective_count,
        },
        "action_types": action_type_rows,
    }
