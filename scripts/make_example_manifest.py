#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate the example portfolio manifest with the absolute repo root path.

run_governed_portfolio_cycle.py invokes run_portfolio_task.py in a work
subdirectory, so relative repo paths (like ".") resolve to the wrong directory.
This script writes manifests/portfolio_manifest_example.json with the absolute
repo root so the full cycle pipeline works correctly.

Usage (run from repo root):
    python3 scripts/make_example_manifest.py

Writes:
    manifests/portfolio_manifest_example.json
"""

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT = _REPO_ROOT / "manifests" / "portfolio_manifest_example.json"


def make_example_manifest(output_path=None):
    """Write portfolio_manifest_example.json with absolute repo root path.

    Args:
        output_path: Path-like for the output file. Defaults to
                     manifests/portfolio_manifest_example.json.

    Returns:
        Absolute Path of the written manifest.
    """
    dest = Path(output_path) if output_path is not None else _OUTPUT
    dest.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "repos": [
            {
                "id": "mcp-governance-orchestrator",
                "path": str(_REPO_ROOT),
            }
        ]
    }
    dest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return dest


if __name__ == "__main__":
    dest = make_example_manifest()
    sys.stdout.write(f"wrote: {dest}\n")
