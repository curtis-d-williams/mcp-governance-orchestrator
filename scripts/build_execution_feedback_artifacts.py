#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""CLI: build execution feedback artifacts in one step.

This wrapper composes:
1. build_evaluation_record_from_run.py
2. build_action_effectiveness_ledger.py

Usage:
    python3 scripts/build_execution_feedback_artifacts.py \
        --before <portfolio_state_before.json> \
        --after <portfolio_state_after.json> \
        --executed-actions <executed_actions.json> \
        --evaluation-output <evaluation_records.json> \
        --ledger-output <action_effectiveness_ledger.json> \
        [--generated-at <string>]

Fails closed on any upstream error.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _fail(msg: str) -> int:
    sys.stderr.write(f"error: {msg}\n")
    return 1


def _run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build evaluation records and action effectiveness ledger in one step.",
    )
    parser.add_argument("--before", required=True, metavar="FILE",
                        help="Path to portfolio_state_before.json.")
    parser.add_argument("--after", required=True, metavar="FILE",
                        help="Path to portfolio_state_after.json.")
    parser.add_argument("--executed-actions", required=True, metavar="FILE",
                        help="Path to executed_actions.json.")
    parser.add_argument("--evaluation-output", required=True, metavar="FILE",
                        help="Destination path for evaluation_records.json.")
    parser.add_argument("--ledger-output", required=True, metavar="FILE",
                        help="Destination path for action_effectiveness_ledger.json.")
    parser.add_argument("--generated-at", default="", metavar="STRING",
                        help="Value for generated_at fields. Defaults to empty string.")
    args = parser.parse_args(argv)

    before = Path(args.before)
    after = Path(args.after)
    executed = Path(args.executed_actions)
    evaluation_output = Path(args.evaluation_output)
    ledger_output = Path(args.ledger_output)

    for label, path in (
        ("before_state", before),
        ("after_state", after),
        ("executed actions", executed),
    ):
        if not path.exists():
            return _fail(f"{label} file not found: {path}")

    eval_cmd = [
        sys.executable,
        "scripts/build_evaluation_record_from_run.py",
        "--before", str(before),
        "--after", str(after),
        "--executed-actions", str(executed),
        "--output", str(evaluation_output),
    ]
    if args.generated_at:
        # no generated_at flag on evaluation builder by design
        pass

    rc, out, err = _run(eval_cmd)
    if rc != 0:
        return _fail(f"evaluation record build failed: {(err or out).strip()}")

    ledger_cmd = [
        sys.executable,
        "scripts/build_action_effectiveness_ledger.py",
        "--input", str(evaluation_output),
        "--output", str(ledger_output),
        "--generated-at", args.generated_at,
    ]
    rc, out, err = _run(ledger_cmd)
    if rc != 0:
        return _fail(f"ledger build failed: {(err or out).strip()}")

    sys.stdout.write(f"wrote: {evaluation_output}\n")
    sys.stdout.write(f"wrote: {ledger_output}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
