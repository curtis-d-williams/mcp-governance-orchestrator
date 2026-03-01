from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple


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
            # Defensive: unknown format
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

    # Deterministic sort by guardian_id
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

    Allowed optional keys:
      - domain: str
      - checks: list[str]
      - io: object with optional bool fields: reads_repo, reads_network, writes_repo
      - outputs: object with optional bool fields: suggestions, findings, metrics
      - notes: str

    Returns list of error strings (deterministic order).
    """
    errs: List[str] = []

    # empty is always ok
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

    # Deterministic: return in a fixed order based on checks above
    return errs


def validate_registry(repo_root: Path | None = None) -> Dict[str, Any]:
    """
    Deterministic, read-only registry validation.

    Goals:
    - schema sanity for normalized output
    - capability schema sanity (if present)
    - tier consistency against GUARDIAN_TIERS (if available)
    - best-effort callable existence check for in-repo modules (static AST parse, no imports)

    Never executes guardians.
    """
    root = repo_root or Path(".")
    raw = load_registry(repo_root=root)
    normalized = inspect_registry(repo_root=root)

    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    # Try to read GUARDIAN_TIERS from orchestrator server module (safe import; does not execute guardians).
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
            cap_errs = _validate_capabilities_schema(capabilities)
            for e in cap_errs:
                errors.append({"guardian_id": gid, "type": "capabilities_schema", "message": e})

        # Tier consistency vs server map (if present)
        if gid in guardian_tiers and isinstance(tier, int):
            expected = guardian_tiers[gid]
            if tier != expected:
                errors.append({"guardian_id": gid, "type": "tier_mismatch", "message": f"registry tier {tier} != server GUARDIAN_TIERS {expected}"})

        # Best-effort callable existence check without importing guardians
        path, source = _safe_read_module_source(root, module_path) if isinstance(module_path, str) else (None, None)
        if source is None:
            if path is not None:
                warnings.append({"guardian_id": gid, "type": "module_source_missing", "message": f"Could not read module source at {path}"})
            else:
                warnings.append({"guardian_id": gid, "type": "callable_unchecked", "message": "Module not resolvable to in-repo source; callable existence not checked (no imports performed)."})
        else:
            if not _callable_defined_in_source(source, callable_name):
                errors.append({"guardian_id": gid, "type": "callable_missing", "message": f"Callable '{callable_name}' not found in {module_path} (static check)"})

        # Backward compatibility sanity
        if isinstance(raw.get(gid), str) and entry_format != "legacy":
            errors.append({"guardian_id": gid, "type": "legacy_format", "message": "Raw registry entry is legacy string but normalized entry_format is not 'legacy'"})

    ok = len(errors) == 0
    return {"ok": ok, "errors": errors, "warnings": warnings, "count": len(normalized)}


def main() -> None:
    """
    CLI entrypoint:
        python -m mcp_governance_orchestrator.registry inspect
        python -m mcp_governance_orchestrator.registry validate
    """
    import sys

    if len(sys.argv) < 2 or sys.argv[1] not in ("inspect", "validate"):
        print("Usage: python -m mcp_governance_orchestrator.registry inspect|validate")
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


if __name__ == "__main__":
    main()
