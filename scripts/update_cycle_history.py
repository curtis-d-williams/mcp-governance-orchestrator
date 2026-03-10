# SPDX-License-Identifier: MIT
"""Append a normalized record to artifacts/cycle_history.json.

Reads governed_portfolio_cycle.json and appends a deterministic normalized
record to the cycle history index.  Running this script multiple times
against the same cycle artifact at the same logical timestamp is idempotent:
if the normalized record is already present, it is not duplicated.

Usage:
    python3 scripts/update_cycle_history.py \\
        --cycle-artifact governed_portfolio_cycle.json \\
        --output artifacts/cycle_history.json

Exit codes:
    0  — history file written (or unchanged when already up-to-date)
    1  — error (unreadable input, bad JSON, etc.)
"""

import argparse
import datetime
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _write_json(path, data):
    """Write *data* as deterministic JSON (indent=2, sort_keys, trailing newline)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _try_read_json(path):
    """Return parsed JSON from *path* if it exists, else None."""
    p = Path(path)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None


# ---------------------------------------------------------------------------
# Timestamp helper (injectable for deterministic tests)
# ---------------------------------------------------------------------------

def _utcnow_iso():
    """Return the current UTC time as an ISO-8601 string with trailing 'Z'."""
    return datetime.datetime.utcnow().isoformat() + "Z"


# ---------------------------------------------------------------------------
# Record normalization
# ---------------------------------------------------------------------------

_RECORD_KEYS = ("ledger_source", "selected_tasks", "status", "timestamp")


def _normalize_record(cycle_artifact, timestamp):
    """Return a deterministic normalized record from *cycle_artifact*.

    Fields:
      - status:         top-level status from the cycle artifact
      - ledger_source:  planner_inputs.ledger_source (or None)
      - selected_tasks: execution_result.selected_tasks (or None)
      - timestamp:      UTC ISO-8601 string passed by the caller

    Args:
        cycle_artifact: parsed cycle artifact dict
        timestamp:      UTC ISO-8601 string

    Returns:
        dict with exactly the keys in _RECORD_KEYS
    """
    planner_inputs = cycle_artifact.get("planner_inputs") or {}
    execution_result = cycle_artifact.get("execution_result") or {}
    return {
        "ledger_source": planner_inputs.get("ledger_source"),
        "selected_tasks": execution_result.get("selected_tasks"),
        "status": cycle_artifact.get("status"),
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# History update
# ---------------------------------------------------------------------------

def update_cycle_history(cycle_artifact_path, output_path, _now_fn=None):
    """Append a normalized record from *cycle_artifact_path* to *output_path*.

    The dedup key is the canonical JSON of the full normalized record
    (including timestamp).  If the record is already present, the file is
    rewritten deterministically but no new entry is added.

    Args:
        cycle_artifact_path: Path to governed_portfolio_cycle.json.
        output_path:         Path to cycle_history.json (created if absent).
        _now_fn:             Optional callable returning a UTC ISO-8601 string.
                             Defaults to _utcnow_iso().  Provided for testing.

    Returns:
        0 on success, 1 on error.
    """
    if _now_fn is None:
        _now_fn = _utcnow_iso

    try:
        cycle_artifact = json.loads(
            Path(cycle_artifact_path).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot read cycle artifact: {exc}\n")
        return 1

    timestamp = _now_fn()
    new_record = _normalize_record(cycle_artifact, timestamp)
    new_canonical = json.dumps(new_record, sort_keys=True)

    # Load existing history or start fresh.
    existing = _try_read_json(output_path)
    if existing is None:
        existing = {"cycles": []}

    existing_cycles = existing.get("cycles", [])
    if not isinstance(existing_cycles, list):
        existing_cycles = []

    # Collect existing canonical strings (dedupe set).
    existing_canonicals = {json.dumps(r, sort_keys=True) for r in existing_cycles}

    if new_canonical in existing_canonicals:
        # Already present — write back sorted but make no new entry.
        all_canonicals = sorted(existing_canonicals)
    else:
        all_canonicals = sorted(existing_canonicals | {new_canonical})

    cycles = [json.loads(c) for c in all_canonicals]
    _write_json(output_path, {"cycles": cycles})
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Append a normalized cycle record to cycle_history.json.",
        add_help=True,
    )
    parser.add_argument("--cycle-artifact", required=True, metavar="FILE",
                        help="Path to governed_portfolio_cycle.json.")
    parser.add_argument("--output", required=True, metavar="FILE",
                        help="Path to cycle_history.json (created if absent).")

    args = parser.parse_args(argv)
    sys.exit(update_cycle_history(args.cycle_artifact, args.output))


if __name__ == "__main__":
    main()
