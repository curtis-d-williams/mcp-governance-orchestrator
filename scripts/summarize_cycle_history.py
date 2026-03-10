# SPDX-License-Identifier: MIT
"""Summarize archived governed portfolio cycle artifacts.

Scans an archive directory for *_cycle*.json files, reads each,
and emits a compact chronological summary for operator observability.

Usage:
    python3 scripts/summarize_cycle_history.py
    python3 scripts/summarize_cycle_history.py --archive-dir artifacts/cycles --format csv
    python3 scripts/summarize_cycle_history.py --output summary.json

Exit codes:
    0  — always (empty archive is a valid, successful result)
"""

import argparse
import csv
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

_CSV_FIELDS = [
    "filename",
    "timestamp",
    "status",
    "phase",
    "selected_actions",
    "selected_actions_count",
    "risk_level",
    "attempts_count",
    "abort_reason",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path, data):
    """Write *data* as deterministic JSON (indent=2, sort_keys, trailing newline)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _extract_timestamp(filename):
    """Derive the timestamp prefix from an archive filename.

    Examples:
        2026-03-10T15-32-38_cycle.json   -> "2026-03-10T15-32-38"
        2026-03-10T15-32-38_cycle_1.json -> "2026-03-10T15-32-38"
    """
    stem = Path(filename).stem          # strip .json suffix
    idx = stem.find("_cycle")
    return stem[:idx] if idx != -1 else stem


def _extract_selected_actions(governed_result):
    """Return the selected_actions list from *governed_result*, or []."""
    if not isinstance(governed_result, dict):
        return []
    sa = governed_result.get("selected_actions")
    if isinstance(sa, list):
        return sa
    result = governed_result.get("result")
    if isinstance(result, dict):
        sa2 = result.get("selected_actions")
        if isinstance(sa2, list):
            return sa2
    return []


def _extract_risk_level(governed_result):
    """Return risk_level from the last attempt in *governed_result*, or None."""
    if not isinstance(governed_result, dict):
        return None
    attempts = governed_result.get("attempts")
    if isinstance(attempts, list) and attempts:
        return attempts[-1].get("risk_level")
    return None


def _summarize_cycle_file(path):
    """Summarize one cycle archive file.

    Returns a summary dict on success, or None when the file cannot be
    parsed as JSON (so the caller can skip it).  Partial/malformed cycle
    objects produce a best-effort row rather than raising.
    """
    try:
        cycle = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    filename = Path(path).name
    cycle_dict = cycle if isinstance(cycle, dict) else {}
    governed_result = cycle_dict.get("governed_result")
    if not isinstance(governed_result, dict):
        governed_result = {}

    selected_actions = _extract_selected_actions(governed_result)
    attempts = governed_result.get("attempts")
    attempts_count = len(attempts) if isinstance(attempts, list) else 0

    return {
        "abort_reason": governed_result.get("abort_reason"),
        "attempts_count": attempts_count,
        "filename": filename,
        "phase": cycle_dict.get("phase"),
        "risk_level": _extract_risk_level(governed_result),
        "selected_actions": selected_actions,
        "selected_actions_count": len(selected_actions),
        "status": cycle_dict.get("status"),
        "timestamp": _extract_timestamp(filename),
    }


def summarize_cycle_history(archive_dir):
    """Scan *archive_dir* and return a sorted list of cycle summary dicts.

    Returns an empty list when the directory does not exist or contains no
    matching files.  Invalid JSON files are silently skipped.
    """
    d = Path(archive_dir)
    if not d.exists():
        return []
    rows = []
    for p in sorted(d.glob("*_cycle*.json")):
        row = _summarize_cycle_file(p)
        if row is not None:
            rows.append(row)
    return rows


def _write_csv(out, rows):
    """Write *rows* as CSV.

    Args:
        out:  Path-like to write to, or None to write to stdout.
        rows: list of summary dicts (field order follows _CSV_FIELDS).
    """
    def _to_csv_row(r):
        sa = r.get("selected_actions") or []
        return [
            r.get("filename") or "",
            r.get("timestamp") or "",
            r.get("status") or "",
            r.get("phase") or "",
            ";".join(str(s) for s in sa),
            r.get("selected_actions_count", 0),
            r.get("risk_level") or "",
            r.get("attempts_count", 0),
            r.get("abort_reason") or "",
        ]

    if out is None:
        writer = csv.writer(sys.stdout)
        writer.writerow(_CSV_FIELDS)
        for r in rows:
            writer.writerow(_to_csv_row(r))
    else:
        with open(str(out), "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(_CSV_FIELDS)
            for r in rows:
                writer.writerow(_to_csv_row(r))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Summarize archived governed portfolio cycle artifacts.",
        add_help=True,
    )
    parser.add_argument("--archive-dir", default="artifacts/cycles", metavar="DIR",
                        help="Directory of archived cycle artifacts (default: artifacts/cycles).")
    parser.add_argument("--output", default=None, metavar="FILE",
                        help="Output file path. Omit to print to stdout.")
    parser.add_argument("--format", default="json", choices=["json", "csv"],
                        help="Output format: json or csv (default: json).")

    args = parser.parse_args(argv)
    rows = summarize_cycle_history(args.archive_dir)

    if args.format == "csv":
        _write_csv(args.output, rows)
    else:
        if args.output is not None:
            _write_json(args.output, rows)
        else:
            print(json.dumps(rows, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
