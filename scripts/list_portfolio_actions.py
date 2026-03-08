#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Emit a deterministic prioritized action queue from portfolio_state.json.

Usage:
    python3 scripts/list_portfolio_actions.py --input <portfolio_state.json>
    python3 scripts/list_portfolio_actions.py --input <portfolio_state.json> --json
    python3 scripts/list_portfolio_actions.py --input <portfolio_state.json> --repo-id <repo_id>
    python3 scripts/list_portfolio_actions.py --input <portfolio_state.json> \
        --ledger <action_effectiveness_ledger.json>

Output (default): text table — priority | action_type | repo_id | action_id
Output (--ledger): text table — adjusted_priority | priority | action_type | repo_id | classification | action_id
Output (--json):  JSON array of action objects with repo_id added.

Only eligible==true actions are included.
Sort order (no ledger): priority desc, action_type, action_id, repo_id.
Sort order (with ledger): adjusted_priority desc, priority desc, action_type, action_id, repo_id.
Fails closed on malformed input; never modifies portfolio_state.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _fail(msg: str) -> int:
    sys.stderr.write(f"error: {msg}\n")
    return 1


# ---------------------------------------------------------------------------
# Loading and validation
# ---------------------------------------------------------------------------

def _load_state(path: Path) -> Dict[str, Any]:
    """Load and minimally validate a portfolio_state.json. Fail closed."""
    if not path.exists():
        raise ValueError(f"input file not found: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read input file: {exc}") from exc
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON: {exc}") from exc
    if not isinstance(state, dict):
        raise ValueError("portfolio_state.json must be a JSON object")
    if "repos" not in state:
        raise ValueError("portfolio_state.json missing required key 'repos'")
    if not isinstance(state["repos"], list):
        raise ValueError("'repos' must be a JSON array")
    return state


def _load_ledger(path: Path) -> Dict[str, Any]:
    """Load and minimally validate an action_effectiveness_ledger.json. Fail closed."""
    if not path.exists():
        raise ValueError(f"ledger file not found: {path}")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read ledger file: {exc}") from exc
    try:
        ledger = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed ledger JSON: {exc}") from exc
    if not isinstance(ledger, dict):
        raise ValueError("ledger must be a JSON object")
    if "action_types" not in ledger:
        raise ValueError("ledger missing required key 'action_types'")
    if not isinstance(ledger["action_types"], list):
        raise ValueError("ledger 'action_types' must be a list")
    return ledger


def _build_ledger_index(ledger: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Return {action_type: row_dict} for O(1) lookup during annotation."""
    return {
        row["action_type"]: row
        for row in ledger["action_types"]
        if isinstance(row, dict) and isinstance(row.get("action_type"), str)
    }


# ---------------------------------------------------------------------------
# Action collection
# ---------------------------------------------------------------------------

def _preconditions_met(action: Dict[str, Any], repo: Dict[str, Any]) -> bool:
    """Return True iff all action preconditions are satisfied by the repo's signals.

    Supported preconditions:
        "last_run_failed"    – signals.last_run_ok must be False
        "artifacts_missing"  – signals.artifact_completeness < 1.0
        "determinism_failed" – signals.determinism_ok must be False

    An empty preconditions list always passes.
    Unknown preconditions fail closed (returns False).
    """
    preconditions = action.get("preconditions", [])
    if not preconditions:
        return True
    signals = repo.get("signals", {})
    for precondition in preconditions:
        if precondition == "last_run_failed":
            if signals.get("last_run_ok", True) is not False:
                return False
        elif precondition == "artifacts_missing":
            if float(signals.get("artifact_completeness", 1.0)) >= 1.0:
                return False
        elif precondition == "determinism_failed":
            if signals.get("determinism_ok", True) is not False:
                return False
        else:
            return False  # unknown precondition — fail closed
    return True


def _collect_actions(
    state: Dict[str, Any],
    repo_id_filter: Optional[str],
) -> List[Dict[str, Any]]:
    """Return deterministically sorted eligible actions, each with repo_id."""
    collected: List[Dict[str, Any]] = []

    for repo in state["repos"]:
        if not isinstance(repo, dict):
            continue
        rid = repo.get("repo_id", "")
        if repo_id_filter is not None and rid != repo_id_filter:
            continue
        actions = repo.get("recommended_actions", [])
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, dict):
                continue
            if not action.get("eligible", False):
                continue
            if not _preconditions_met(action, repo):
                continue
            entry = dict(action)
            entry["repo_id"] = rid
            collected.append(entry)

    # Deterministic sort: priority desc, action_type, action_id, repo_id.
    collected.sort(
        key=lambda a: (
            -a.get("priority", 0.0),
            a.get("action_type", ""),
            a.get("action_id", ""),
            a.get("repo_id", ""),
        )
    )
    return collected


# ---------------------------------------------------------------------------
# Ledger annotation
# ---------------------------------------------------------------------------

_LEDGER_DEFAULTS: Dict[str, Any] = {
    "effectiveness_score": 0.0,
    "recommended_priority_adjustment": 0.0,
    "classification": "neutral",
}


def _annotate_with_ledger(
    actions: List[Dict[str, Any]],
    ledger_index: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Add effectiveness fields to each action and re-sort by adjusted_priority."""
    annotated: List[Dict[str, Any]] = []
    for a in actions:
        entry = dict(a)
        row = ledger_index.get(a.get("action_type", ""), {})
        entry["effectiveness_score"] = float(
            row.get("effectiveness_score", _LEDGER_DEFAULTS["effectiveness_score"])
        )
        entry["recommended_priority_adjustment"] = float(
            row.get("recommended_priority_adjustment",
                    _LEDGER_DEFAULTS["recommended_priority_adjustment"])
        )
        entry["classification"] = str(
            row.get("classification", _LEDGER_DEFAULTS["classification"])
        )
        entry["adjusted_priority"] = round(
            a.get("priority", 0.0) + entry["recommended_priority_adjustment"], 2
        )
        annotated.append(entry)

    # Re-sort: adjusted_priority desc, priority desc, action_type, action_id, repo_id.
    annotated.sort(
        key=lambda a: (
            -a["adjusted_priority"],
            -a.get("priority", 0.0),
            a.get("action_type", ""),
            a.get("action_id", ""),
            a.get("repo_id", ""),
        )
    )
    return annotated


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _fmt_text(actions: List[Dict[str, Any]]) -> str:
    """Render a fixed-column text table (no ledger)."""
    if not actions:
        return "(no eligible actions)\n"

    # Column widths — at least header width, then data-driven.
    col_priority = max(8, max(len(f"{a.get('priority', 0.0):.2f}") for a in actions))
    col_action_type = max(11, max(len(a.get("action_type", "")) for a in actions))
    col_repo_id = max(7, max(len(a.get("repo_id", "")) for a in actions))
    col_action_id = max(9, max(len(a.get("action_id", "")) for a in actions))

    def _row(priority: str, action_type: str, repo_id: str, action_id: str) -> str:
        return (
            f"{priority:<{col_priority}}  "
            f"{action_type:<{col_action_type}}  "
            f"{repo_id:<{col_repo_id}}  "
            f"{action_id:<{col_action_id}}"
        )

    header = _row("priority", "action_type", "repo_id", "action_id")
    sep = "-" * len(header)
    lines = [header, sep]
    for a in actions:
        lines.append(_row(
            f"{a.get('priority', 0.0):.2f}",
            a.get("action_type", ""),
            a.get("repo_id", ""),
            a.get("action_id", ""),
        ))
    return "\n".join(lines) + "\n"


def _fmt_text_ledger(actions: List[Dict[str, Any]]) -> str:
    """Render a fixed-column text table with ledger-derived columns."""
    if not actions:
        return "(no eligible actions)\n"

    col_adj = max(17, max(len(f"{a.get('adjusted_priority', 0.0):.2f}") for a in actions))
    col_priority = max(8, max(len(f"{a.get('priority', 0.0):.2f}") for a in actions))
    col_action_type = max(11, max(len(a.get("action_type", "")) for a in actions))
    col_repo_id = max(7, max(len(a.get("repo_id", "")) for a in actions))
    col_classification = max(14, max(len(a.get("classification", "")) for a in actions))
    col_action_id = max(9, max(len(a.get("action_id", "")) for a in actions))

    def _row(adj: str, pri: str, at: str, rid: str, cls: str, aid: str) -> str:
        return (
            f"{adj:<{col_adj}}  "
            f"{pri:<{col_priority}}  "
            f"{at:<{col_action_type}}  "
            f"{rid:<{col_repo_id}}  "
            f"{cls:<{col_classification}}  "
            f"{aid:<{col_action_id}}"
        )

    header = _row("adjusted_priority", "priority", "action_type", "repo_id",
                  "classification", "action_id")
    sep = "-" * len(header)
    lines = [header, sep]
    for a in actions:
        lines.append(_row(
            f"{a.get('adjusted_priority', 0.0):.2f}",
            f"{a.get('priority', 0.0):.2f}",
            a.get("action_type", ""),
            a.get("repo_id", ""),
            a.get("classification", ""),
            a.get("action_id", ""),
        ))
    return "\n".join(lines) + "\n"


def _fmt_json(actions: List[Dict[str, Any]]) -> str:
    """Render a deterministic JSON array."""
    return json.dumps(actions, indent=2, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit a prioritized action queue from portfolio_state.json.",
    )
    parser.add_argument("--input", required=True, metavar="FILE",
                        help="Path to portfolio_state.json.")
    parser.add_argument("--json", dest="emit_json", action="store_true",
                        help="Emit JSON array instead of text table.")
    parser.add_argument("--repo-id", default=None, metavar="REPO_ID",
                        help="Filter to a single repo.")
    parser.add_argument("--ledger", default=None, metavar="FILE",
                        help="Path to action_effectiveness_ledger.json for annotation.")
    args = parser.parse_args(argv)

    try:
        state = _load_state(Path(args.input))
    except ValueError as exc:
        return _fail(str(exc))

    repo_id_filter: Optional[str] = args.repo_id
    actions = _collect_actions(state, repo_id_filter)

    if args.ledger is not None:
        try:
            ledger = _load_ledger(Path(args.ledger))
        except ValueError as exc:
            return _fail(str(exc))
        ledger_index = _build_ledger_index(ledger)
        actions = _annotate_with_ledger(actions, ledger_index)
        if args.emit_json:
            sys.stdout.write(_fmt_json(actions))
        else:
            sys.stdout.write(_fmt_text_ledger(actions))
    else:
        if args.emit_json:
            sys.stdout.write(_fmt_json(actions))
        else:
            sys.stdout.write(_fmt_text(actions))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
