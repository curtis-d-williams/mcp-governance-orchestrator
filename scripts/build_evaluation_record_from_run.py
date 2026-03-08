#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""CLI: build evaluation_records.json from before/after portfolio states and executed actions.

Usage:
    python3 scripts/build_evaluation_record_from_run.py \
        --before <portfolio_state_before.json> \
        --after <portfolio_state_after.json> \
        --executed-actions <executed_actions.json> \
        --output <evaluation_records.json>

Fails closed on malformed input.
Output is a deterministic JSON list containing one evaluation record:
[
  {
    "before_state": {...},
    "after_state": {...},
    "executed_actions": [...]
  }
]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _fail(msg: str) -> int:
    sys.stderr.write(f"error: {msg}\n")
    return 1


def _read_json(path: Path, label: str) -> Any:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {label}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON in {label}: {exc}") from exc


def _require_portfolio_state(data: Any, label: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    repos = data.get("repos")
    if not isinstance(repos, list):
        raise ValueError(f"{label} must contain 'repos' as a list")
    for i, repo in enumerate(repos):
        if not isinstance(repo, dict):
            raise ValueError(f"{label}.repos[{i}] must be an object")
        repo_id = repo.get("repo_id")
        if not isinstance(repo_id, str) or not repo_id:
            raise ValueError(f"{label}.repos[{i}] missing repo_id")
    return data


def _normalize_executed_actions(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        if "executed_actions" not in data:
            raise ValueError("executed actions object must contain 'executed_actions'")
        data = data["executed_actions"]

    if not isinstance(data, list):
        raise ValueError("executed actions must be a list or an object with 'executed_actions'")

    normalized: list[dict[str, Any]] = []
    for i, action in enumerate(data):
        if not isinstance(action, dict):
            raise ValueError(f"executed_actions[{i}] must be an object")
        action_type = action.get("action_type")
        repo_id = action.get("repo_id")
        if not isinstance(action_type, str) or not action_type:
            raise ValueError(f"executed_actions[{i}] missing action_type")
        if not isinstance(repo_id, str) or not repo_id:
            raise ValueError(f"executed_actions[{i}] missing repo_id")
        normalized.append(action)

    return sorted(
        normalized,
        key=lambda a: (
            str(a["repo_id"]),
            str(a["action_type"]),
            str(a.get("action_id", "")),
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build evaluation records from before/after portfolio states and executed actions.",
    )
    parser.add_argument("--before", required=True, metavar="FILE",
                        help="Path to portfolio_state_before.json.")
    parser.add_argument("--after", required=True, metavar="FILE",
                        help="Path to portfolio_state_after.json.")
    parser.add_argument("--executed-actions", required=True, metavar="FILE",
                        help="Path to executed_actions.json.")
    parser.add_argument("--output", required=True, metavar="FILE",
                        help="Destination path for evaluation_records.json.")
    args = parser.parse_args(argv)

    before_path = Path(args.before)
    after_path = Path(args.after)
    executed_actions_path = Path(args.executed_actions)
    output_path = Path(args.output)

    for label, path in (
        ("before_state", before_path),
        ("after_state", after_path),
        ("executed actions", executed_actions_path),
    ):
        if not path.exists():
            return _fail(f"{label} file not found: {path}")

    try:
        before_state = _require_portfolio_state(
            _read_json(before_path, "before_state"),
            "before_state",
        )
        after_state = _require_portfolio_state(
            _read_json(after_path, "after_state"),
            "after_state",
        )
        executed_actions = _normalize_executed_actions(
            _read_json(executed_actions_path, "executed actions"),
        )
    except ValueError as exc:
        return _fail(str(exc))

    record = {
        "before_state": before_state,
        "after_state": after_state,
        "executed_actions": executed_actions,
    }

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps([record], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return _fail(f"cannot write output file: {exc}")

    sys.stdout.write(f"wrote: {output_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
