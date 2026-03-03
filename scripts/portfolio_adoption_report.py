#!/usr/bin/env python3
"""
portfolio_adoption_report.py

Purpose (non-contract tooling):
- Given a portfolio repos.json (same shape as portfolio runner),
  emit a canonical JSON report about repo-local governance adoption.

Currently measures:
- has_repo_registry: whether <repo>/config/guardians.json exists

Optional (opt-in) engine-backed mode:
- When --engine-provenance is enabled, determine repo vs fallback registry
  using the orchestrator engine output (portfolio --include-registry-source),
  instead of a local file existence heuristic.

This does NOT change portfolio execution semantics and is intended
for observability / posture tracking only.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional


REGISTRY_REL_PATH = os.path.join("config", "guardians.json")


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _canonical_dump(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _load_registry_provenance_from_engine(policy_path: str, repos_path: str) -> Dict[str, Dict[str, str]]:
    """
    Returns mapping: repo_id -> {"source": "repo"|"fallback", "path": "<resolved path>"}
    Raises RuntimeError on engine failure.
    """
    cmd = [
        sys.executable,
        "-m",
        "mcp_governance_orchestrator.portfolio",
        "run",
        "--policy",
        policy_path,
        "--repos",
        repos_path,
        "--include-registry-source",
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    try:
        envelope = json.loads(p.stdout)
    except Exception as e:
        raise RuntimeError(
            "Failed to parse JSON from portfolio run.\n"
            f"Command: {' '.join(cmd)}\n"
            f"stderr:\n{p.stderr}\n"
            f"stdout:\n{p.stdout}\n"
            f"parse_error: {e}"
        )

    if not envelope.get("ok", False):
        raise RuntimeError(
            "Portfolio run returned ok=false.\n"
            f"error: {envelope.get('error')}\n"
            f"stderr:\n{p.stderr}"
        )

    repos = envelope.get("repos", [])
    out: Dict[str, Dict[str, str]] = {}
    for r in repos:
        if not isinstance(r, dict):
            continue
        rid = r.get("id")
        stdout_json = r.get("stdout_json") or {}
        registry = stdout_json.get("registry")
        if isinstance(rid, str) and isinstance(registry, dict):
            src = registry.get("source")
            path = registry.get("path")
            if isinstance(src, str) and isinstance(path, str):
                out[rid] = {"source": src, "path": path}
    return out


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repos", required=True, help="Path to repos.json (portfolio format)")
    p.add_argument(
        "--engine-provenance",
        action="store_true",
        help="Use orchestrator engine output (portfolio --include-registry-source) to determine repo vs fallback registry. Opt-in; default behavior unchanged.",
    )
    p.add_argument(
        "--policy",
        help="Required when --engine-provenance is set (passed to portfolio runner). Example: policies/default.json",
    )
    args = p.parse_args(argv)

    data = _load_json(args.repos)
    repos = data.get("repos")
    if not isinstance(repos, list):
        print(_canonical_dump({"ok": False, "error_type": "input_schema", "details": "repos must be a list"}))
        return 3

    engine_registry: Optional[Dict[str, Dict[str, str]]] = None
    if args.engine_provenance:
        if not isinstance(args.policy, str) or not args.policy:
            print(
                _canonical_dump(
                    {
                        "ok": False,
                        "error_type": "arg_schema",
                        "details": "--policy is required when --engine-provenance is set",
                    }
                )
            )
            return 4
        try:
            engine_registry = _load_registry_provenance_from_engine(args.policy, args.repos)
        except Exception as e:
            print(_canonical_dump({"ok": False, "error_type": "engine_provenance", "details": str(e)}))
            return 5

    rows = []
    for r in repos:
        if not isinstance(r, dict):
            continue
        rid = r.get("id")
        path = r.get("path")
        if not isinstance(rid, str) or not isinstance(path, str):
            continue

        reg_path = os.path.join(path, REGISTRY_REL_PATH)

        row: Dict[str, Any] = {
            "id": rid,
            "path": path,
            # Keep existing field stable: this is the repo-local expected location
            "registry_path": reg_path,
        }

        if engine_registry is not None and rid in engine_registry:
            # Align adoption with engine truth
            prov = engine_registry[rid]
            row["has_repo_registry"] = prov.get("source") == "repo"
            # Only emitted in engine mode (opt-in)
            row["registry_provenance"] = prov
        else:
            # Default behavior unchanged
            row["has_repo_registry"] = os.path.exists(reg_path)

        rows.append(row)

    out: Dict[str, Any] = {"ok": True, "repos": sorted(rows, key=lambda x: x["id"])}
    if args.engine_provenance:
        out["engine_provenance"] = True
        out["policy_path"] = args.policy
    print(_canonical_dump(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
