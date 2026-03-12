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


def as_nonnegative_int(value):
    """Return *value* as a non-negative int when possible, else 0."""
    return value if isinstance(value, int) and value >= 0 else 0


def merge_counter_ledger(
    existing_entries,
    incoming_entries,
    *,
    counter_fields,
    last_fields,
    identity_sort=True,
):
    """Merge mapping-style ledger entries deterministically.

    Rules:
    - incoming non-dict rows are ignored
    - missing entries are created
    - counter_fields are added cumulatively as non-negative ints
    - last_fields are replaced from incoming when present
    - other incoming fields are written as latest values
    """
    merged = existing_entries if isinstance(existing_entries, dict) else {}
    incoming_map = incoming_entries if isinstance(incoming_entries, dict) else {}

    for identity, incoming in incoming_map.items():
        if not isinstance(incoming, dict):
            continue

        entry = merged.get(identity)
        if entry is None:
            entry = {field: 0 for field in counter_fields}
            merged[identity] = entry

        for field in counter_fields:
            entry.setdefault(field, 0)

        for field, value in incoming.items():
            if field in counter_fields or field in last_fields:
                continue
            entry[field] = value

        for field in counter_fields:
            entry[field] = as_nonnegative_int(entry.get(field)) + as_nonnegative_int(
                incoming.get(field)
            )

        for field in last_fields:
            if field in incoming:
                entry[field] = incoming.get(field)

    if not identity_sort:
        return merged

    return {
        identity: merged[identity]
        for identity in sorted(merged)
    }
