from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _get_field_path(data: Dict[str, Any], path: str) -> Tuple[bool, Any]:
    """
    Deterministic dot-path lookup.
    Returns (exists, value).
    """
    current: Any = data
    parts = path.split(".")
    for part in parts:
        if not isinstance(current, dict):
            return False, None
        if part not in current:
            return False, None
        current = current[part]
    return True, current


def _matches_clause(guardian: Dict[str, Any], clause: Dict[str, Any]) -> bool:
    """
    Guardian matches clause iff ALL predicates match.
    Predicate matches iff:
      - field exists
      - value equals expected (exact match)
    """
    for field_path, expected in clause.items():
        exists, value = _get_field_path(guardian, field_path)
        if not exists:
            return False
        if value != expected:
            return False
    return True


def evaluate_policy(
    policy: Dict[str, Any],
    normalized_guardians: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Pure deterministic policy evaluation.
    No imports, no execution, metadata-only.
    """

    require = policy.get("require", []) or []
    forbid = policy.get("forbid", []) or []
    constraints = policy.get("constraints", {}) or {}

    # Guardians must already be normalized & deterministically ordered upstream.
    guardians = list(normalized_guardians)

    require_results = []
    forbid_results = []
    constraint_results = []

    # ---- REQUIRE ----
    require_passed = 0
    for clause in require:
        matched = [
            g.get("guardian_id")
            for g in guardians
            if _matches_clause(g, clause)
        ]
        matched_sorted = sorted(matched)
        ok = len(matched_sorted) > 0
        if ok:
            require_passed += 1

        require_results.append(
            {
                "clause": clause,
                "ok": ok,
                "matched_guardians": matched_sorted,
            }
        )

    # ---- FORBID ----
    forbid_passed = 0
    for clause in forbid:
        violations = [
            g.get("guardian_id")
            for g in guardians
            if _matches_clause(g, clause)
        ]
        violations_sorted = sorted(violations)
        ok = len(violations_sorted) == 0
        if ok:
            forbid_passed += 1

        forbid_results.append(
            {
                "clause": clause,
                "ok": ok,
                "violations": violations_sorted,
            }
        )

    # ---- CONSTRAINTS ----
    constraints_passed = 0
    total_constraints = 0

    # disallow_tier3_only
    if constraints.get("disallow_tier3_only") is True:
        total_constraints += 1
        tiers = [g.get("tier") for g in guardians]
        all_tier3 = len(tiers) > 0 and all(t == 3 for t in tiers)
        ok = not all_tier3
        if ok:
            constraints_passed += 1

        constraint_results.append(
            {
                "name": "disallow_tier3_only",
                "enabled": True,
                "ok": ok,
                "details": "ok" if ok else "all_guardians_are_tier3",
            }
        )

    # ---- SUMMARY ----
    summary = {
        "require_total": len(require),
        "require_passed": require_passed,
        "forbid_total": len(forbid),
        "forbid_passed": forbid_passed,
        "constraints_total": total_constraints,
        "constraints_passed": constraints_passed,
    }

    overall_ok = (
        require_passed == len(require)
        and forbid_passed == len(forbid)
        and constraints_passed == total_constraints
    )

    return {
        "ok": overall_ok,
        "fail_closed": True,
        "summary": summary,
        "require": require_results,
        "forbid": forbid_results,
        "constraints": constraint_results,
    }
