#!/usr/bin/env python3
"""
Deterministic Tier 3 template scaffolder.

Creates:
- templates/<template_name>/__init__.py
- templates/<template_name>/server.py   (contract-compliant Tier 3 guardian)
- tests/test_tier3_<template_name>.py   (determinism + contract assertions)
Updates:
- config/guardians.json                 (top-level dict: guardian_id -> module_path)

Contract source of truth:
- docs/TIER3_CONTRACT.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Dict, Any


RE_TEMPLATE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")  # python-package-ish, deterministic
RE_GUARDIAN_ID = re.compile(r"^[a-z][a-z0-9_\-]*:v[0-9]+$")  # simple, stable


def _die(msg: str, code: int = 2) -> None:
    raise SystemExit(f"error: {msg}")


def _read_registry(path: Path) -> Dict[str, Any]:
    """Read config/guardians.json.

    Backward compatible:
      - legacy entry: guardian_id -> module_path (string)
      - structured entry: guardian_id -> {module_path, callable, tier, description}

    We preserve all entries as-is (strings or dicts).
    """
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        _die(f"failed to parse {path}: {e}")
    if not isinstance(data, dict):
        _die(f"{path} must be a JSON object mapping guardian_id -> entry")
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if not isinstance(k, str):
            _die(f"{path} keys must be strings; found {type(k).__name__}")
        if isinstance(v, str):
            out[k] = v
        elif isinstance(v, dict):
            mp = v.get("module_path")
            if not isinstance(mp, str) or not mp:
                _die(f"{path} structured entry for {k!r} must include non-empty string module_path")
            out[k] = dict(v)
        else:
            _die(f"{path} values must be string or object; found {type(v).__name__} for {k!r}")
    return out


def _write_registry(path: Path, reg: Dict[str, Any]) -> None:
    # Deterministic formatting
    text = json.dumps(reg, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template-name", required=True, help="e.g. security_insights")
    ap.add_argument("--guardian-id", required=True, help='e.g. security_insights:v1')
    ap.add_argument("--description", required=True, help="one-line description for humans")
    ap.add_argument("--force", action="store_true", help="overwrite existing template files (dangerous)")
    args = ap.parse_args()

    template_name: str = args.template_name.strip()
    guardian_id: str = args.guardian_id.strip()
    description: str = args.description.strip()

    if not RE_TEMPLATE_NAME.match(template_name):
        _die("template-name must match: ^[a-z][a-z0-9_]*$ (lowercase, underscores ok)")
    if not RE_GUARDIAN_ID.match(guardian_id):
        _die("guardian-id must match: ^[a-z][a-z0-9_\\-]*:v[0-9]+$ (e.g., foo_bar:v1)")
    if not description:
        _die("description must be non-empty")

    repo_root = Path(__file__).resolve().parents[1]
    templates_dir = repo_root / "templates"
    tpl_dir = templates_dir / template_name
    registry_path = repo_root / "config" / "guardians.json"

    module_path = f"templates.{template_name}.server"

    # Load registry and check conflicts
    reg = _read_registry(registry_path)

    def _entry_module_path(entry: Any) -> str:
        if isinstance(entry, str):
            return entry
        if isinstance(entry, dict) and isinstance(entry.get("module_path"), str):
            return entry["module_path"]
        return ""

    if guardian_id in reg:
        existing_mp = _entry_module_path(reg[guardian_id])
        if existing_mp and existing_mp != module_path:
            _die(f"guardian-id already exists in registry with different module_path: {existing_mp}")
        if not args.force:
            _die(f"guardian-id already exists in registry: {guardian_id} (use --force to proceed)")

    # Create template directory
    tpl_dir.mkdir(parents=True, exist_ok=True)

    init_py = tpl_dir / "__init__.py"
    server_py = tpl_dir / "server.py"

    if (init_py.exists() or server_py.exists()) and not args.force:
        _die(f"template files already exist under {tpl_dir} (use --force to overwrite)")

    init_py.write_text("# Tier 3 template package\n", encoding="utf-8")

    # Contract-compliant Tier 3 implementation:
    # - deterministic suggestions object
    # - returns {tool, ok, fail_closed, suggestions}
    server_py.write_text(
        f'''#!/usr/bin/env python3
"""
Tier 3 (suggestion-only) template: {template_name}

Contract: docs/TIER3_CONTRACT.md
- deterministic
- non-enforcing (fail_closed must be False)
- no side effects
"""

from __future__ import annotations


def generate_suggestions() -> dict:
    # Deterministic placeholder suggestions. Replace with real logic (read-only).
    return {{
        "suggestion_id": "{template_name}_example",
        "description": {json.dumps(description)},
        "metrics": {{"example_metric": 42}},
        "notes": "Non-enforcing, deterministic"
    }}


def main() -> dict:
    suggestions = generate_suggestions()
    return {{
        "tool": "{template_name}",
        "ok": True,
        "fail_closed": False,
        "suggestions": suggestions,
    }}


if __name__ == "__main__":
    import json as _json
    out = main()
    print(_json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
''',
        encoding="utf-8",
    )
    os.chmod(server_py, 0o755)

    # Add deterministic pytest
    tests_dir = repo_root / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    test_path = tests_dir / f"test_tier3_{template_name}.py"
    if test_path.exists() and not args.force:
        _die(f"test already exists: {test_path} (use --force to overwrite)")

    test_path.write_text(
        f'''import json

from mcp_governance_orchestrator.server import run_guardians


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_tier3_{template_name}_is_deterministic_and_contract_compliant():
    out1 = run_guardians(repo_path=".", guardians=["{guardian_id}"])
    out2 = run_guardians(repo_path=".", guardians=["{guardian_id}"])

    assert _canonical(out1) == _canonical(out2)

    assert out1["ok"] is True
    assert out1["fail_closed"] is False

    g = out1["guardians"][0]
    assert g["invoked"] is True
    assert g["ok"] is True
    assert g["fail_closed"] is False

    inner = g["output"]
    assert isinstance(inner, dict)

    assert "tool" in inner and isinstance(inner["tool"], str) and inner["tool"]
    assert "ok" in inner and isinstance(inner["ok"], bool) and inner["ok"] is True
    assert "fail_closed" in inner and isinstance(inner["fail_closed"], bool) and inner["fail_closed"] is False
    assert "suggestions" in inner
''',
        encoding="utf-8",
    )

    # Update registry deterministically
    # Update registry deterministically (structured entry)
    reg[guardian_id] = {
        "module_path": module_path,
        "callable": "main",
        "tier": 3,
        "description": description,
    }
    _write_registry(registry_path, reg)

    print("ok")
    print(f"created: {tpl_dir}")
    print(f"updated: {registry_path}")
    print(f"created: {test_path}")
    print(f"module_path: {module_path}")


if __name__ == "__main__":
    main()
