# SPDX-License-Identifier: MIT
"""Archive a governed portfolio cycle artifact with a timestamped filename.

Usage:
    python3 scripts/archive_cycle_artifact.py \\
        --input governed_portfolio_cycle.json \\
        [--archive-dir artifacts/cycles] \\
        [--timestamp 2024-01-15T09-30-00]

Exit codes:
    0  — archived successfully
    1  — failure (input missing, etc.)
"""

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json_stdout(data):
    """Print *data* as deterministic JSON (indent=2, sort_keys) to stdout."""
    print(json.dumps(data, indent=2, sort_keys=True))


def _now_timestamp():
    """Return the current UTC time as a YYYY-MM-DDTHH-MM-SS string."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


def _archive_filename(timestamp):
    """Return the base archive filename for *timestamp* (no collision suffix)."""
    return f"{timestamp}_cycle.json"


def _resolve_archive_path(dst_dir, timestamp):
    """Return a Path inside *dst_dir* that does not yet exist.

    First choice is <timestamp>_cycle.json.  If that file already exists,
    append an incrementing integer suffix:
        <timestamp>_cycle_1.json
        <timestamp>_cycle_2.json
        ...

    Never overwrites an existing archive.

    Args:
        dst_dir:   Path to the (already-created) archive directory.
        timestamp: YYYY-MM-DDTHH-MM-SS string.

    Returns:
        pathlib.Path for a file that does not yet exist.
    """
    base = dst_dir / _archive_filename(timestamp)
    if not base.exists():
        return base
    counter = 1
    while True:
        candidate = dst_dir / f"{timestamp}_cycle_{counter}.json"
        if not candidate.exists():
            return candidate
        counter += 1


# ---------------------------------------------------------------------------
# Core archiver
# ---------------------------------------------------------------------------

def archive_artifact(input_path, archive_dir, timestamp=None, sidecar_paths=None):
    """Copy *input_path* into *archive_dir* with a timestamped filename.

    Args:
        input_path:    Path-like pointing to the cycle artifact JSON.
        archive_dir:   Directory to write the archive into (created if needed).
        timestamp:     Optional YYYY-MM-DDTHH-MM-SS override string.
                       Defaults to the current UTC time via _now_timestamp().
        sidecar_paths: Optional list of additional file paths to archive
                       alongside the main artifact.  Missing sidecars are
                       silently skipped; the main archive always proceeds.

    Returns:
        dict with keys: status, input, archived_to, sidecars_archived, timestamp.
        status is "ok" on success, "error" on any failure.
    """
    src = Path(input_path)
    if not src.exists():
        return {
            "archived_to": None,
            "input": str(src),
            "reason": f"input file not found: {src}",
            "sidecars_archived": [],
            "status": "error",
            "timestamp": timestamp,
        }

    ts = timestamp if timestamp is not None else _now_timestamp()
    dst_dir = Path(archive_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = _resolve_archive_path(dst_dir, ts)

    shutil.copy2(str(src), str(dst))

    sidecars_archived = []
    for sp in (sidecar_paths or []):
        sp_path = Path(sp)
        if sp_path.exists():
            sidecar_dst = dst_dir / f"{ts}_{sp_path.name}"
            shutil.copy2(str(sp_path), str(sidecar_dst))
            sidecars_archived.append(str(sidecar_dst))

    return {
        "archived_to": str(dst),
        "input": str(src),
        "sidecars_archived": sidecars_archived,
        "status": "ok",
        "timestamp": ts,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Archive a governed portfolio cycle artifact.",
        add_help=True,
    )
    parser.add_argument("--input", required=True, metavar="FILE",
                        help="Path to the cycle artifact JSON file to archive.")
    parser.add_argument("--archive-dir", default="artifacts/cycles", metavar="DIR",
                        help="Directory to write archives into (default: artifacts/cycles).")
    parser.add_argument("--timestamp", default=None, metavar="TIMESTAMP",
                        help="Override timestamp (YYYY-MM-DDTHH-MM-SS). Defaults to current UTC.")

    args = parser.parse_args(argv)
    result = archive_artifact(args.input, args.archive_dir, args.timestamp)
    _write_json_stdout(result)
    if result["status"] != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()
