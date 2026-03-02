#!/usr/bin/env python3
"""
portfolio_adoption_report.py

Purpose (non-contract tooling):
- Given a portfolio repos.json (same shape as portfolio runner),
  emit a canonical JSON report about repo-local governance adoption.

Currently measures:
- has_repo_registry: whether <repo>/config/guardians.json exists

This does NOT change portfolio execution semantics and is intended
for observability / posture tracking only.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List


REGISTRY_REL_PATH = os.path.join("config", "guardians.json")


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _canonical_dump(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repos", required=True, help="Path to repos.json (portfolio format)")
    args = p.parse_args(argv)

    data = _load_json(args.repos)
    repos = data.get("repos")
    if not isinstance(repos, list):
        print(_canonical_dump({"ok": False, "error_type": "input_schema", "details": "repos must be a list"}))
        return 3

    rows = []
    for r in repos:
        if not isinstance(r, dict):
            continue
        rid = r.get("id")
        path = r.get("path")
        if not isinstance(rid, str) or not isinstance(path, str):
            continue
        reg_path = os.path.join(path, REGISTRY_REL_PATH)
        rows.append(
            {
                "has_repo_registry": os.path.exists(reg_path),
                "id": rid,
                "path": path,
                "registry_path": reg_path,
            }
        )

    out = {"ok": True, "repos": sorted(rows, key=lambda x: x["id"])}
    print(_canonical_dump(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
