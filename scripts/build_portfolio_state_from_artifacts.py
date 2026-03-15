#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Artifact bridge: read Tier-3 outputs and produce portfolio_state.json.

Usage:
    python3 scripts/build_portfolio_state_from_artifacts.py \
        --report  <tier3_portfolio_report.csv> \
        --aggregate <tier3_multi_run_aggregate.json> \
        --output  <artifacts/portfolio_state.json> \
        [--comparison-gap-artifact <comparison_gap_artifact.json>] \
        [--generated-at <string>]

Fail-closed on malformed or missing required inputs.
generated_at defaults to empty string for deterministic output.

Mapping is conservative: never invent failures from ambiguous data.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from mcp_governance_orchestrator.capability_spec_registry import get_capability_spec  # noqa: E402
from mcp_governance_orchestrator.portfolio_state import build_portfolio_state  # noqa: E402


def _fail(msg: str) -> int:
    sys.stderr.write(f"error: {msg}\n")
    return 1


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def _repo_id_from_row(row: Dict[str, str]) -> str:
    """Return the repo identifier from a CSV row, trying common column names."""
    for key in ("repo_id", "repo", "id"):
        val = row.get(key, "").strip()
        if val:
            return val
    return ""


def _parse_row_result(row: Dict[str, str]) -> Dict[str, Any]:
    """Parse the JSON-encoded 'result' cell of a CSV row; return {} on failure."""
    raw = row.get("result", "")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _result_lifecycle_ok(result: Dict[str, Any]) -> bool:
    """Return True if result explicitly indicates a successful lifecycle."""
    if "lifecycle_ok" in result:
        return bool(result["lifecycle_ok"])
    review = result.get("review")
    if isinstance(review, dict) and "ok" in review:
        return bool(review["ok"])
    # No clear success indicator — treat as ambiguous (not a failure).
    return True


def _result_artifact_completeness(result: Dict[str, Any]) -> float:
    """Return 1.0/0.0 based on artifact presence; default 1.0 when unknown."""
    review = result.get("review")
    if isinstance(review, dict) and "artifacts" in review:
        arts = review["artifacts"]
        if isinstance(arts, list):
            return 1.0 if len(arts) > 0 else 0.0
    return 1.0


def _read_csv(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Return {repo_id: [result_dict, ...]} from the CSV report."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            rid = _repo_id_from_row(row)
            if not rid:
                continue
            out.setdefault(rid, []).append(_parse_row_result(row))
    return out


# ---------------------------------------------------------------------------
# Aggregate JSON helpers
# ---------------------------------------------------------------------------

def _read_aggregate(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Return {repo_id: [result_dict, ...]} from the aggregate JSON.

    Accepts both a top-level list of {repo, task, result} objects and a
    top-level dict with a single such object.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        items: List[Any] = [raw]
    elif isinstance(raw, list):
        items = raw
    else:
        return {}

    out: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        rid = ""
        for key in ("repo_id", "repo", "id"):
            val = item.get(key, "")
            if isinstance(val, str) and val.strip():
                rid = val.strip()
                break
        if not rid:
            continue
        result = item.get("result", {})
        if not isinstance(result, dict):
            result = {}
        out.setdefault(rid, []).append(result)
    return out


# ---------------------------------------------------------------------------
# Optional comparison-gap artifact helpers
# ---------------------------------------------------------------------------

def _read_comparison_gap_artifact(path: Path) -> List[str]:
    """Return sorted canonical capabilities from an optional gap artifact.

    Unknown or malformed capabilities are ignored.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return []

    gaps = raw.get("capability_gaps", [])
    if not isinstance(gaps, list):
        return []

    capabilities = set()
    for entry in gaps:
        if not isinstance(entry, dict):
            continue
        capability = entry.get("capability")
        if not isinstance(capability, str) or not capability:
            continue
        if not isinstance(get_capability_spec(capability), dict):
            continue
        capabilities.add(capability)

    return sorted(capabilities)


# ---------------------------------------------------------------------------
# Signal builder
# ---------------------------------------------------------------------------

def _determinism_ok(results: List[Dict[str, Any]]) -> bool:
    """Return False only when any result explicitly signals determinism failure."""
    for r in results:
        if r.get("determinism_ok") is False:
            return False
        if isinstance(r.get("determinism_failures"), int) and r["determinism_failures"] > 0:
            return False
        if r.get("consistent") is False:
            return False
    return True


def _build_signal(
    repo_id: str,
    csv_results: List[Dict[str, Any]],
    agg_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a normalized repo-signal dict from CSV and aggregate results.

    Conservative bias: only assert unhealthy state when explicitly evidenced.
    """
    # --- last_run_ok --------------------------------------------------------
    # False only when at least one CSV result explicitly shows lifecycle failure.
    if csv_results:
        fail_count = sum(1 for r in csv_results if not _result_lifecycle_ok(r))
        last_run_ok = fail_count == 0
    else:
        fail_count = 0
        last_run_ok = True  # no CSV evidence → default healthy

    # --- artifact_completeness ----------------------------------------------
    if csv_results:
        vals = [_result_artifact_completeness(r) for r in csv_results]
        avg = sum(vals) / len(vals)
        # Snap to 0.0 or 1.0 for clean signal when all agree; partial otherwise.
        if avg == 1.0:
            artifact_completeness = 1.0
        elif avg == 0.0:
            artifact_completeness = 0.0
        else:
            artifact_completeness = round(avg, 2)
    else:
        artifact_completeness = 1.0  # no evidence → default complete

    # --- determinism_ok -----------------------------------------------------
    # Check both CSV and aggregate results; aggregate is the richer source.
    det_ok = _determinism_ok(csv_results + agg_results)

    # --- recent_failures ----------------------------------------------------
    # Prefer explicit field from aggregate; fall back to CSV fail count.
    recent_failures: int = 0
    for r in agg_results:
        if isinstance(r.get("recent_failures"), int):
            recent_failures = r["recent_failures"]
            break
    else:
        recent_failures = fail_count  # 0 when last_run_ok is True

    # --- stale_runs ---------------------------------------------------------
    stale_runs: int = 0
    for r in agg_results:
        if isinstance(r.get("stale_runs"), int):
            stale_runs = r["stale_runs"]
            break

    return {
        "repo_id": repo_id,
        "last_run_ok": last_run_ok,
        "artifact_completeness": artifact_completeness,
        "determinism_ok": det_ok,
        "recent_failures": recent_failures,
        "stale_runs": stale_runs,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build portfolio_state.json from Tier-3 artifact outputs.",
    )
    parser.add_argument("--report", required=True, metavar="CSV",
                        help="Path to tier3_portfolio_report.csv.")
    parser.add_argument("--aggregate", required=True, metavar="JSON",
                        help="Path to tier3_multi_run_aggregate.json.")
    parser.add_argument("--output", required=True, metavar="JSON",
                        help="Destination path for portfolio_state.json.")
    parser.add_argument("--comparison-gap-artifact", default=None, metavar="JSON",
                        help="Optional capability-gap artifact derived from MCP comparison.")
    parser.add_argument("--generated-at", default="", metavar="STRING",
                        help="Value for generated_at field. Defaults to empty string.")
    args = parser.parse_args(argv)

    report_path = Path(args.report)
    agg_path = Path(args.aggregate)
    output_path = Path(args.output)
    comparison_gap_artifact_path = (
        Path(args.comparison_gap_artifact)
        if args.comparison_gap_artifact is not None
        else None
    )
    generated_at: str = args.generated_at

    # Fail closed on missing inputs.
    if not report_path.exists():
        return _fail(f"report file not found: {report_path}")
    if not agg_path.exists():
        return _fail(f"aggregate file not found: {agg_path}")
    if (
        comparison_gap_artifact_path is not None
        and not comparison_gap_artifact_path.exists()
    ):
        return _fail(
            f"comparison gap artifact file not found: {comparison_gap_artifact_path}"
        )

    # Read CSV.
    try:
        csv_data = _read_csv(report_path)
    except Exception as exc:
        return _fail(f"failed to read report CSV: {exc}")

    # Read aggregate JSON.
    try:
        agg_data = _read_aggregate(agg_path)
    except Exception as exc:
        return _fail(f"failed to read aggregate JSON: {exc}")

    # Read optional comparison-gap artifact.
    try:
        comparison_gap_capabilities = (
            _read_comparison_gap_artifact(comparison_gap_artifact_path)
            if comparison_gap_artifact_path is not None
            else []
        )
    except Exception as exc:
        return _fail(f"failed to read comparison gap artifact: {exc}")

    # Union of repo IDs from both sources, sorted for determinism.
    all_repo_ids = sorted(set(csv_data) | set(agg_data))
    if not all_repo_ids:
        return _fail("no repos found in input artifacts")

    signals = [
        _build_signal(rid, csv_data.get(rid, []), agg_data.get(rid, []))
        for rid in all_repo_ids
    ]

    try:
        state = build_portfolio_state(signals, generated_at=generated_at)
    except ValueError as exc:
        return _fail(f"portfolio state build failed: {exc}")

    if comparison_gap_capabilities:
        merged = sorted(
            set(state.get("capability_gaps", [])) | set(comparison_gap_capabilities)
        )
        state["capability_gaps"] = merged

    # Track persistence of capability gaps across cycles.
    previous_cycles = state.get("capability_gap_cycles", {})
    updated_cycles = {}

    for cap in state.get("capability_gaps", []):
        updated_cycles[cap] = int(previous_cycles.get(cap, 0)) + 1

    state["capability_gap_cycles"] = dict(sorted(updated_cycles.items()))


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
