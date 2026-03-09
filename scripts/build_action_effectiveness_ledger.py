#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""CLI: build action_effectiveness_ledger.json from evaluation records.

Usage:
    python3 scripts/build_action_effectiveness_ledger.py \
        --input  <evaluation_records.json> \
        --output <ledger.json> \
        [--generated-at <string>]

Fails closed on malformed input.
generated_at defaults to "" for deterministic output.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from mcp_governance_orchestrator.action_effectiveness import (  # noqa: E402
    build_action_effectiveness_ledger,
)


def _fail(msg: str) -> int:
    sys.stderr.write(f"error: {msg}\n")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build action effectiveness ledger from evaluation records.",
    )
    parser.add_argument("--input", required=True, metavar="FILE",
                        help="Path to evaluation_records.json.")
    parser.add_argument("--output", required=True, metavar="FILE",
                        help="Destination path for ledger.json.")
    parser.add_argument("--generated-at", default="", metavar="STRING",
                        help="Value for generated_at field. Defaults to empty string.")
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output)
    generated_at: str = args.generated_at

    if not input_path.exists():
        return _fail(f"input file not found: {input_path}")

    try:
        raw = input_path.read_text(encoding="utf-8")
    except OSError as exc:
        return _fail(f"cannot read input file: {exc}")

    try:
        records = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _fail(f"malformed JSON: {exc}")

    if not isinstance(records, list):
        return _fail("input JSON must be a list of evaluation records")

    try:
        ledger = build_action_effectiveness_ledger(records, generated_at=generated_at)
    except ValueError as exc:
        return _fail(str(exc))

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(ledger, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return _fail(f"cannot write output file: {exc}")

    sys.stdout.write(f"wrote: {output_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
