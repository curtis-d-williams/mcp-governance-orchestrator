#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""CLI: orchestrate full execution feedback capture in one step.

This thin wrapper:
1. Copies --before-source to --before-output byte-for-byte.
2. Builds --after-output via build_portfolio_state_from_artifacts.py.
3. Builds --evaluation-output and --ledger-output via
   build_execution_feedback_artifacts.py.

Usage:
    python3 scripts/capture_execution_feedback.py \
        --before-source <portfolio_state_before.json> \
        --report        <tier3_portfolio_report.csv> \
        --aggregate     <tier3_multi_run_aggregate.json> \
        --executed-actions <executed_actions.json> \
        --before-output    <artifacts/before.json> \
        --after-output     <artifacts/after.json> \
        --evaluation-output <artifacts/evaluation_records.json> \
        --ledger-output     <artifacts/action_effectiveness_ledger.json> \
        [--generated-at <string>]

Fails closed on any missing required input or any upstream error.
"""
from __future__ import annotations

import argparse
import shutil
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
        description="Capture full execution feedback: copy before-state, build after-state, build evaluation and ledger.",
    )
    parser.add_argument("--before-source", required=True, metavar="FILE",
                        help="Source portfolio_state_before.json to copy.")
    parser.add_argument("--report", required=True, metavar="CSV",
                        help="Path to tier3_portfolio_report.csv.")
    parser.add_argument("--aggregate", required=True, metavar="JSON",
                        help="Path to tier3_multi_run_aggregate.json.")
    parser.add_argument("--executed-actions", required=True, metavar="FILE",
                        help="Path to executed_actions.json.")
    parser.add_argument("--before-output", required=True, metavar="FILE",
                        help="Destination path for the copied before-state.")
    parser.add_argument("--after-output", required=True, metavar="FILE",
                        help="Destination path for the built after-state.")
    parser.add_argument("--evaluation-output", required=True, metavar="FILE",
                        help="Destination path for evaluation_records.json.")
    parser.add_argument("--ledger-output", required=True, metavar="FILE",
                        help="Destination path for action_effectiveness_ledger.json.")
    parser.add_argument("--generated-at", default="", metavar="STRING",
                        help="Value for generated_at fields. Defaults to empty string.")
    args = parser.parse_args(argv)

    before_source = Path(args.before_source)
    report = Path(args.report)
    aggregate = Path(args.aggregate)
    executed = Path(args.executed_actions)
    before_output = Path(args.before_output)
    after_output = Path(args.after_output)
    evaluation_output = Path(args.evaluation_output)
    ledger_output = Path(args.ledger_output)
    generated_at: str = args.generated_at

    # Fail closed on any missing required input.
    for label, path in (
        ("before-source", before_source),
        ("report", report),
        ("aggregate", aggregate),
        ("executed-actions", executed),
    ):
        if not path.exists():
            return _fail(f"{label} file not found: {path}")

    # Step 1: copy before-source to before-output byte-for-byte.
    try:
        before_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(before_source), str(before_output))
    except OSError as exc:
        return _fail(f"cannot copy before-source to before-output: {exc}")

    # Step 2: build after-output via build_portfolio_state_from_artifacts.py.
    after_cmd = [
        sys.executable,
        "scripts/build_portfolio_state_from_artifacts.py",
        "--report", str(report),
        "--aggregate", str(aggregate),
        "--output", str(after_output),
        "--generated-at", generated_at,
    ]
    rc, out, err = _run(after_cmd)
    if rc != 0:
        return _fail(f"after-state build failed: {(err or out).strip()}")

    # Step 3: build evaluation and ledger via build_execution_feedback_artifacts.py.
    feedback_cmd = [
        sys.executable,
        "scripts/build_execution_feedback_artifacts.py",
        "--before", str(before_output),
        "--after", str(after_output),
        "--executed-actions", str(executed),
        "--evaluation-output", str(evaluation_output),
        "--ledger-output", str(ledger_output),
        "--generated-at", generated_at,
    ]
    rc, out, err = _run(feedback_cmd)
    if rc != 0:
        return _fail(f"feedback artifact build failed: {(err or out).strip()}")

    sys.stdout.write(f"wrote: {before_output}\n")
    sys.stdout.write(f"wrote: {after_output}\n")
    sys.stdout.write(f"wrote: {evaluation_output}\n")
    sys.stdout.write(f"wrote: {ledger_output}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
