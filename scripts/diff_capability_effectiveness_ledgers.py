#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Diff two capability_effectiveness_ledger.json files and report changes.

Usage:
    python3 scripts/diff_capability_effectiveness_ledgers.py \
        --before seed.json --after updated.json
    python3 scripts/diff_capability_effectiveness_ledgers.py \
        --before seed.json --after updated.json --output diff.json

Exits 0 on success. Writes structured JSON diff to --output (or stdout).
Fails closed on missing or malformed input.
No external library dependencies.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_TRACKED_FIELDS = (
    "artifact_kind",
    "total_syntheses",
    "successful_syntheses",
    "failed_syntheses",
    "successful_evolved_syntheses",
    "last_synthesis_status",
    "last_synthesis_source",
    "last_synthesis_used_evolution",
    "similarity_score",
    "similarity_delta",
    "last_comparison_status",
)


def _fail(msg: str) -> int:
    sys.stderr.write(f"error: {msg}\n")
    return 1


def _load_ledger(path: Path) -> dict:
    if not path.exists():
        raise ValueError(f"input file not found: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read input file: {exc}") from exc
    try:
        ledger = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON: {exc}") from exc
    if not isinstance(ledger, dict):
        raise ValueError("ledger must be a JSON object")
    if "capabilities" not in ledger:
        raise ValueError("ledger missing required key 'capabilities'")
    if not isinstance(ledger["capabilities"], dict):
        raise ValueError("ledger 'capabilities' must be an object")
    return ledger


def _diff_capabilities(before: dict, after: dict) -> dict:
    """Return a structured diff between two capabilities dicts."""
    before_keys = set(before)
    after_keys = set(after)

    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)

    changed: dict[str, dict] = {}
    unchanged: list[str] = []
    for key in sorted(before_keys & after_keys):
        b_entry = before[key] if isinstance(before[key], dict) else {}
        a_entry = after[key] if isinstance(after[key], dict) else {}
        field_diffs: dict[str, dict] = {}
        for field in _TRACKED_FIELDS:
            b_val = b_entry.get(field)
            a_val = a_entry.get(field)
            if b_val != a_val:
                field_diffs[field] = {"before": b_val, "after": a_val}
        if field_diffs:
            changed[key] = field_diffs
        else:
            unchanged.append(key)

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": unchanged,
        "summary": {
            "added_count": len(added),
            "removed_count": len(removed),
            "changed_count": len(changed),
            "unchanged_count": len(unchanged),
        },
    }


def build_diff_report(before_path: Path, after_path: Path) -> dict:
    before_ledger = _load_ledger(before_path)
    after_ledger = _load_ledger(after_path)
    diff = _diff_capabilities(
        before_ledger["capabilities"],
        after_ledger["capabilities"],
    )
    return {
        "before": str(before_path),
        "after": str(after_path),
        **diff,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diff two capability_effectiveness_ledger.json files.",
    )
    parser.add_argument("--before", required=True, metavar="FILE",
                        help="Path to the earlier capability_effectiveness_ledger.json.")
    parser.add_argument("--after", required=True, metavar="FILE",
                        help="Path to the later capability_effectiveness_ledger.json.")
    parser.add_argument("--output", default=None, metavar="FILE",
                        help="Destination JSON file (default: stdout).")
    args = parser.parse_args(argv)

    try:
        report = build_diff_report(Path(args.before), Path(args.after))
    except ValueError as exc:
        return _fail(str(exc))

    out_text = json.dumps(report, indent=2, sort_keys=True) + "\n"

    if args.output:
        out = Path(args.output)
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(out_text, encoding="utf-8")
        except OSError as exc:
            return _fail(f"cannot write output: {exc}")
        sys.stdout.write(f"wrote: {out}\n")
    else:
        sys.stdout.write(out_text)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
