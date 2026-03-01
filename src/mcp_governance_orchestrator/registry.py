from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any


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
        else:
            # Defensive: unknown format
            raise ValueError(f"Invalid registry entry format for {guardian_id}")

        normalized[guardian_id] = {
            "module_path": module_path,
            "callable": callable_name,
            "tier": tier,
            "description": description,
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


def main() -> None:
    """
    CLI entrypoint:
        python -m mcp_governance_orchestrator.registry inspect
    """
    import sys

    if len(sys.argv) < 2 or sys.argv[1] != "inspect":
        print("Usage: python -m mcp_governance_orchestrator.registry inspect")
        sys.exit(1)

    data = inspect_registry()

    # Canonical JSON output (stable)
    print(
        json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
