from __future__ import annotations

import ast
import json
from mcp_governance_orchestrator.policy_schema_v1 import validate_policy_schema_v1, policy_schema_error_report
from pathlib import Path
from typing import Dict, Any, List, Tuple, Iterable


REGISTRY_PATH = Path("config/guardians.json")


def load_registry(repo_root: Path | None = None) -> Dict[str, Any]:
    """
    Load raw registry JSON without modification.
    Deterministic, read-only.
    """
    root = repo_root or Path(".")
    path = root / REGISTRY_PATH
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _infer_tier(module_path: str) -> int:
    """
    Tier inference rules (must match orchestrator semantics):
    - Explicit tier (if structured entry with int) wins.
    - Else infer Tier 3 if module_path starts with 'templates.'
    - Else default Tier 1.
    """
    if module_path.startswith("templates."):
        return 3
    return 1


def normalize_registry(raw: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Normalize registry entries into a uniform structured form.

    Output schema per guardian_id:

    {
        "module_path": str,
        "callable": str,
        "tier": int,
        "description": str,
        "capabilities": dict,
        "entry_format": "legacy" | "structured"
    }

    Deterministic:
    - Does NOT execute guardians
    - Does NOT import guardians
    - Pure transformation only
    """
    normalized: Dict[str, Dict[str, Any]] = {}

    for guardian_id, entry in raw.items():
        if isinstance(entry, str):
            # Legacy string format
            module_path = entry
            callable_name = "main"
            tier = _infer_tier(module_path)
            description = ""
            capabilities: Dict[str, Any] = {}
            entry_format = "legacy"
        elif isinstance(entry, dict):
            module_path = entry.get("module_path", "")
            callable_name = entry.get("callable", "main")
            description = entry.get("description", "")
            entry_format = "structured"

            explicit_tier = entry.get("tier")
            if isinstance(explicit_tier, int):
                tier = explicit_tier
            else:
                tier = _infer_tier(module_path)

            caps = entry.get("capabilities", {})
            if caps is None:
                capabilities = {}
            elif isinstance(caps, dict):
                capabilities = caps
            else:
                raise ValueError(f"Invalid capabilities format for {guardian_id}: must be object")
        else:
            raise ValueError(f"Invalid registry entry format for {guardian_id}")

        normalized[guardian_id] = {
            "module_path": module_path,
            "callable": callable_name,
            "tier": tier,
            "description": description,
            "capabilities": capabilities,
            "entry_format": entry_format,
        }

    return normalized


def inspect_registry(repo_root: Path | None = None) -> Dict[str, Dict[str, Any]]:
    """
    Public API for registry introspection.
    Returns normalized registry sorted deterministically by guardian_id.
    """
    raw = load_registry(repo_root=repo_root)
    normalized = normalize_registry(raw)
    sorted_ids = sorted(normalized.keys())
    return {gid: normalized[gid] for gid in sorted_ids}


def _safe_read_module_source(repo_root: Path, module_path: str) -> Tuple[Path | None, str | None]:
    """
    Best-effort, read-only module source resolution WITHOUT importing.

    We only attempt static parsing for modules that live inside this repo:
      - templates.<...> -> <repo_root>/templates/.../*.py
      - mcp_governance_orchestrator.<...> -> <repo_root>/src/mcp_governance_orchestrator/.../*.py

    Returns (path, source) or (None, None) if not resolvable.
    """
    if module_path.startswith("templates."):
        rel = Path(*module_path.split(".")[1:]).with_suffix(".py")
        path = repo_root / "templates" / rel
    elif module_path.startswith("mcp_governance_orchestrator."):
        rel = Path(*module_path.split(".")[1:]).with_suffix(".py")
        path = repo_root / "src" / "mcp_governance_orchestrator" / rel
    else:
        return None, None

    if not path.exists() or not path.is_file():
        return path, None

    return path, path.read_text(encoding="utf-8")


def _callable_defined_in_source(source: str, name: str) -> bool:
    """
    Static check: does the module source define a top-level function or class with this name?
    (No imports; deterministic.)
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return True
    return False


def _validate_capabilities_schema(capabilities: Dict[str, Any]) -> List[str]:
    """
    Minimal capability schema validation (v1).
    Returns list of error strings (deterministic order).
    """
    errs: List[str] = []

    if not capabilities:
        return errs

    if "domain" in capabilities and not isinstance(capabilities["domain"], str):
        errs.append("capabilities.domain must be a string")

    if "checks" in capabilities:
        checks = capabilities["checks"]
        if not isinstance(checks, list) or any(not isinstance(x, str) for x in checks):
            errs.append("capabilities.checks must be a list of strings")

    if "notes" in capabilities and not isinstance(capabilities["notes"], str):
        errs.append("capabilities.notes must be a string")

    if "io" in capabilities:
        io = capabilities["io"]
        if not isinstance(io, dict):
            errs.append("capabilities.io must be an object")
        else:
            for k in ("reads_repo", "reads_network", "writes_repo"):
                if k in io and not isinstance(io[k], bool):
                    errs.append(f"capabilities.io.{k} must be a boolean")

    if "outputs" in capabilities:
        outputs = capabilities["outputs"]
        if not isinstance(outputs, dict):
            errs.append("capabilities.outputs must be an object")
        else:
            for k in ("suggestions", "findings", "metrics"):
                if k in outputs and not isinstance(outputs[k], bool):
                    errs.append(f"capabilities.outputs.{k} must be a boolean")

    return errs


def validate_registry(repo_root: Path | None = None) -> Dict[str, Any]:
    """
    Deterministic, read-only registry validation.
    Never executes guardians.
    """
    root = repo_root or Path(".")
    raw = load_registry(repo_root=root)
    normalized = inspect_registry(repo_root=root)

    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    guardian_tiers: Dict[str, int] = {}
    try:
        from mcp_governance_orchestrator.server import GUARDIAN_TIERS  # type: ignore

        if isinstance(GUARDIAN_TIERS, dict):
            guardian_tiers = {k: v for k, v in GUARDIAN_TIERS.items() if isinstance(v, int)}
    except Exception:
        warnings.append(
            {
                "type": "guardian_tiers_unavailable",
                "message": "Could not import mcp_governance_orchestrator.server.GUARDIAN_TIERS; skipping tier consistency check vs server.",
            }
        )

    allowed_tiers = {1, 2, 3}

    for gid in sorted(normalized.keys()):
        meta = normalized[gid]

        required = {"module_path", "callable", "tier", "description", "capabilities", "entry_format"}
        if set(meta.keys()) != required:
            errors.append({"guardian_id": gid, "type": "schema", "message": f"Invalid keys: {sorted(meta.keys())}"})
            continue

        module_path = meta["module_path"]
        callable_name = meta["callable"]
        tier = meta["tier"]
        entry_format = meta["entry_format"]
        capabilities = meta["capabilities"]

        if not isinstance(module_path, str) or module_path.strip() == "":
            errors.append({"guardian_id": gid, "type": "module_path", "message": "module_path must be a non-empty string"})
        if not isinstance(callable_name, str) or callable_name.strip() == "":
            errors.append({"guardian_id": gid, "type": "callable", "message": "callable must be a non-empty string"})
        if not isinstance(tier, int) or tier not in allowed_tiers:
            errors.append({"guardian_id": gid, "type": "tier", "message": f"tier must be one of {sorted(allowed_tiers)}"})
        if entry_format not in ("legacy", "structured"):
            errors.append({"guardian_id": gid, "type": "entry_format", "message": "entry_format must be 'legacy' or 'structured'"})
        if not isinstance(capabilities, dict):
            errors.append({"guardian_id": gid, "type": "capabilities", "message": "capabilities must be an object (dict)"})
        else:
            for e in _validate_capabilities_schema(capabilities):
                errors.append({"guardian_id": gid, "type": "capabilities_schema", "message": e})

        if gid in guardian_tiers and isinstance(tier, int):
            expected = guardian_tiers[gid]
            if tier != expected:
                errors.append({"guardian_id": gid, "type": "tier_mismatch", "message": f"registry tier {tier} != server GUARDIAN_TIERS {expected}"})

        path, source = _safe_read_module_source(root, module_path) if isinstance(module_path, str) else (None, None)
        if source is None:
            if path is not None:
                warnings.append({"guardian_id": gid, "type": "module_source_missing", "message": f"Could not read module source at {path}"})
            else:
                warnings.append({"guardian_id": gid, "type": "callable_unchecked", "message": "Module not resolvable to in-repo source; callable existence not checked (no imports performed)."})
        else:
            if not _callable_defined_in_source(source, callable_name):
                errors.append({"guardian_id": gid, "type": "callable_missing", "message": f"Callable '{callable_name}' not found in {module_path} (static check)"})

        if isinstance(raw.get(gid), str) and entry_format != "legacy":
            errors.append({"guardian_id": gid, "type": "legacy_format", "message": "Raw registry entry is legacy string but normalized entry_format is not 'legacy'"})

    ok = len(errors) == 0
    return {"ok": ok, "errors": errors, "warnings": warnings, "count": len(normalized)}


def _parse_scalar(value: str) -> Any:
    """
    Deterministic scalar parser for CLI filters.
    """
    v = value.strip()
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    if v.isdigit():
        try:
            return int(v)
        except Exception:
            return v
    return v


def _get_by_path(obj: Dict[str, Any], path: str) -> Any:
    """
    Get nested value by dot path, e.g. 'capabilities.io.reads_repo'
    Returns sentinel _MISSING if not present.
    """
    _MISSING = object()
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def _match_where(guardian_id: str, meta: Dict[str, Any], key: str, expected: Any) -> bool:
    """
    Deterministic filter matching. Supports:
      - guardian_id exact match
      - meta top-level exact match (tier, entry_format, module_path, callable, description)
      - dot-path into capabilities (e.g. capabilities.domain)
      - membership test for capabilities.checks (expected must be str)
    """
    if key == "guardian_id":
        return guardian_id == expected

    if key == "capabilities.checks":
        checks = meta.get("capabilities", {}).get("checks", [])
        return isinstance(expected, str) and isinstance(checks, list) and expected in checks

    if "." in key:
        val = _get_by_path(meta, key)
        return val is not object() and val == expected  # handled below (we never compare to sentinel)
    # top-level
    return meta.get(key) == expected


def list_from_inspected(
    inspected: Dict[str, Dict[str, Any]],
    where: Iterable[str] | None = None,
    fields: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """
    Deterministic listing from a pre-inspected registry dict.
    Extracted to enable unit tests without touching on-disk registry.

    Returns a LIST of records, each includes 'guardian_id' plus selected fields.
    Sorted by guardian_id ascending.
    """
    clauses: List[Tuple[str, Any]] = []
    for clause in (where or []):
        if "=" not in clause:
            raise ValueError(f"Invalid --where clause (expected KEY=VALUE): {clause}")
        k, v = clause.split("=", 1)
        k = k.strip()
        v_parsed = _parse_scalar(v)
        clauses.append((k, v_parsed))

    default_fields = ["module_path", "callable", "tier", "description", "capabilities", "entry_format"]
    use_fields = fields or default_fields
    for f in use_fields:
        if f == "guardian_id":
            continue
        if f not in default_fields:
            raise ValueError(f"Unknown field: {f}")

    out: List[Dict[str, Any]] = []
    for gid in sorted(inspected.keys()):
        meta = inspected[gid]

        ok = True
        for k, expected in clauses:
            if k == "guardian_id":
                if gid != expected:
                    ok = False
                    break
                continue

            if k == "capabilities.checks":
                checks = meta.get("capabilities", {}).get("checks", [])
                if not (isinstance(expected, str) and isinstance(checks, list) and expected in checks):
                    ok = False
                    break
                continue

            if "." in k:
                sentinel = object()
                val = _get_by_path(meta, k)
                if val is sentinel or val != expected:
                    ok = False
                    break
                continue

            if meta.get(k) != expected:
                ok = False
                break

        if not ok:
            continue

        rec: Dict[str, Any] = {"guardian_id": gid}
        for f in use_fields:
            if f == "guardian_id":
                continue
            rec[f] = meta[f]
        out.append(rec)

    return out


def list_registry(
    repo_root: Path | None = None,
    where: Iterable[str] | None = None,
    fields: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """
    Deterministic registry listing with optional filters and field projection.

    Returns a LIST of records, each record includes 'guardian_id' and selected fields.
    Sorted by guardian_id ascending.
    """
    data = inspect_registry(repo_root=repo_root)
    return list_from_inspected(data, where=where, fields=fields)


def _render_table(rows: List[Dict[str, Any]], fields: List[str]) -> str:
    """
    Minimal deterministic table renderer (no external deps).
    """
    cols = ["guardian_id"] + [f for f in fields if f != "guardian_id"]
    # stringify values deterministically
    def s(v: Any) -> str:
        if isinstance(v, (dict, list)):
            return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return str(v)

    grid: List[List[str]] = [[c for c in cols]]
    for r in rows:
        grid.append([s(r.get(c, "")) for c in cols])

    widths = [max(len(row[i]) for row in grid) for i in range(len(cols))]
    lines: List[str] = []
    for idx, row in enumerate(grid):
        line = "  ".join(row[i].ljust(widths[i]) for i in range(len(cols)))
        lines.append(line)
        if idx == 0:
            lines.append("  ".join("-" * widths[i] for i in range(len(cols))))
    return "\n".join(lines)


def main() -> None:
    """
    CLI entrypoint:
        python -m mcp_governance_orchestrator.registry inspect
        python -m mcp_governance_orchestrator.registry validate
        python -m mcp_governance_orchestrator.registry list ...
        python -m mcp_governance_orchestrator.registry enforce-policy policy.json
    """
    import sys
    import json
    from mcp_governance_orchestrator.policy import evaluate_policy

    if len(sys.argv) < 2:
        print("Usage: python -m mcp_governance_orchestrator.registry inspect|validate|list|enforce-policy|run-policy")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "inspect":
        data = inspect_registry()
        print(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return

    if cmd == "validate":
        report = validate_registry()
        print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        sys.exit(0 if report.get("ok") else 2)

    if cmd == "enforce-policy":
        if len(sys.argv) < 3:
            print("Usage: python -m mcp_governance_orchestrator.registry enforce-policy policy.json")
            sys.exit(1)

        policy_path = sys.argv[2]

        try:
            with open(policy_path, "r", encoding="utf-8") as f:
                policy = json.load(f)
                schema_errors = validate_policy_schema_v1(policy)
                if schema_errors:
                    print(json.dumps(policy_schema_error_report(schema_errors), sort_keys=True, separators=(",", ":"), ensure_ascii=False))
                    sys.exit(3)
        except Exception as e:
            error_obj = {
                "path": "$",
                "code": "load_error",
                "message": "invalid or unreadable policy file"
            }
            print(json.dumps({
                "ok": False,
                "fail_closed": True,
                "error_type": "policy_load",
                "errors": [error_obj]
            }, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            sys.exit(3)

        inspected = inspect_registry()
        guardians = []
        for gid, meta in inspected.items():
            g = {"guardian_id": gid}
            g.update(meta)
            guardians.append(g)

        result = evaluate_policy(policy, guardians)
        result["policy_path"] = policy_path

        print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        sys.exit(0 if result.get("ok") else 2)

    if cmd == "run-policy":
        if len(sys.argv) < 4:
            print("Usage: python -m mcp_governance_orchestrator.registry run-policy policy.json repo_path")
            sys.exit(1)

        policy_path = sys.argv[2]
        repo_path = sys.argv[3]

        try:
            with open(policy_path, "r", encoding="utf-8") as f:
                policy = json.load(f)
                schema_errors = validate_policy_schema_v1(policy)
                if schema_errors:
                    print(json.dumps(policy_schema_error_report(schema_errors), sort_keys=True, separators=(",", ":"), ensure_ascii=False))
                    sys.exit(3)
        except Exception:
            error_obj = {
                "path": "$",
                "code": "load_error",
                "message": "invalid or unreadable policy file"
            }
            print(json.dumps({
                "ok": False,
                "fail_closed": True,
                "error_type": "policy_load",
                "errors": [error_obj]
            }, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            sys.exit(3)

        inspected = inspect_registry()
        guardians = []
        for gid, meta in inspected.items():
            g = {"guardian_id": gid}
            g.update(meta)
            guardians.append(g)

        plan = evaluate_policy(policy, guardians)
        plan["policy_path"] = policy_path

        # If policy does not pass, do not execute.
        if not plan.get("ok"):
            print(json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            sys.exit(2)

        selected = plan.get("selection", {}).get("selected_guardians", [])
        if not isinstance(selected, list):
            selected = []

        from mcp_governance_orchestrator.server import run_guardians as _run_guardians  # execution layer (frozen)

        exec_result = _run_guardians(repo_path=repo_path, guardians=selected)

        combined = {
            "ok": bool(exec_result.get("ok")) and bool(plan.get("ok")),
            "fail_closed": bool(exec_result.get("fail_closed")),
            "policy": plan,
            "execution": exec_result,
            "selected_guardians": selected,
            "policy_path": policy_path,
            "repo_path": repo_path,
        }

        print(json.dumps(combined, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        sys.exit(0 if combined.get("ok") else 2)


    if cmd == "list":
        where: List[str] = []
        fmt = "json"
        fields: List[str] | None = None

        args = sys.argv[2:]
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--where":
                if i + 1 >= len(args):
                    raise SystemExit("ERROR: --where requires KEY=VALUE")
                where.append(args[i + 1])
                i += 2
                continue
            if a == "--format":
                if i + 1 >= len(args):
                    raise SystemExit("ERROR: --format requires json|table")
                fmt = args[i + 1]
                i += 2
                continue
            if a == "--fields":
                if i + 1 >= len(args):
                    raise SystemExit("ERROR: --fields requires comma-separated names")
                raw_fields = [x.strip() for x in args[i + 1].split(",") if x.strip()]
                fields = raw_fields or None
                i += 2
                continue
            raise SystemExit(f"ERROR: unknown arg {a}")

        try:
            rows = list_registry(where=where, fields=fields)
        except ValueError as e:
            raise SystemExit(f"ERROR: {e}")

        use_fields = fields or ["module_path", "callable", "tier", "description", "capabilities", "entry_format"]

        if fmt == "table":
            print(_render_table(rows, use_fields))
            return
        if fmt == "json":
            print(json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            return

        raise SystemExit("ERROR: --format must be json or table")

    print("Usage: python -m mcp_governance_orchestrator.registry inspect|validate|list|enforce-policy|run-policy")
    sys.exit(1)


if __name__ == "__main__":
    main()
