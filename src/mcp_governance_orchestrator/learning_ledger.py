# SPDX-License-Identifier: MIT
"""Deterministic helpers for learning-ledger persistence."""

import json
from pathlib import Path


def load_json_fail_closed(path, default):
    """Return parsed JSON from *path*, else *default* on any read/parse failure."""
    if path is None:
        return default
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json_deterministic(path, data):
    """Write *data* as deterministic JSON with trailing newline."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def empty_ledger(root_key):
    """Return an empty ledger envelope for a supported root key."""
    if root_key == "action_types":
        return {"action_types": []}
    if root_key == "capabilities":
        return {"capabilities": {}}
    raise ValueError(f"unsupported ledger root key: {root_key}")
