# SPDX-License-Identifier: MIT
"""Append a normalized execution record to execution_history.json.

Reads an execution_result.json produced by execute_governed_actions.py and
appends a deterministic normalized record to the history file.  Running this
script multiple times against the same execution_result is idempotent: if the
normalized record is already present, it is not duplicated.

Usage:
    python3 scripts/update_execution_history.py \\
        --execution-result execution_result.json \\
        --output execution_history.json

Exit codes:
    0  — history file written (or unchanged when already up-to-date)
    1  — error (unreadable input, bad JSON, etc.)
"""

import argparse
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
# Record normalization
# ---------------------------------------------------------------------------

_RECORD_KEYS = (
    "parsed_output",
    "resolved_via",
    "returncode",
    "selected_tasks",
    "status",
)


def _normalize_record(execution_result):
    """Return a deterministic normalized record from *execution_result*.

    Only stable, non-transient fields are included so that the record is
    reproducible across repeated runs against the same input.
    """
    return {k: execution_result.get(k) for k in _RECORD_KEYS}


# ---------------------------------------------------------------------------
# History update
# ---------------------------------------------------------------------------

def update_execution_history(execution_result_path, output_path):
    """Append a normalized record from *execution_result_path* to *output_path*.

    Args:
        execution_result_path: Path to execution_result.json.
        output_path:           Path to execution_history.json (created if absent).

    Returns:
        0 on success, 1 on error.
    """
    try:
        execution_result = json.loads(
            Path(execution_result_path).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot read execution result: {exc}\n")
        return 1

    # Load existing history or start fresh.
    existing = _try_read_json(output_path)
    if existing is None:
        existing = {"records": []}

    existing_records = existing.get("records", [])
    if not isinstance(existing_records, list):
        existing_records = []

    # Compute new record and its canonical form.
    new_record = _normalize_record(execution_result)
    new_canonical = json.dumps(new_record, sort_keys=True)

    # Collect existing canonical strings (dedupe set).
    existing_canonicals = {
        json.dumps(r, sort_keys=True) for r in existing_records
    }

    if new_canonical in existing_canonicals:
        # Already present — write back sorted but make no new entry.
        all_canonicals = sorted(existing_canonicals)
    else:
        all_canonicals = sorted(existing_canonicals | {new_canonical})

    records = [json.loads(c) for c in all_canonicals]
    _write_json(output_path, {"records": records})
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Append a normalized execution record to execution_history.json.",
        add_help=True,
    )
    parser.add_argument("--execution-result", required=True, metavar="FILE",
                        help="Path to execution_result.json.")
    parser.add_argument("--output", required=True, metavar="FILE",
                        help="Path to execution_history.json (created if absent).")

    args = parser.parse_args(argv)
    sys.exit(update_execution_history(args.execution_result, args.output))


if __name__ == "__main__":
    main()
