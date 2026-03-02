from __future__ import annotations

from typing import Any, Dict, List


# Frozen Policy DSL v1
_ALLOWED_TOP_LEVEL_KEYS = ("policy_version", "select", "require", "forbid", "constraints")
_ALLOWED_CONSTRAINT_KEYS = ("disallow_tier3_only", "min_selected", "max_selected", "require_tiers")


def _err(path: str, code: str, message: str) -> Dict[str, str]:
    return {"path": path, "code": code, "message": message}


def validate_policy_schema_v1(policy: Any) -> List[Dict[str, str]]:
    """
    Deterministic Policy DSL v1 schema validation.

    Returns a list of structured errors (deterministic ordering).
    Empty list means schema-valid.
    """
    errors: List[Dict[str, str]] = []

    # 0) policy must be a dict
    if not isinstance(policy, dict):
        return [_err("$", "type", "expected object")]

    # 1) policy_version (required; int; must be 1)
    if "policy_version" not in policy:
        errors.append(_err("$.policy_version", "missing", "required"))
    else:
        pv = policy.get("policy_version")
        if not isinstance(pv, int):
            errors.append(_err("$.policy_version", "type", "expected int"))
        elif pv != 1:
            errors.append(_err("$.policy_version", "value", "unsupported version"))

    # 2) select / require / forbid: list[dict]
    for key in ("select", "require", "forbid"):
        if key in policy:
            val = policy.get(key)
            if not isinstance(val, list):
                errors.append(_err(f"$.{key}", "type", "expected list[object]"))
            else:
                for i, item in enumerate(val):
                    if not isinstance(item, dict):
                        errors.append(_err(f"$.{key}[{i}]", "type", "expected object"))

    # 3) constraints: dict
    constraints = {}
    if "constraints" in policy:
        cval = policy.get("constraints")
        if not isinstance(cval, dict):
            errors.append(_err("$.constraints", "type", "expected object"))
        else:
            constraints = cval

    # 4) unknown top-level keys (sorted)
    unknown_top = sorted([k for k in policy.keys() if k not in _ALLOWED_TOP_LEVEL_KEYS])
    for k in unknown_top:
        errors.append(_err(f"$.{k}", "unknown_key", "not allowed"))

    # If constraints wasn't a dict, don't cascade into constraint-key validation
    if "constraints" in policy and not isinstance(policy.get("constraints"), dict):
        return errors

    # 5) unknown constraint keys (sorted)
    unknown_c = sorted([k for k in constraints.keys() if k not in _ALLOWED_CONSTRAINT_KEYS])
    for k in unknown_c:
        errors.append(_err(f"$.constraints.{k}", "unknown_key", "not allowed"))

    # 6) constraint types/values (fixed order)
    if "disallow_tier3_only" in constraints and not isinstance(constraints.get("disallow_tier3_only"), bool):
        errors.append(_err("$.constraints.disallow_tier3_only", "type", "expected bool"))

    for k in ("min_selected", "max_selected"):
        if k in constraints:
            v = constraints.get(k)
            if not isinstance(v, int):
                errors.append(_err(f"$.constraints.{k}", "type", "expected int >= 0"))
            elif v < 0:
                errors.append(_err(f"$.constraints.{k}", "value", "expected int >= 0"))

    if "require_tiers" in constraints:
        rt = constraints.get("require_tiers")
        if not isinstance(rt, list):
            errors.append(_err("$.constraints.require_tiers", "type", "expected list[int]"))
        else:
            for i, item in enumerate(rt):
                if not isinstance(item, int):
                    errors.append(_err(f"$.constraints.require_tiers[{i}]", "type", "expected int"))

    return errors


def policy_schema_error_report(errors: List[Dict[str, str]]) -> Dict[str, Any]:
    return {
        "ok": False,
        "fail_closed": True,
        "error_type": "policy_schema",
        "errors": errors,
    }
