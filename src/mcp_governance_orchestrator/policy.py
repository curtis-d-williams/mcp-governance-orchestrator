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


def _apply_selection(
    guardians: List[Dict[str, Any]],
    select: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Deterministic selection:
      - If select is empty: selected = all guardians
      - Else: selected guardians must match ALL select clauses (AND across clauses)
    Returns (selected_guardians, selected_ids_sorted)
    """
    if not select:
        ids = sorted([g.get("guardian_id") for g in guardians if g.get("guardian_id") is not None])
        return list(guardians), ids

    selected: List[Dict[str, Any]] = []
    for g in guardians:
        ok = True
        for clause in select:
            if not _matches_clause(g, clause):
                ok = False
                break
        if ok:
            selected.append(g)

    selected_ids_sorted = sorted([g.get("guardian_id") for g in selected if g.get("guardian_id") is not None])
    return selected, selected_ids_sorted


def evaluate_policy(
    policy: Dict[str, Any],
    normalized_guardians: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Pure deterministic policy evaluation.
    No imports, no execution, metadata-only.

    Selection happens first; require/forbid/constraints apply to selected set.
    Backward compatible: missing/empty select => all guardians selected.
    """
    select = policy.get("select", []) or []
    require = policy.get("require", []) or []
    forbid = policy.get("forbid", []) or []
    constraints = policy.get("constraints", {}) or {}

    # Guardians must already be normalized & deterministically ordered upstream.
    all_guardians = list(normalized_guardians)
    selected_guardians, selected_ids_sorted = _apply_selection(all_guardians, select)

    require_results = []
    forbid_results = []
    constraint_results = []

    # ---- REQUIRE (applies to selected set) ----
    require_passed = 0
    for clause in require:
        matched = [
            g.get("guardian_id")
            for g in selected_guardians
            if _matches_clause(g, clause)
        ]
        matched_sorted = sorted([x for x in matched if x is not None])
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

    # ---- FORBID (applies to selected set) ----
    forbid_passed = 0
    for clause in forbid:
        violations = [
            g.get("guardian_id")
            for g in selected_guardians
            if _matches_clause(g, clause)
        ]
        violations_sorted = sorted([x for x in violations if x is not None])
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

    # ---- CONSTRAINTS (applies to selected set) ----
    constraints_passed = 0
    total_constraints = 0

    # Deterministic constraint evaluation order:
    # 1) disallow_tier3_only
    # 2) min_selected
    # 3) max_selected
    # 4) require_tiers

    if constraints.get("disallow_tier3_only") is True:
        total_constraints += 1
        tiers = [g.get("tier") for g in selected_guardians]
        all_tier3 = len(tiers) > 0 and all(t == 3 for t in tiers)
        ok = not all_tier3
        if ok:
            constraints_passed += 1

        constraint_results.append(
            {
                "name": "disallow_tier3_only",
                "enabled": True,
                "ok": ok,
                "details": "ok" if ok else "all_selected_guardians_are_tier3",
            }
        )

    if isinstance(constraints.get("min_selected"), int):
        total_constraints += 1
        min_sel = constraints["min_selected"]
        n = len(selected_guardians)
        ok = n >= min_sel
        if ok:
            constraints_passed += 1
        constraint_results.append(
            {
                "name": "min_selected",
                "enabled": True,
                "ok": ok,
                "details": "ok" if ok else f"selected_total {n} < min_selected {min_sel}",
            }
        )

    if isinstance(constraints.get("max_selected"), int):
        total_constraints += 1
        max_sel = constraints["max_selected"]
        n = len(selected_guardians)
        ok = n <= max_sel
        if ok:
            constraints_passed += 1
        constraint_results.append(
            {
                "name": "max_selected",
                "enabled": True,
                "ok": ok,
                "details": "ok" if ok else f"selected_total {n} > max_selected {max_sel}",
            }
        )

    if isinstance(constraints.get("require_tiers"), list):
        tiers_req = constraints["require_tiers"]
        if all(isinstance(t, int) for t in tiers_req):
            total_constraints += 1
            present = sorted({g.get("tier") for g in selected_guardians if isinstance(g.get("tier"), int)})
            missing = sorted([t for t in tiers_req if t not in present])
            ok = len(missing) == 0
            if ok:
                constraints_passed += 1
            constraint_results.append(
                {
                    "name": "require_tiers",
                    "enabled": True,
                    "ok": ok,
                    "details": "ok" if ok else f"missing_tiers {missing}",
                    "present_tiers": present,
                }
            )

    # ---- SUMMARY ----
    summary = {
        "selected_total": len(selected_guardians),
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
        "selection": {
            "clauses": select,
            "selected_guardians": selected_ids_sorted,
        },
        "summary": summary,
        "require": require_results,
        "forbid": forbid_results,
        "constraints": constraint_results,
    }
