#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""CLI: build portfolio_state.json from normalized repo-signal input JSON.

Usage:
    python3 scripts/build_portfolio_state.py --input <signals.json> --output <portfolio_state.json>
    python3 scripts/build_portfolio_state.py --input <signals.json> --output <portfolio_state.json> \
        --generated-at "2025-01-01T00:00:00+00:00"

Exits with code 1 on malformed or invalid input (fail-closed).
generated_at defaults to empty string "" when --generated-at is omitted.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure the package is importable when run as a script from the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from mcp_governance_orchestrator.portfolio_state import build_portfolio_state  # noqa: E402


def _fail(msg: str) -> int:
    sys.stderr.write(f"error: {msg}\n")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build portfolio_state.json from repo-signal input JSON.",
        add_help=True,
    )
    parser.add_argument("--input", required=True, metavar="FILE", help="Input signals JSON file (array).")
    parser.add_argument("--output", required=True, metavar="FILE", help="Output portfolio_state JSON file.")
    parser.add_argument(
        "--generated-at",
        default="",
        metavar="STRING",
        help="Timestamp string for generated_at field. Defaults to empty string.",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    output_path = Path(args.output)
    generated_at: str = args.generated_at

    # Fail closed: input must exist.
    if not input_path.exists():
        return _fail(f"input file not found: {input_path}")

    # Fail closed: input must be readable.
    try:
        raw_text = input_path.read_text(encoding="utf-8")
    except OSError as exc:
        return _fail(f"cannot read input file: {exc}")

    # Fail closed: input must be valid JSON.
    try:
        signals = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return _fail(f"malformed JSON in input file: {exc}")

    # Fail closed: top-level must be a list.
    if not isinstance(signals, list):
        return _fail("input JSON must be an array of repo-signal objects")

    # Fail closed: schema validation happens inside build_portfolio_state.
    try:
        state = build_portfolio_state(signals, generated_at=generated_at)
    except ValueError as exc:
        return _fail(str(exc))

    # Write output (create parent directories if needed).
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(state, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return _fail(f"cannot write output file: {exc}")

    sys.stdout.write(f"wrote: {output_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
